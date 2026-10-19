"""Loan readiness and recommendation (Technical Documentation section 2.4).

SafeEMI = alpha * NCF_p25 - ExistingEMI
P_max   = SafeEMI * ((1+r)^n - 1) / (r (1+r)^n)
This is an estimate, never a loan approval.
"""

from datetime import date

import numpy as np

from app.engines.data import OWNER_DRAWINGS, BusinessData, active_months, last_full_months, monthly_totals

DISCLAIMER = "Estimate only, not a loan approval. Lenders make their own decisions."

ALPHA = {"Excellent": 0.40, "Good": 0.35, "Fair": 0.25, "Needs improvement": 0.15}


def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    if months <= 0:
        return 0.0
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def max_principal(safe_emi: float, annual_rate_pct: float, months: int) -> float:
    if safe_emi <= 0 or months <= 0:
        return 0.0
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return safe_emi * months
    return safe_emi * ((1 + r) ** months - 1) / (r * (1 + r) ** months)


def capacity(data: BusinessData, today: date, band: str) -> dict:
    months = active_months(data, last_full_months(today, 12))
    inc, exp = monthly_totals(data, months, exclude=OWNER_DRAWINGS) if months else ([], [])
    net = [a - b for a, b in zip(inc, exp)]
    ncf_p25 = float(np.percentile(net, 25)) if net else 0.0
    existing = sum(l.emi for l in data.loans if l.status == "active")
    alpha = ALPHA.get(band, 0.15)
    safe = alpha * ncf_p25 - existing
    return {
        "months_used": len(net),
        "monthly_net_cash_flow": [round(x) for x in net],
        "ncf_p25": round(ncf_p25),
        "alpha": alpha,
        "existing_emi": round(existing),
        "safe_emi": round(max(0.0, safe)),
    }


def checklist(data: BusinessData, today: date, cap: dict, credit: dict) -> list[dict]:
    items = []
    old_receivables = sum(i.outstanding for i in data.invoices if not i.paid_date and (today - i.due_date).days > 30)
    items.append({
        "item": "Collect receivables more than 30 days overdue",
        "done": old_receivables == 0,
        "detail": f"{round(old_receivables):,} outstanding for over 30 days" if old_receivables else "None outstanding",
    })
    items.append({
        "item": "Keep at least 6 months of records",
        "done": cap["months_used"] >= 6,
        "detail": f"{cap['months_used']} months recorded",
    })
    neg = sum(1 for x in cap["monthly_net_cash_flow"] if x <= 0)
    items.append({
        "item": "Keep most months cash-flow positive",
        "done": cap["months_used"] > 0 and neg / cap["months_used"] <= 0.25,
        "detail": f"{neg} of {cap['months_used']} months were negative",
    })
    items.append({
        "item": "Keep existing installments manageable",
        "done": cap["existing_emi"] <= 0.5 * max(cap["ncf_p25"], 1),
        "detail": f"Existing installments {cap['existing_emi']:,} per month",
    })
    items.append({
        "item": "Reach a credit score of 650 (Good) or higher",
        "done": credit["score"] >= 650,
        "detail": f"Current score {credit['score']} ({credit['band']})",
    })
    return items


def evaluate(p: dict, score: int, safe_emi: float) -> dict:
    """One loan type for one business: can it take it, how much, and if not, exactly why not."""
    base = {"product_id": p["id"], "name": p["name"], "lender": p["lender"], "kind": p["kind"], "rate": p["rate"],
            "tenure_months": p["tenure_months"], "min_amount": p["min_amount"], "max_amount": p["max_amount"],
            "min_score": p["min_score"]}
    if p["min_score"] > score:
        return {**base, "status": "score_too_low", "points_needed": p["min_score"] - score,
                "reason": f"Needs a credit score of {p['min_score']}. Yours is {score}, so {p['min_score'] - score} points to go."}
    pmax = max_principal(safe_emi, p["rate"], p["tenure_months"])
    if pmax < p["min_amount"]:
        needed = emi(p["min_amount"], p["rate"], p["tenure_months"])
        return {**base, "status": "capacity_too_low", "monthly_needed": round(needed),
                "reason": f"Your score qualifies, but the smallest loan ({p['min_amount']:,}) needs about "
                          f"{round(needed):,} a month and you can safely repay {round(safe_emi):,}."}
    amount = min(pmax, p["max_amount"])
    monthly = emi(amount, p["rate"], p["tenure_months"])
    total_interest = monthly * p["tenure_months"] - amount
    return {**base, "status": "eligible", "recommended_amount": round(amount, -2) or round(amount),
            "monthly_installment": round(monthly), "total_interest": round(total_interest),
            "cost_per_100": round(100 * total_interest / amount, 2) if amount else None}


def recommend(data: BusinessData, today: date, credit: dict, products: list[dict]) -> dict:
    cap = capacity(data, today, credit["band"])
    s = credit["score"]
    catalog = [evaluate(p, s, cap["safe_emi"]) for p in products]
    rank = {"eligible": 0, "capacity_too_low": 1, "score_too_low": 2}
    catalog.sort(key=lambda o: (rank[o["status"]], o.get("cost_per_100") if o["status"] == "eligible" else 0, o["min_score"]))
    options = [o for o in catalog if o["status"] == "eligible"]

    best_amount = max((o["recommended_amount"] for o in options), default=0)
    ready = bool(options) and cap["safe_emi"] > 0
    return {
        "ready": ready,
        "score": s,
        "band": credit["band"],
        "safe_monthly_installment": cap["safe_emi"],
        "max_recommended_amount": best_amount,
        "capacity": cap,
        "options": options,
        "catalog": catalog,
        "checklist": checklist(data, today, cap, credit),
        "disclaimer": DISCLAIMER,
    }
