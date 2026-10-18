"""Supplier negotiation assistant: dated cash flow, payment conflicts, payment plans, financing.

Dated cash flow (next 30 days). Every amount is counted exactly once and tagged:
  confirmed   known obligations with a date: supplier bills (or the installments of a plan the
              supplier accepted), loan installments, recurring payables such as rent and salaries
  estimated   forecast sales and running costs (from forecast.py), and receivables
Receivables are placed on each invoice's expected payment date: due date + that customer's
usual delay. An invoice already later than the customer usually pays is "at risk" and is
counted at a reduced weight a week from now. Payments already received are history, not future.

Nothing in this module pays, sends or applies for anything. It only calculates.
"""

import math
from datetime import date, timedelta

import numpy as np

from app.engines.collection import history
from app.engines.data import BusinessData, Inv
from app.engines.forecast import forecast

AT_RISK_WEIGHT = 0.6      # an invoice already later than the customer's habit: count 60%
NEW_CUSTOMER_WEIGHT = 0.8
NEW_CUSTOMER_DELAY = 7    # assume a week late until there's a record
LATE_RECEIPT_DAYS = 7     # at-risk invoices are expected a week from now
EXTENSION_STEPS = (7, 14, 21, 30)
ROUND_TO = 500


def _d(iso_or_date) -> date:
    return iso_or_date if isinstance(iso_or_date, date) else date.fromisoformat(iso_or_date)


# Receivables

def expected_receipts(data: BusinessData, today: date, horizon_end: date) -> list[dict]:
    """One row per open invoice: when its money is expected and how much of it we count."""
    rows = []
    for inv in data.invoices:
        owed = inv.outstanding
        if owed <= 0:
            continue
        h = history(data, inv.customer_id, today)
        if h.paid_invoices:
            delay = max(0, round(h.avg_delay_days or 0))
            weight, basis = 1.0, f"usually pays {delay} days after due" if delay else "usually pays on time"
        else:
            delay, weight, basis = NEW_CUSTOMER_DELAY, NEW_CUSTOMER_WEIGHT, "new customer, no payment record"
        expected = inv.due_date + timedelta(days=delay)
        at_risk = expected <= today  # already later than this customer's normal habit
        if at_risk:
            expected = today + timedelta(days=LATE_RECEIPT_DAYS)
            weight = min(weight, AT_RISK_WEIGHT)
            basis = f"{(today - inv.due_date).days} days overdue, later than usual"
        rows.append({
            "invoice_id": inv.id, "customer_id": inv.customer_id,
            "customer": data.customers.get(inv.customer_id, f"Customer {inv.customer_id}"),
            "outstanding": round(owed), "due_date": inv.due_date.isoformat(),
            "expected_date": expected.isoformat(), "days_late_expected": max(0, (expected - inv.due_date).days),
            "weight": weight, "counted": round(owed * weight), "at_risk": at_risk or weight < 1.0,
            "in_window": expected <= horizon_end, "basis": basis, "kind": "estimate",
        })
    rows.sort(key=lambda r: r["expected_date"])
    return rows


# Dated cash flow

def dated_cashflow(data: BusinessData, today: date, days: int = 30, extra: list[tuple[date, float, str]] = ()) -> dict:
    """Day-by-day balance with confirmed and estimated parts kept apart.

    extra: what-if movements (date, +in/-out, label), used to test plans and financing.
    """
    fc = forecast(data, today, days)
    horizon = [_d(r["date"]) for r in fc["series"]]
    end = horizon[-1]
    receipts = expected_receipts(data, today, end)
    recv_by_day: dict[date, float] = {}
    for r in receipts:
        if r["in_window"]:
            recv_by_day[_d(r["expected_date"])] = recv_by_day.get(_d(r["expected_date"]), 0.0) + r["counted"]
    extra_by_day: dict[date, float] = {}
    for when, amount, _ in extra:
        when = max(when, horizon[0])
        if when <= end:
            extra_by_day[when] = extra_by_day.get(when, 0.0) + amount

    balance = fc["start_balance"]
    threshold = fc["threshold"]
    rows = []
    for r in fc["series"]:
        day = _d(r["date"])
        est_in = r["income"] + recv_by_day.get(day, 0.0)
        est_out = r["expense"]
        conf_out = r["expected_outflow"]
        adj = extra_by_day.get(day, 0.0)
        balance += est_in - est_out - conf_out + adj
        rows.append({
            "date": r["date"], "estimated_in": round(est_in), "receivables_in": round(recv_by_day.get(day, 0.0)),
            "estimated_out": round(est_out), "confirmed_out": round(conf_out), "adjustment": round(adj),
            "balance": round(balance), "below_threshold": balance < threshold,
        })
    events = [{**e, "basis": "confirmed"} for e in fc["expected_outflows"]]
    return {"as_of": today.isoformat(), "start_balance": fc["start_balance"], "threshold": threshold,
            "series": rows, "outflows": events, "receipts": receipts}


def conflicts(cf: dict) -> list[dict]:
    """Runs of days below the safety threshold, with the payments that cause them."""
    out, run = [], []
    rows = cf["series"]
    for r in rows + [None]:
        if r and r["below_threshold"]:
            run.append(r)
            continue
        if run:
            start, stop = _d(run[0]["date"]), _d(run[-1]["date"])
            worst = min(run, key=lambda x: x["balance"])
            causes = [e for e in cf["outflows"]
                      if start - timedelta(days=3) <= _d(e["date"]) <= _d(worst["date"])]
            causes.sort(key=lambda e: -e["amount"])
            later = [x for x in cf["receipts"] if x["in_window"] and _d(x["expected_date"]) > start]
            gap = cf["threshold"] - worst["balance"]
            label = lambda e: e.get("supplier") or e.get("name") or "Loan installment"
            why = ", ".join(f"{label(e)} {round(e['amount']):,} on {_d(e['date']).strftime('%b %d')}"
                            for e in causes[:3]) or "running costs above income"
            text = (f"Cash stays below your safety level from {start.strftime('%b %d')} to {stop.strftime('%b %d')}, "
                    f"worst on {_d(worst['date']).strftime('%b %d')} ({round(gap):,} short). Main payments: {why}.")
            if later:
                text += (f" Money expected later ({later[0]['customer']} {later[0]['counted']:,} around "
                         f"{_d(later[0]['expected_date']).strftime('%b %d')}) arrives too late to cover it.")
            out.append({"start": start.isoformat(), "end": stop.isoformat(), "days": len(run),
                        "worst_date": worst["date"], "worst_gap": round(gap), "first_gap":
                        round(cf["threshold"] - run[0]["balance"]),
                        "causes": causes[:5], "receipts_after": later[:3], "explanation": text})
            run = []
    return out


# Payment plans for one bill

def _simulate(base: list[dict], threshold: float, payments: list[tuple[date, float]]) -> dict:
    """Balance path when the bill is paid as `payments` (base has the bill removed)."""
    by_day: dict[date, float] = {}
    for when, amount in payments:
        by_day[when] = by_day.get(when, 0.0) + amount
    first = _d(base[0]["date"])
    carried = sum(a for w, a in by_day.items() if w < first)  # overdue: paid on day one
    out, min_bal, below = 0.0, math.inf, 0
    for r in base:
        day = _d(r["date"])
        out += by_day.get(day, 0.0) + (carried if day == first else 0.0)
        bal = r["balance"] - out
        min_bal = min(min_bal, bal)
        below += bal < threshold
    return {"min_balance": round(min_bal), "days_below": below}


def _late_fee(amount: float, from_day: date, to_day: date, pct_month: float | None) -> float:
    days = (to_day - from_day).days
    return round(amount * (pct_month or 0) / 100 * days / 30) if days > 0 else 0.0


def bill_options(cf: dict, bill: dict, supplier: dict) -> list[dict]:
    """Ways to pay one bill: on time, extended, or in parts. All are proposals until approved and accepted."""
    threshold = cf["threshold"]
    amount, due = bill["outstanding"], _d(bill["due_date"])
    first_day = _d(cf["series"][0]["date"])
    horizon_end = _d(cf["series"][-1]["date"])
    # Put this bill's currently scheduled payments back to get the path without it.
    scheduled = {}
    for e in cf["outflows"]:
        if e["kind"] == "bill" and e.get("bill_id") == bill["bill_id"]:
            scheduled[_d(e["date"])] = scheduled.get(_d(e["date"]), 0.0) + e["amount"]
    base, add_back = [], 0.0
    for r in cf["series"]:
        add_back += scheduled.get(_d(r["date"]), 0.0)
        base.append({"date": r["date"], "balance": r["balance"] + add_back})
    pay_from = max(due, first_day)
    late_pct = supplier.get("late_fee_pct_month")

    def option(kind, installments, reasoning):
        sim = _simulate(base, threshold, installments)
        fee = sum(_late_fee(a, due, w, late_pct) for w, a in installments)
        return {"kind": kind,
                "installments": [{"due_date": w.isoformat(), "amount": round(a)} for w, a in installments],
                "days_extended": max(0, (max(w for w, _ in installments) - due).days),
                "estimated_fee": fee, "fee_basis": (f"{late_pct}% a month late fee in the supplier's terms; may be "
                                                    f"waived if they agree" if late_pct else "no late fee in terms"),
                "min_balance_after": sim["min_balance"], "days_below_after": sim["days_below"],
                "keeps_cash_safe": sim["days_below"] == 0, "reasoning": reasoning}

    options = [option("pay_on_time", [(pay_from, amount)], f"Pay the full {round(amount):,} on {pay_from:%b %d} as agreed.")]

    best_ext = None
    for step in EXTENSION_STEPS:
        when = due + timedelta(days=step)
        cand = option("extension", [(when, amount)],
                      f"Ask to move the full {round(amount):,} by {step} days, to {when:%b %d}.")
        if best_ext is None or cand["days_below_after"] < best_ext["days_below_after"]:
            best_ext = cand
        if cand["keeps_cash_safe"]:
            break
    options.append(best_ext)

    # Partial: pay what the cash can carry on the due date, the rest once it is affordable.
    headroom = min((r["balance"] - threshold) for r in base if _d(r["date"]) >= pay_from) if pay_from <= horizon_end else 0
    first = math.floor(max(0.0, min(headroom, amount)) / ROUND_TO) * ROUND_TO
    if first < 0.2 * amount:
        first = math.floor(0.25 * amount / ROUND_TO) * ROUND_TO  # a goodwill part-payment
    if 0 < first < amount:
        rest = amount - first
        later = None
        for r in base:
            day = _d(r["date"])
            if day <= pay_from:
                continue
            tail = [x["balance"] - first for x in base if _d(x["date"]) >= day]
            if min(tail) - rest >= threshold:
                later = day
                break
        later = later or due + timedelta(days=30)
        options.append(option("partial", [(pay_from, first), (later, rest)],
                              f"Pay {round(first):,} on {pay_from:%b %d} and the remaining {round(rest):,} on "
                              f"{later:%b %d}" + (" (after the 30-day forecast)" if later > horizon_end else "") + "."))
    for o in options:
        o["bill_id"] = bill["bill_id"]
    return options


# Financing comparison

def _emi(principal: float, monthly_rate: float, months: int) -> float:
    r = monthly_rate / 100
    if months <= 0:
        return principal
    return principal / months if r == 0 else principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def financing_options(today: date, need: float, need_by: date, days_needed: int, offers: list[dict],
                      receipts: list[dict]) -> list[dict]:
    """Principal, fees, interest, repayment dates, total repayment and total cost for each demo offer."""
    out = []
    days_needed = max(7, days_needed)
    for o in offers:
        funds_by = today + timedelta(days=o["lead_days"])
        base = {"offer_id": o["id"], "provider": o["provider"], "name": o["name"], "kind": o["kind"],
                "is_demo": o["is_demo"], "funds_available": funds_by.isoformat(),
                "min_amount": o["min_amount"], "max_amount": o["max_amount"],
                "meets_deadline": funds_by <= need_by,
                "label": "DEMO offer for comparison only. Not a real offer or approval." if o["is_demo"] else
                         "Estimate only. Not an approval."}
        if o["kind"] == "invoice_financing":
            eligible = [r for r in receipts if not r["at_risk"] and r["in_window"] and r["outstanding"] >= o["min_amount"]
                        and _d(r["expected_date"]) > funds_by]
            eligible.sort(key=lambda r: _d(r["expected_date"]))
            picked, principal, fees, interest, repayments = [], 0.0, 0.0, 0.0, []
            for r in eligible:
                if principal >= need:
                    break
                adv = r["outstanding"] * o["advance_rate_pct"] / 100
                days = (_d(r["expected_date"]) - funds_by).days
                fee = r["outstanding"] * o["fee_pct"] / 100
                intr = adv * o["monthly_rate_pct"] / 100 * days / 30
                principal, fees, interest = principal + adv, fees + fee, interest + intr
                repayments.append({"date": r["expected_date"], "amount": round(adv + fee + intr),
                                   "source": f"{r['customer']} pays invoice #{r['invoice_id']}"})
                picked.append({"invoice_id": r["invoice_id"], "customer": r["customer"], "face": r["outstanding"],
                               "advance": round(adv)})
            if not picked:
                continue
            avg_days = max(1, round(np.mean([(_d(x["date"]) - funds_by).days for x in repayments])))
            out.append({**base, "principal": round(principal), "fees": round(fees), "interest": round(interest),
                        "repayments": repayments, "invoices": picked, "days": avg_days,
                        "covers_need": principal >= need, "risk": "low",
                        "repaid_from": "customer payments on the financed invoices"})
            continue
        principal = min(o["max_amount"], max(o["min_amount"], math.ceil(need / 1000) * 1000))
        if principal <= 0:
            continue
        fees = principal * o["fee_pct"] / 100
        if o["kind"] == "overdraft":
            days = min(o["max_days"], days_needed)
            interest = principal * o["monthly_rate_pct"] / 100 * days / 30
            repay_day = funds_by + timedelta(days=days)
            repayments = [{"date": repay_day.isoformat(), "amount": round(principal + interest), "source": "your cash"}]
            risk = "medium"
        else:
            months = max(1, min(math.ceil(o["max_days"] / 30), math.ceil(days_needed / 30)))
            emi = _emi(principal, o["monthly_rate_pct"], months)
            interest = emi * months - principal
            repayments = [{"date": (funds_by + timedelta(days=30 * k)).isoformat(), "amount": round(emi),
                           "source": "your cash"} for k in range(1, months + 1)]
            days = 30 * months
            risk = "medium"
        out.append({**base, "principal": round(principal), "fees": round(fees), "interest": round(interest),
                    "repayments": repayments, "days": days, "covers_need": principal >= need, "risk": risk,
                    "repaid_from": "your cash"})
    for f in out:
        f["total_repayment"] = round(f["principal"] + f["fees"] + f["interest"])
        f["total_cost"] = round(f["fees"] + f["interest"])
        f["cost_per_100"] = round(100 * f["total_cost"] / f["principal"], 2) if f["principal"] else None
        f["effective_annual_rate_pct"] = (round(100 * f["total_cost"] / f["principal"] * 365 / max(f["days"], 1), 1)
                                          if f["principal"] else None)
    out.sort(key=lambda f: (not f["meets_deadline"], not f["covers_need"], f["cost_per_100"] or 1e9))
    return out
