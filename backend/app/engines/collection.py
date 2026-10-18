"""Receivable prioritization: who to collect from first, what to do, and how much credit to allow.

Collection Priority Score (0-100) = 100 * (0.30 A + 0.25 D + 0.15 R + 0.15 C + 0.15 P)
  A  amount owed, log-scaled against the largest balance
  D  aging bucket weight (current 0.05, 0-30 0.35, 31-60 0.60, 61-90 0.85, 90+ 1.00)
  R  payment-history risk = 1 - on-time rate (new customers 0.5)
  C  how much of the forecast cash gap the overdue amount covers (0-1)
  P  probability of a payment within 7 days

P comes from a logistic regression trained on this business's own past invoices when there are
enough examples, otherwise from transparent rules. Everything here is pure Python on BusinessData.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from sklearn.linear_model import LogisticRegression  # imported once at startup (slow first import)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.engines.data import BusinessData, Inv

WEIGHTS = {"A": 0.30, "D": 0.25, "R": 0.15, "C": 0.15, "P": 0.15}
BUCKET_WEIGHT = {"current": 0.05, "0-30": 0.35, "31-60": 0.60, "61-90": 0.85, "90+": 1.00}
NEW_CUSTOMER_LIMIT = 10_000
MIN_TRAINING_SAMPLES = 40
MIN_POSITIVES = 10
DISCOUNT_PCT = 2

ACTION_LABEL = {
    "stop_credit": "Stop further credit and visit",
    "visit": "Visit in person",
    "call": "Call today",
    "discount": f"Offer {DISCOUNT_PCT}% early-payment discount",
    "send_reminder": "Send a reminder",
    "wait": "No action yet (not due)",
}
ACTION_TONE = {"stop_credit": "final", "visit": "firm", "call": "firm", "discount": "friendly",
               "send_reminder": None, "wait": "friendly"}


def aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "0-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


@dataclass
class History:
    paid_invoices: int
    on_time_rate: float | None   # None = no history yet
    avg_delay_days: float | None
    partial_rate: float          # share of invoices paid in more than one payment


def history(data: BusinessData, customer_id: int, as_of: date) -> History:
    """Payment behavior using only what was known on as_of (no peeking at later payments)."""
    paid = [i for i in data.invoices if i.customer_id == customer_id and i.paid_date and i.paid_date <= as_of]
    if not paid:
        return History(0, None, None, 0.0)
    counts: dict[int, int] = {}
    ids = {i.id for i in paid}
    for p in data.payments:
        if p.invoice_id in ids and p.date <= as_of:
            counts[p.invoice_id] = counts.get(p.invoice_id, 0) + 1
    return History(
        paid_invoices=len(paid),
        on_time_rate=sum(1 for i in paid if i.paid_date <= i.due_date) / len(paid),
        avg_delay_days=float(np.mean([(i.paid_date - i.due_date).days for i in paid])),
        partial_rate=sum(1 for i in paid if counts.get(i.id, 1) > 1) / len(paid),
    )


def _payments_by_invoice(data: BusinessData) -> dict[int, list]:
    out: dict[int, list] = {}
    for p in data.payments:
        out.setdefault(p.invoice_id, []).append(p)
    return out


# Probability of a payment within 7 days

def _features(inv: Inv, outstanding: float, h: History, as_of: date) -> list[float]:
    days_over = (as_of - inv.due_date).days
    return [
        max(-1.0, min(6.0, days_over / 30)),
        h.on_time_rate if h.on_time_rate is not None else 0.5,
        max(-1.0, min(3.0, (h.avg_delay_days or 15) / 30)),
        h.partial_rate,
        math.log10(max(outstanding, 1.0)),
        1.0 if h.paid_invoices else 0.0,
    ]


def training_set(data: BusinessData, today: date) -> tuple[list[list[float]], list[int]]:
    """Weekly snapshots of past open invoices; label = any payment in the following 7 days."""
    if not data.invoices:
        return [], []
    first = min(i.issue_date for i in data.invoices) + timedelta(days=30)
    pays = _payments_by_invoice(data)
    X, y = [], []
    ref = first
    while ref <= today - timedelta(days=8):
        hist_cache: dict[int, History] = {}
        for inv in data.invoices:
            if inv.issue_date > ref or (inv.paid_date and inv.paid_date <= ref):
                continue
            inv_pays = pays.get(inv.id, [])
            owed = inv.amount - sum(p.amount for p in inv_pays if p.date <= ref)
            if owed <= 0:
                continue
            if inv.customer_id not in hist_cache:
                hist_cache[inv.customer_id] = history(data, inv.customer_id, ref)
            h = hist_cache[inv.customer_id]
            paid_next_week = any(ref < p.date <= ref + timedelta(days=7) for p in inv_pays)
            X.append(_features(inv, owed, h, ref))
            y.append(1 if paid_next_week else 0)
        ref += timedelta(days=7)
    return X, y


class PayModel:
    """Logistic regression when the data allows it, transparent rules otherwise."""

    def __init__(self, data: BusinessData, today: date):
        X, y = training_set(data, today)
        self.samples, self.positives = len(y), sum(y)
        self.model = None
        if self.samples >= MIN_TRAINING_SAMPLES and MIN_POSITIVES <= self.positives <= self.samples - MIN_POSITIVES:
            self.model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
            self.model.fit(np.array(X), np.array(y))
            self.train_accuracy = float(self.model.score(np.array(X), np.array(y)))
        self.method = "logistic_regression" if self.model is not None else "rules"

    def info(self) -> dict:
        out = {"method": self.method, "samples": self.samples, "positives": self.positives}
        if self.model is not None:
            out["train_accuracy"] = round(self.train_accuracy, 3)
        return out

    def predict(self, inv: Inv, outstanding: float, h: History, today: date) -> float:
        # A customer with no payment record tells the model nothing; use the rules for them.
        if self.model is not None and h.paid_invoices > 0:
            p = float(self.model.predict_proba(np.array([_features(inv, outstanding, h, today)]))[0][1])
        else:
            p = rule_probability(inv, h, today)
        return max(0.02, min(0.98, p))


def rule_probability(inv: Inv, h: History, today: date) -> float:
    """Fallback when there's too little history to train on."""
    base = h.on_time_rate if h.on_time_rate is not None else 0.5
    days_over = (today - inv.due_date).days
    if days_over < -7:
        p = 0.05 + 0.10 * base           # not due for a while: early payment is rare
    elif days_over <= 0:
        p = 0.15 + 0.75 * base           # due this week: reliable payers pay now
    else:
        p = (0.10 + 0.60 * base) * math.exp(-days_over / 60)  # the longer overdue, the less likely
    if h.partial_rate > 0.3:
        p += 0.10                        # partial payers tend to send something
    return p


# Scoring

def _relationship(data: BusinessData, today: date) -> dict[int, dict]:
    year_ago = today - timedelta(days=365)
    out = {}
    for cid in data.customers:
        invs = [i for i in data.invoices if i.customer_id == cid]
        recent = [i for i in invs if i.issue_date >= year_ago]
        since = min([i.issue_date for i in invs] + [data.customer_since.get(cid, today)])
        months = max(1.0, (today - since).days / 30.44)
        out[cid] = {"purchases_12m": sum(i.amount for i in recent),
                    "invoices_per_month": round(len(invs) / months, 2)}
    values = sorted(v["purchases_12m"] for v in out.values() if v["purchases_12m"] > 0)
    cut = values[int(0.8 * (len(values) - 1))] if len(values) >= 3 else math.inf
    for v in out.values():
        v["top_customer"] = v["purchases_12m"] >= cut and v["purchases_12m"] > 0
    return out


def credit_limit(data: BusinessData, customer_id: int, h: History, max_overdue: int, today: date) -> dict:
    if max_overdue > 90:
        return {"amount": 0, "basis": "More than 90 days overdue: stop credit until cleared"}
    if h.paid_invoices < 2:
        return {"amount": NEW_CUSTOMER_LIMIT, "basis": "New customer: starter limit until there is a payment record"}
    since = today - timedelta(days=90)
    monthly = sum(i.amount for i in data.invoices if i.customer_id == customer_id and i.issue_date >= since) / 3
    reliability = 0.5 + (h.on_time_rate or 0.0)  # 0.5 (never on time) to 1.5 (always on time)
    if h.partial_rate > 0.3:
        reliability *= 0.9
    amount = round(monthly * reliability / 500) * 500
    return {"amount": amount,
            "basis": f"Average monthly credit purchases {round(monthly):,} x reliability {reliability:.2f}"}


def recommend_action(bucket: str, p: float, outstanding: float, big_balance: float,
                     due_soon: bool, top_customer: bool) -> tuple[str, bool]:
    """Returns (action, softened_for_relationship)."""
    if bucket == "current":
        action = "send_reminder" if due_soon else "wait"
    elif bucket == "90+" or p < 0.20:
        action = "stop_credit"
    elif bucket == "61-90":
        action = "visit"
    elif bucket == "31-60":
        action = "call"
    elif 0.30 <= p <= 0.60 and outstanding >= big_balance:
        action = "discount"
    else:
        action = "send_reminder"
    softened = False
    if top_customer and action in ("stop_credit", "visit"):
        # Don't damage a relationship with a top customer: one step gentler.
        action, softened = ("visit" if action == "stop_credit" else "call"), True
    return action, softened


def score_customers(data: BusinessData, today: date, shortage_gap: float = 0.0,
                    model: PayModel | None = None) -> dict:
    model = model or PayModel(data, today)
    rel = _relationship(data, today)
    open_by_customer: dict[int, list[Inv]] = {}
    for inv in data.invoices:
        if inv.outstanding > 0:
            open_by_customer.setdefault(inv.customer_id, []).append(inv)

    rows = []
    for cid, invs in open_by_customer.items():
        h = history(data, cid, today)
        outstanding = sum(i.outstanding for i in invs)
        overdue_amount = sum(i.outstanding for i in invs if i.due_date < today)
        max_over = max(0, max((today - i.due_date).days for i in invs))
        p = max(model.predict(i, i.outstanding, h, today) for i in invs)
        rows.append({"cid": cid, "invs": invs, "h": h, "outstanding": outstanding,
                     "overdue": overdue_amount, "max_over": max_over, "p": p,
                     "due_soon": any(0 <= (i.due_date - today).days <= 3 for i in invs)})
    if not rows:
        return {"customers": [], "model": model.info()}

    max_out = max(r["outstanding"] for r in rows)
    big_balance = float(np.percentile([r["outstanding"] for r in rows], 75))
    result = []
    for r in rows:
        h, bucket = r["h"], aging_bucket(r["max_over"])
        features = {
            "A": math.log1p(r["outstanding"]) / math.log1p(max_out),
            "D": BUCKET_WEIGHT[bucket],
            "R": 1 - h.on_time_rate if h.on_time_rate is not None else 0.5,
            "C": min(1.0, r["overdue"] / shortage_gap) if shortage_gap > 0 else 0.0,
            "P": r["p"],
        }
        score = 100 * sum(WEIGHTS[k] * v for k, v in features.items())
        top = rel[r["cid"]]["top_customer"]
        action, softened = recommend_action(bucket, r["p"], r["outstanding"], big_balance, r["due_soon"], top)
        limit = credit_limit(data, r["cid"], h, r["max_over"], today)
        tone = ACTION_TONE[action] or ("friendly" if r["max_over"] <= 7 else "firm")
        result.append({
            "customer_id": r["cid"],
            "customer_name": data.customers.get(r["cid"], f"Customer {r['cid']}"),
            "score": round(score, 1),
            "outstanding": round(r["outstanding"]),
            "overdue_amount": round(r["overdue"]),
            "max_days_overdue": r["max_over"],
            "aging_bucket": bucket,
            "p_pay_7d": round(r["p"], 3),
            "action": action,
            "action_label": ACTION_LABEL[action],
            "softened_for_relationship": softened,
            "tone": tone,
            "credit_limit": limit["amount"],
            "credit_limit_basis": limit["basis"],
            "new_customer": h.paid_invoices == 0,
            "history": {"paid_invoices": h.paid_invoices,
                        "on_time_rate": round(h.on_time_rate, 2) if h.on_time_rate is not None else None,
                        "avg_delay_days": round(h.avg_delay_days, 1) if h.avg_delay_days is not None else None,
                        "partial_rate": round(h.partial_rate, 2)},
            "relationship": rel[r["cid"]],
            "closes_shortage": shortage_gap > 0 and r["overdue"] >= shortage_gap,
            "features": {k: round(v, 3) for k, v in features.items()},
            "invoices": sorted(({"invoice_id": i.id, "amount": round(i.outstanding),
                                 "original_amount": round(i.amount), "due_date": i.due_date.isoformat(),
                                 "days_overdue": max(0, (today - i.due_date).days)} for i in r["invs"]),
                               key=lambda x: -x["days_overdue"]),
        })
    result.sort(key=lambda x: -x["score"])
    for i, r in enumerate(result, start=1):
        r["rank"] = i
        # Older field names, kept so existing pages and the agent keep working.
        r["priority"] = round(r["score"] / 100, 3)
        r["late_payment_share"] = round(1 - r["history"]["on_time_rate"], 2) \
            if r["history"]["on_time_rate"] is not None else 0.5
        r["risk_level"] = "high" if r["aging_bucket"] in ("61-90", "90+") or r["p_pay_7d"] < 0.2 \
            else "medium" if r["aging_bucket"] == "31-60" or r["late_payment_share"] >= 0.25 else "low"
    return {"customers": result, "model": model.info()}
