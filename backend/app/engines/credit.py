"""Explainable credit scoring (Technical Documentation section 2.3).

S = 300 + 600 * sum(w_i * f_i);  Contribution_i = 600 * w_i * (f_i - b_i)
"""

import math
from datetime import date

import numpy as np

from app.engines.data import OWNER_DRAWINGS, BusinessData, active_months, last_full_months, monthly_totals

# (key, label, weight, healthy baseline)
FACTORS = [
    ("income_level", "Average monthly income", 0.20, 0.50),
    ("income_stability", "Income stability", 0.15, 0.60),
    ("positive_months", "Months with positive cash flow", 0.20, 0.75),
    ("receivables", "Outstanding receivables", 0.15, 0.70),
    ("repayment", "On-time repayment rate", 0.20, 0.90),
    ("business_age", "Business age", 0.10, 0.40),
]

# Log-scale range for average monthly income, in the business's own currency. Wide enough that a one-person shop
# earning a few thousand a month and a busy business earning hundreds of thousands both land inside it.
INCOME_LOW, INCOME_HIGH = 500, 500_000

# What each factor measures and what the owner can do about it, shown on the Credit Score page.
TIPS = {
    "income_level": "Record every sale and deposit in Transactions so your real monthly income shows. A higher average raises this.",
    "income_stability": "Steady income scores higher than big swings. Record income when it arrives, not in lumps.",
    "positive_months": "Counts months where more money came in than went out. Collect invoices on time and trim costs in weak months.",
    "receivables": "Compares unpaid invoices with a month of income. Chase overdue customers and mark invoices paid in the Ledger.",
    "repayment": "Loan installments and supplier bills paid on or before the due date. Add your loans (Loan Center) and bills (Ledger, I owe), and mark them paid on time.",
    "business_age": "Counts from your business start date, up to 5 years. It grows by itself.",
}

POSITIVE_TEXT = {
    "income_level": "Strong monthly income raised your score by {pts} points.",
    "income_stability": "Steady income from month to month raised your score by {pts} points.",
    "positive_months": "Most months ended with positive cash flow, adding {pts} points.",
    "receivables": "Low outstanding receivables added {pts} points.",
    "repayment": "Paying installments and bills on time added {pts} points.",
    "business_age": "An established business history added {pts} points.",
}
NEGATIVE_TEXT = {
    "income_level": "Low monthly income lowered your score by {pts} points.",
    "income_stability": "Income that swings a lot between months lowered your score by {pts} points.",
    "positive_months": "Too many months with negative cash flow lowered your score by {pts} points.",
    "receivables": "High outstanding receivables lowered your score by {pts} points.",
    "repayment": "Late installments or bills lowered your score by {pts} points.",
    "business_age": "A short business history lowered your score by {pts} points.",
}
NO_DATA_TEXT = ("Nothing is recorded yet, so every part of the score starts low. "
                "Add your sales and expenses and it builds from there.")
NO_HISTORY_TEXT = ("No loan or bill repayment history yet, so this part is held at a neutral level. "
                   "Paying a bill or installment on time builds it.")


def band_for(score: int) -> str:
    if score >= 750:
        return "Excellent"
    if score >= 650:
        return "Good"
    if score >= 550:
        return "Fair"
    return "Needs improvement"


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_features(data: BusinessData, today: date) -> tuple[dict[str, float], dict]:
    months = active_months(data, last_full_months(today, 12))
    if not months:
        months = [(today.year, today.month)]
    inc, exp = monthly_totals(data, months, exclude=OWNER_DRAWINGS)
    avg_inc = float(np.mean(inc)) if inc else 0.0

    f = {}
    if avg_inc > 0:
        f["income_level"] = _clip((math.log10(avg_inc) - math.log10(INCOME_LOW))
                                  / (math.log10(INCOME_HIGH) - math.log10(INCOME_LOW)))
        cv = float(np.std(inc) / avg_inc)
        f["income_stability"] = _clip(1 - cv)
    else:
        f["income_level"] = 0.0
        f["income_stability"] = 0.0

    net = [a - b for a, b in zip(inc, exp)]
    f["positive_months"] = sum(1 for x in net if x > 0) / len(net) if net else 0.0

    receivables = sum(i.outstanding for i in data.invoices)
    f["receivables"] = _clip(1 - receivables / avg_inc) if avg_inc > 0 else 0.0

    # On-time rate across loan repayments and supplier bills that have come due.
    due = [(r.due_date, r.paid_date) for r in data.repayments if r.due_date <= today]
    due += [(b.due_date, b.paid_date) for b in data.bills if b.due_date <= today]
    if due:
        f["repayment"] = sum(1 for d, p in due if p is not None and p <= d) / len(due)
    else:
        f["repayment"] = 0.5  # no history yet: neutral

    age_months = max(0, (today - data.started_at).days) / 30.44
    f["business_age"] = _clip(age_months / 60)

    raw = {
        "months_used": len(months),
        "avg_monthly_income": round(avg_inc),
        "avg_monthly_expense": round(float(np.mean(exp))) if exp else 0,
        "outstanding_receivables": round(receivables),
        "obligations_due": len(due),
        "business_age_months": round(age_months, 1),
    }
    return f, raw


def confidence_for(raw: dict) -> dict:
    """How much to trust the score: it needs real records. `missing` says exactly what to add."""
    missing = []
    if raw["avg_monthly_income"] <= 0:
        missing.append("No income is recorded yet. Add your sales in Transactions (or import a CSV).")
    if raw["months_used"] < 3:
        missing.append("Add at least 3 months of sales and expenses. The score looks at up to 12 months.")
    elif raw["months_used"] < 6:
        missing.append("A few more months of records (6 or more) will make the score steadier.")
    if raw["obligations_due"] == 0:
        missing.append("Add your loans and supplier bills and mark them paid on time to build your repayment record.")
    level = "low" if raw["avg_monthly_income"] <= 0 or raw["months_used"] < 3 else "medium" if raw["months_used"] < 6 else "high"
    return {"level": level, "months_used": raw["months_used"], "missing": missing}


def points(f: dict[str, float]) -> int:
    """The score for a set of factor values (the same formula score() uses)."""
    return int(round(300 + 600 * sum(w * f[key] for key, _, w, _ in FACTORS)))


def score(data: BusinessData, today: date) -> dict:
    f, raw = compute_features(data, today)
    total = 0.0
    factors = []
    for key, label, w, b in FACTORS:
        total += w * f[key]
        contribution = 600 * w * (f[key] - b)
        factors.append({
            "key": key, "label": label, "weight": w, "value": round(f[key], 3),
            "baseline": b, "contribution": round(contribution, 1), "tip": TIPS[key],
        })
    s = points(f)

    confidence = confidence_for(raw)
    positives = sorted([x for x in factors if x["contribution"] > 0], key=lambda x: -x["contribution"])[:3]
    negatives = sorted([x for x in factors if x["contribution"] < 0], key=lambda x: x["contribution"])[:3]
    reasons_up = [POSITIVE_TEXT[x["key"]].format(pts=round(x["contribution"])) for x in positives]
    reasons_down = [NO_HISTORY_TEXT if x["key"] == "repayment" and raw["obligations_due"] == 0
                    else NEGATIVE_TEXT[x["key"]].format(pts=round(-x["contribution"])) for x in negatives]

    if raw["avg_monthly_income"] <= 0:       # no records at all: do not blame the owner for each factor
        reasons_up, reasons_down = [], [NO_DATA_TEXT]
    return {
        "score": s,
        "band": band_for(s),
        "factors": factors,
        "reasons_positive": reasons_up,
        "reasons_negative": reasons_down,
        "inputs": raw,
        "confidence": confidence,
        "as_of": today.isoformat(),
    }
