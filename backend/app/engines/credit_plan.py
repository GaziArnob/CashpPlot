"""How to raise the credit score: concrete actions, each with the points it would add.

Every number comes from re-running the score formula (engines/credit.py) with the one thing changed, so the points
are what the same engine would give, not a guess. They are estimates: they assume the action happens and nothing else
moves, and the score is CashPilot's own, not a credit bureau's.
"""

import math
from datetime import date

import numpy as np

from app.engines.credit import (INCOME_HIGH, INCOME_LOW, _clip, band_for, compute_features, confidence_for,
                                points)
from app.engines.data import OWNER_DRAWINGS, BusinessData, active_months, last_full_months, monthly_totals

BANDS = [(550, "Fair"), (650, "Good"), (750, "Excellent")]
EXTRA_ON_TIME = 3        # "pay your next 3 bills or installments on time"
EXTRA_GOOD_MONTHS = 3    # "end your next 3 months in profit"
INCOME_GROWTH = 0.20
AGE_MONTHS = 6          # time alone

DISCLAIMER = ("Estimates from your own records: each shows the points if that one thing happens and nothing else "
              "changes. This is CashPilot's score, not a credit bureau's, and not a loan approval.")


def _with(f: dict, **changes) -> dict:
    return {**f, **changes}


def _action(key, title, detail, gain, link, kind="action"):
    return {"id": key, "title": title, "detail": detail, "points": gain, "link": link, "kind": kind}


def plan(data: BusinessData, today: date, loan_products: list[dict]) -> dict:
    f, raw = compute_features(data, today)
    current = points(f)
    avg_inc = raw["avg_monthly_income"]
    months = active_months(data, last_full_months(today, 12)) or [(today.year, today.month)]
    inc, exp = monthly_totals(data, months, exclude=OWNER_DRAWINGS)
    net = [a - b for a, b in zip(inc, exp)]

    actions, combined = [], {}

    # 1. Get paid on overdue invoices, customer by customer.
    overdue: dict[int, float] = {}
    for i in data.invoices:
        if i.outstanding > 0 and i.due_date < today:
            overdue[i.customer_id] = overdue.get(i.customer_id, 0.0) + i.outstanding
    total_recv = raw["outstanding_receivables"]
    if avg_inc > 0 and overdue:
        def recv_after(collected: float) -> float:
            return _clip(1 - max(0.0, total_recv - collected) / avg_inc)
        for cid, amount in sorted(overdue.items(), key=lambda kv: -kv[1])[:3]:
            gain = points(_with(f, receivables=recv_after(amount))) - current
            if gain >= 1:
                name = data.customers.get(cid, "A customer")
                actions.append(_action(f"collect:{cid}", f"Collect the overdue invoices from {name}",
                                       f"{round(amount):,} is past its due date. Once it is paid, the unpaid-invoices part of your score improves.",
                                       gain, "/ledger"))
        if len(overdue) > 1:
            everything = sum(overdue.values())
            gain = points(_with(f, receivables=recv_after(everything))) - current
            if gain >= 1:
                actions.append(_action("collect:all", f"Collect every overdue invoice ({len(overdue)} customers)",
                                       f"{round(everything):,} in total is past due.", gain, "/ledger"))
        combined["receivables"] = recv_after(sum(overdue.values()))

    # 2. Pay bills and loan installments on time.
    due = [(r.due_date, r.paid_date) for r in data.repayments if r.due_date <= today]
    due += [(b.due_date, b.paid_date) for b in data.bills if b.due_date <= today]
    on_time = sum(1 for d, p in due if p is not None and p <= d)
    if f["repayment"] < 0.99:
        rate_after = (on_time + EXTRA_ON_TIME) / (len(due) + EXTRA_ON_TIME)
        gain = points(_with(f, repayment=rate_after)) - current
        if gain >= 1:
            now = (f"{on_time} of {len(due)} paid on time so far." if due
                   else "You have no repayment history yet, so this part is held at a neutral level.")
            actions.append(_action("on_time", f"Pay your next {EXTRA_ON_TIME} bills or loan installments on time", now, gain, "/ledger"))
            combined["repayment"] = rate_after

    # 3. End months in profit.
    if net:
        window = (net + [1.0] * EXTRA_GOOD_MONTHS)[-12:]
        good_after = sum(1 for x in window if x > 0) / len(window)
        gain = points(_with(f, positive_months=good_after)) - current
        if gain >= 1:
            actions.append(_action("profit", f"End your next {EXTRA_GOOD_MONTHS} months with more money in than out",
                                   f"{sum(1 for x in net if x > 0)} of your last {len(net)} months were in profit.", gain, "/reports"))
            combined["positive_months"] = good_after

    # 4. Grow income.
    if avg_inc > 0:
        grown = _clip((math.log10(avg_inc * (1 + INCOME_GROWTH)) - math.log10(INCOME_LOW)) / (math.log10(INCOME_HIGH) - math.log10(INCOME_LOW)))
        gain = points(_with(f, income_level=grown)) - current
        if gain >= 1:
            actions.append(_action("income", f"Grow average monthly income by {round(INCOME_GROWTH * 100)}%",
                                   f"From about {round(avg_inc):,} to {round(avg_inc * (1 + INCOME_GROWTH)):,} a month.", gain, "/transactions"))
            combined["income_level"] = grown

    # 5. Time alone.
    age_after = _clip((raw["business_age_months"] + AGE_MONTHS) / 60)
    gain = points(_with(f, business_age=age_after)) - current
    if gain >= 1:
        actions.append(_action("age", f"Keep trading: in {AGE_MONTHS} months your business age adds points", "Nothing to do, it counts on its own.", gain, "/credit-score", kind="time"))

    actions.sort(key=lambda a: -a["points"])
    everything_score = points(_with(f, **combined))

    next_band = next(((t, b) for t, b in BANDS if t > current), None)
    higher = sorted((p for p in loan_products if p["min_score"] > current), key=lambda p: p["min_score"])
    return {
        "score": current,
        "band": band_for(current),
        "next_band": None if next_band is None else {
            "band": next_band[1], "score": next_band[0], "points_needed": next_band[0] - current,
            "reachable": everything_score >= next_band[0]},
        "next_loan": None if not higher else {
            "name": higher[0]["name"], "min_score": higher[0]["min_score"], "points_needed": higher[0]["min_score"] - current,
            "reachable": everything_score >= higher[0]["min_score"]},
        "actions": actions,
        "needs_data": confidence_for(raw)["missing"],
        "if_you_do_everything": {
            "score": everything_score, "band": band_for(everything_score), "points": everything_score - current,
            "unlocks": [p["name"] for p in loan_products if current < p["min_score"] <= everything_score],
        },
        "disclaimer": DISCLAIMER,
    }
