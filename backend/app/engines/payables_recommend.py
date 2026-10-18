"""Recommendation for the supplier negotiation assistant.

Picks the cheapest steps that really lift the lowest balance above the safety level. Every step is
judged by applying its dated cash movements to the forecast, so a loan that is repaid before the
worst day, or a bill moved to a day that is just as tight, earns no credit. Pure calculation:
nothing is paid, sent or applied for.
"""

import math
from datetime import date

from app.engines.payables import _d, conflicts

RISK_RANK = {"low": 0, "medium": 1, "high": 2}


def step_effects(c: dict, cf: dict) -> list[tuple[date, float]]:
    """Dated cash effect of one candidate step versus the current forecast (+ in, - out)."""
    if c["type"] == "supplier_plan":
        undo = [(_d(e["date"]), e["amount"]) for e in cf["outflows"]
                if e["kind"] == "bill" and e.get("bill_id") == c["bill_id"]]
        new = [(_d(i["due_date"]), -i["amount"]) for i in c["plan"]["installments"]]
        return undo + new
    f = c["financing"]
    return [(_d(f["funds_available"]), float(f["principal"]))] + [
        (_d(r["date"]), -float(r["amount"])) for r in f["repayments"]]


def path_with(cf: dict, effects: list[tuple[date, float]]) -> dict:
    """Lowest balance and days below the safety level once `effects` are applied to the forecast."""
    first = _d(cf["series"][0]["date"])
    by_day: dict[date, float] = {}
    for when, amount in effects:
        when = max(when, first)
        by_day[when] = by_day.get(when, 0.0) + amount
    running, low, below, low_day = 0.0, math.inf, 0, None
    for r in cf["series"]:
        running += by_day.get(_d(r["date"]), 0.0)
        bal = r["balance"] + running
        if bal < low:
            low, low_day = bal, r["date"]
        below += bal < cf["threshold"]
    return {"min_balance": round(low), "min_date": low_day, "days_below": below}


def size_financing(f: dict, shortfall: float) -> dict:
    """A loan or overdraft only needs to cover what is still short. Cost scales with the amount.

    Invoice financing is fixed by the invoices advanced against, so it is returned as is.
    """
    if f["kind"] == "invoice_financing" or f["principal"] <= 0:
        return f
    target = math.ceil(max(shortfall, 1) / 1000) * 1000
    principal = min(f["principal"], max(f["min_amount"], target))
    if principal >= f["principal"]:
        return f
    k = principal / f["principal"]
    sized = dict(f)
    sized.update(principal=round(principal), fees=round(f["fees"] * k), interest=round(f["interest"] * k),
                 repayments=[{**r, "amount": round(r["amount"] * k)} for r in f["repayments"]])
    sized["total_repayment"] = round(sized["principal"] + sized["fees"] + sized["interest"])
    sized["total_cost"] = round(sized["fees"] + sized["interest"])
    sized["cost_per_100"] = round(100 * sized["total_cost"] / sized["principal"], 2)
    return sized


def _why(c: dict, relief: float) -> str:
    if c["type"] == "supplier_plan":
        p, bill, record = c["plan"], c["bill"], c.get("record")
        history = (f"You paid {bill['supplier']} on time {round(record * 100)}% of the time, which helps."
                   if record is not None else "No payment record with this supplier yet.")
        return (f"{p['reasoning']} Raises the lowest balance by {round(relief):,}. Estimated cost "
                f"{p['estimated_fee']:,} ({p['fee_basis']}). {history}")
    f = c["financing"]
    return (f"{f['name']} ({f['provider']}): {f['principal']:,} available by {_d(f['funds_available']):%b %d}, "
            f"total cost {f['total_cost']:,} ({f['effective_annual_rate_pct']}% a year), repaid from "
            f"{f['repaid_from']}. Raises the lowest balance by {round(relief):,}. {f['label']}")


def recommend(cf: dict, bill_plans: list[list[dict]], fin: list[dict], suppliers: dict[int, dict],
              bills: list[dict], today: date) -> dict:
    found = conflicts(cf)
    if not found:
        return {"shortfall": 0, "shortfall_date": None, "headline": "No payment conflict in the next 30 days.",
                "steps": [], "alternatives": [], "total_cost": 0, "remaining_gap": 0,
                "lowest_balance_before": path_with(cf, [])["min_balance"],
                "lowest_balance_after": path_with(cf, [])["min_balance"],
                "reasoning": ["Cash stays above your safety level, so no supplier changes or financing are needed."]}
    worst = max(found, key=lambda c: c["worst_gap"])
    need, need_by = worst["worst_gap"], _d(found[0]["start"])
    threshold = cf["threshold"]

    candidates: list[dict] = []
    for plans in bill_plans:
        bill = next(b for b in bills if b["bill_id"] == plans[0]["bill_id"])
        record = suppliers.get(bill["supplier_id"], {}).get("on_time_rate")
        for p in plans:
            if p["kind"] == "pay_on_time":
                continue
            risk = "low" if (record or 0) >= 0.8 and p["kind"] == "partial" else "medium"
            candidates.append({"type": "supplier_plan", "kind": p["kind"], "bill_id": bill["bill_id"],
                               "supplier": bill["supplier"], "cost": p["estimated_fee"], "risk": risk,
                               "meets_deadline": True, "needs_agreement": True, "plan": p, "record": record,
                               "bill": bill})
    for f in fin:
        candidates.append({"type": "financing", "kind": f["kind"], "offer_id": f["offer_id"], "name": f["name"],
                           "cost": f["total_cost"], "risk": f["risk"], "meets_deadline": f["meets_deadline"],
                           "needs_agreement": False, "financing": f})

    base_low = path_with(cf, [])["min_balance"]
    for c in candidates:
        c["standalone"] = path_with(cf, step_effects(c, cf))["min_balance"] - base_low

    chosen: list[dict] = []
    effects: list[tuple[date, float]] = []
    used_bills, used_kinds = set(), set()
    current = path_with(cf, effects)
    while current["min_balance"] < threshold:
        best = None
        for c in candidates:
            if c in chosen or not c["meets_deadline"]:
                continue
            if c["type"] == "supplier_plan" and c["bill_id"] in used_bills:
                continue
            if c["type"] == "financing" and c["kind"] in used_kinds:
                continue
            if c["type"] == "financing":  # size debt to the gap still left, not the original one
                sized = size_financing(c["financing"], threshold - current["min_balance"])
                c = {**c, "financing": sized, "cost": sized["total_cost"]}
            after = path_with(cf, effects + step_effects(c, cf))
            relief = after["min_balance"] - current["min_balance"]
            if relief <= 0:
                continue
            # Cheapest per taka of relief; supplier changes before debt; then lower risk.
            key = (round(c["cost"] / relief, 4), c["type"] != "supplier_plan", RISK_RANK[c["risk"]])
            if best is None or key < best[0]:
                best = (key, c, relief, after)
        if best is None:
            break
        _, c, relief, after = best
        c["relief"], c["why"] = round(relief), _why(c, relief)
        # Replace the unsized candidate by the sized one so alternatives don't list it twice.
        original = next(x for x in candidates if x["type"] == c["type"] and x.get("offer_id") == c.get("offer_id")
                        and x.get("bill_id") == c.get("bill_id") and x["kind"] == c["kind"])
        candidates[candidates.index(original)] = c
        chosen.append(c)
        effects += step_effects(c, cf)
        current = after
        if c["type"] == "supplier_plan":
            used_bills.add(c["bill_id"])
        else:
            used_kinds.add(c["kind"])

    remaining = round(max(0.0, threshold - current["min_balance"]))
    alternatives = []
    for c in candidates:
        if c in chosen:
            continue
        c["relief"] = round(c["standalone"])
        c["why"] = _why(c, c["standalone"]) if c["standalone"] > 0 else ""
        c["why_not"] = ("funds arrive after the shortfall starts" if not c["meets_deadline"]
                        else "does not raise the lowest balance" if c["standalone"] <= 0
                        else "not needed once the chosen steps are in place" if not remaining
                        else "costs more per taka of relief than the chosen steps")
        alternatives.append(c)
    for c in chosen + alternatives:
        c.pop("bill", None)
        c.pop("standalone", None)

    total_cost = round(sum(c["cost"] for c in chosen))
    names = "; ".join(f"{c['kind'].replace('_', ' ')} with {c['supplier']}" if c["type"] == "supplier_plan"
                      else c["name"] for c in chosen)
    headline = (f"Cover the {need:,} gap from {need_by:%b %d} with: {names}. Estimated cost {total_cost:,}."
                if chosen else f"{need:,} short from {need_by:%b %d}; no option fits in time.")
    if chosen and remaining:
        headline += f" About {remaining:,} would still be short."
    reasoning = [
        f"The tightest point is {_d(worst['worst_date']):%b %d}, {need:,} below your safety level. {worst['explanation']}",
        "Each step was tested by applying its dated cash movements to your forecast, so a loan repaid before the "
        "tightest day gets no credit. Steps are ranked by cost per taka of relief, then supplier changes before "
        "debt, then risk.",
        f"With the chosen steps the lowest balance rises from {base_low:,} to {current['min_balance']:,} "
        f"(your safety level is {round(threshold):,}).",
    ]
    if remaining:
        reasoning.append(f"About {remaining:,} is still not covered; see the Cash Advisor plan (collections, "
                         f"clearing stock, cutting drawings).")
    return {"shortfall": need, "shortfall_date": need_by.isoformat(), "headline": headline, "steps": chosen,
            "alternatives": alternatives, "total_cost": total_cost, "remaining_gap": remaining,
            "lowest_balance_before": base_low, "lowest_balance_after": current["min_balance"],
            "reasoning": reasoning, "generated_for": today.isoformat()}
