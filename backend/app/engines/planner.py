"""Action plan: turn the forecast, collection scores and product scores into ordered steps.

Order of preference (cheapest and safest first):
  1. collect      overdue money from the highest-scoring customers
  2. clear_stock  slow movers and dead stock at a discount
  3. delay_payable  ask suppliers to push bills that fall before the cash gap
  4. cut_expense  owner drawings and spending that jumped above normal
  5. scale_up     stars, once there is spare cash (uses cash)
  6. financing    a loan, only for what is still missing after 1-4

Every action carries: expected cash impact, days until it lands, risk, and the reasoning with its
numbers. Cash-raising actions are marked optional once earlier ones already cover the gap.
All amounts come from the other engines; this module only combines them.
"""

from datetime import date, timedelta

COLLECT_TOP = 5
SELL_THROUGH = {"slow": 0.7, "dead": 0.6}      # share of the clearance we expect to sell within the month
CLEAR_DAYS = {"slow": 21, "dead": 14}
MIN_CLEAR_AMOUNT = 1_000
DELAY_DAYS = 14
DRAWINGS_CUT = 0.5
DRAWINGS_CATEGORIES = {"Owner drawings"}
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
KIND_ORDER = {"collect": 0, "clear_stock": 1, "delay_payable": 2, "cut_expense": 3, "scale_up": 4, "financing": 5}


def _risk_from_probability(p: float) -> str:
    return "low" if p >= 0.6 else "medium" if p >= 0.35 else "high"


def _money(n: float) -> str:
    return f"{round(n):,}"


def build_plan(today: date, fc: dict, collections: list[dict], products: dict, insights: list[dict],
               loan: dict | None) -> dict:
    gap = float(fc.get("largest_gap") or 0)
    first = fc.get("first_shortage")
    first_date = date.fromisoformat(first["date"]) if first else None
    actions: list[dict] = []

    def add(kind, title, impact, days, risk, reasoning, target=None, data=None):
        lands = today + timedelta(days=days)
        actions.append({
            "kind": kind, "title": title, "target_ref": target, "cash_impact": round(impact),
            "days_to_impact": days, "risk": risk, "reasoning": reasoning, "data": data or {},
            "lands_after_shortage": bool(first_date and impact > 0 and lands > first_date),
        })

    # 1. Collect from the customers worth chasing this week.
    chase = [c for c in collections if c["overdue_amount"] > 0 or c["action"] == "send_reminder"][:COLLECT_TOP]
    if chase:
        owed = sum(c["outstanding"] for c in chase)
        expected = sum(c["outstanding"] * c["p_pay_7d"] for c in chase)
        names = ", ".join(c["customer_name"] for c in chase)
        add("collect", f"Collect {_money(owed)} from {len(chase)} customers this week",
            expected, 7, _risk_from_probability(expected / owed if owed else 0),
            f"{names} owe {_money(owed)} in total. Based on each one's payment history, about "
            f"{_money(expected)} is likely to come in within 7 days if you follow up as suggested.",
            target="collect:top", data={"owed": round(owed), "customers": [
                {"customer_id": c["customer_id"], "name": c["customer_name"], "outstanding": c["outstanding"],
                 "p_pay_7d": c["p_pay_7d"], "action": c["action_label"]} for c in chase]})

    # 2. Clear slow-moving and dead stock.
    clear = [p for p in products.get("products", [])
             if p["product_class"] in SELL_THROUGH and p["cash_impact"] >= MIN_CLEAR_AMOUNT]
    for p in sorted(clear, key=lambda x: -x["cash_impact"]):
        cls = p["product_class"]
        expected = p["cash_impact"] * SELL_THROUGH[cls]
        units = -p["recommended_qty_change"]
        why = (f"no sale in {p['days_since_last_sale']} days" if cls == "dead"
               else f"{round(p['days_of_stock'] or 0)} days of stock on hand")
        add("clear_stock", f"Clear {units:g} units of {p['name']} at {p.get('discount_pct', 0)}% off",
            expected, CLEAR_DAYS[cls], "medium" if cls == "dead" else "low",
            f"{p['name']} is a {'dead stock' if cls == 'dead' else 'slow-moving'} item ({why}). Selling the "
            f"extra {units:g} units at {p.get('discount_pct', 0)}% off could free {_money(p['cash_impact'])}; "
            f"we count {round(SELL_THROUGH[cls] * 100)}% of that as likely this month.",
            target=f"product:{p['product_id']}",
            data={"potential": p["cash_impact"], "units": units, "discount_pct": p.get("discount_pct", 0)})

    # 3. Ask to delay supplier bills that fall on or before the cash gap.
    if first_date:
        for b in fc.get("expected_outflows", []):
            due = date.fromisoformat(b["date"])
            if b["kind"] == "bill" and due <= first_date + timedelta(days=3):
                add("delay_payable", f"Ask {b['supplier']} to move the {_money(b['amount'])} bill by {DELAY_DAYS} days",
                    b["amount"], max(0, (due - today).days), "medium",
                    f"This bill is due {due.strftime('%b %d')}, right when cash falls short. Moving it "
                    f"{DELAY_DAYS} days keeps {_money(b['amount'])} in hand until collections come in. "
                    f"It is a timing change, not a saving.",
                    target=f"bill:{b['bill_id']}", data={"supplier": b["supplier"], "amount": b["amount"],
                                                        "due_date": b["date"], "new_due_date":
                                                        (due + timedelta(days=DELAY_DAYS)).isoformat()})

    # 4. Cut or pause expenses.
    for e in fc.get("expected_outflows", []):
        if e["kind"] == "recurring" and e.get("category") in DRAWINGS_CATEGORIES:
            cut = e["amount"] * DRAWINGS_CUT
            add("cut_expense", f"Take {round(DRAWINGS_CUT * 100)}% less in owner drawings this month",
                cut, max(0, (date.fromisoformat(e["date"]) - today).days), "low",
                f"{_money(e['amount'])} is planned to be withdrawn on {date.fromisoformat(e['date']).strftime('%b %d')}. "
                f"Taking half keeps {_money(cut)} in the business while cash is tight.",
                target=f"recurring:{e.get('name')}", data={"planned": e["amount"]})
    for i in insights:
        if i.get("direction") == "up" and i.get("monthly_average"):
            excess = i["last_30_days"] - i["monthly_average"]
            if excess >= MIN_CLEAR_AMOUNT:
                add("cut_expense", f"Bring {i['category']} spending back to normal",
                    excess, 7, "low",
                    f"{i['category']} cost {_money(i['last_30_days'])} in the last 30 days against a usual "
                    f"{_money(i['monthly_average'])} a month (+{i['change_pct']}%). Returning to normal saves about "
                    f"{_money(excess)} a month.", target=f"category:{i['category']}")

    # 5. Scale up stars: uses cash, so only now if the budget allows, otherwise once cash recovers.
    for p in products.get("products", []):
        if p["product_class"] != "star" or not p.get("scale_up_cash_needed"):
            continue
        now_cash = -p["cash_impact"]
        needed = p["scale_up_cash_needed"]
        if now_cash > 0:
            title = f"Stock {p['recommended_qty_change']:g} more units of {p['name']} now"
            why = f"There is spare cash above your safety level; {p['name']} is a top seller with a {p['margin_pct']}% margin."
            impact = -now_cash
        else:
            title = f"Increase stock of {p['name']} once {_money(needed)} is spare"
            why = (f"{p['name']} sells fast at a {p['margin_pct']}% margin, but scaling up needs {_money(needed)} "
                   f"above your safety level, which isn't there yet. Do it after the cash gap is closed.")
            impact = 0
        add("scale_up", title, impact, 30, "low", why, target=f"product:{p['product_id']}",
            data={"cash_needed": needed, "spend_now": now_cash})

    # Pick the cash-raising actions needed to cover the gap: lowest risk first, then the ones that
    # land soonest, then the preferred kind. Whatever isn't needed is optional.
    for a in actions:
        a["optional"] = True
    covered = 0.0
    candidates = sorted((a for a in actions if a["cash_impact"] > 0),
                        key=lambda a: (RISK_ORDER[a["risk"]], a["days_to_impact"], KIND_ORDER[a["kind"]]))
    if gap <= 0:
        for a in candidates:
            a["optional"] = a["kind"] != "collect"  # no gap: collecting is still good practice
    for a in candidates:
        if gap <= 0 or covered >= gap:
            break
        a["optional"] = False
        covered += a["cash_impact"]
    remaining = max(0.0, gap - covered)

    # 6. Financing, only for what is still missing.
    if remaining > 0:
        option = None
        if loan and loan.get("options"):
            fits = [o for o in loan["options"] if o["recommended_amount"] >= remaining]
            option = min(fits, key=lambda o: o["recommended_amount"]) if fits else max(
                loan["options"], key=lambda o: o["recommended_amount"])
        if option:
            add("financing", f"Short-term loan: {option['name']} ({option['lender']})",
                min(option["recommended_amount"], remaining), 10, "medium",
                f"After the steps above, about {_money(remaining)} is still missing. {option['name']} could cover it "
                f"at {option['rate']}% for {option['tenure_months']} months (about "
                f"{_money(option['monthly_installment'])} a month). This is an estimate, not a loan approval.",
                target=f"loan_product:{option['product_id']}", data={"option": option})
        else:
            add("financing", "Arrange short-term credit for the remaining gap", remaining, 14, "high",
                f"About {_money(remaining)} is still missing and no listed loan fits safely right now. Ask your "
                f"main supplier for extended credit or your bank for an overdraft.", target="financing:general")
        actions[-1]["optional"] = False

    # Needed steps first, soonest first; then optional ones in the preferred order.
    actions.sort(key=lambda a: (a["optional"], a["days_to_impact"] if not a["optional"] else 0,
                                KIND_ORDER[a["kind"]], -a["cash_impact"]))
    for rank, a in enumerate(actions, start=1):
        a["rank"] = rank
    planned = sum(a["cash_impact"] for a in actions if a["cash_impact"] > 0 and not a["optional"])
    return {
        "as_of": today.isoformat(),
        "gap": round(gap),
        "first_shortage": first,
        "expected_from_plan": round(planned),
        "gap_covered": planned >= gap,
        "remaining_gap": round(max(0.0, gap - planned)),
        "actions": actions,
    }
