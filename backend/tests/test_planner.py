"""Action plan: which steps are needed, their order, financing as a last resort, and the checklist API."""

from datetime import date, timedelta

from app.engines.planner import build_plan

TODAY = date(2026, 10, 17)


def day(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def forecast(gap=0, shortage_day=9, bills=(), drawings=None):
    outflows = [{"date": day(d), "kind": "bill", "bill_id": i, "supplier": f"S{i}", "amount": a, "overdue": False}
                for i, (d, a) in enumerate(bills, start=1)]
    if drawings:
        outflows.append({"date": day(11), "kind": "recurring", "name": "Owner draw", "category": "Owner drawings",
                         "amount": drawings, "overdue": False})
    first = {"date": day(shortage_day), "balance": 0, "gap": gap} if gap else None
    return {"largest_gap": gap, "first_shortage": first, "expected_outflows": outflows}


def customer(cid, owed, p, overdue=True):
    return {"customer_id": cid, "customer_name": f"C{cid}", "outstanding": owed, "overdue_amount": owed if overdue else 0,
            "p_pay_7d": p, "action": "call", "action_label": "Call today"}


def product(pid, cls, impact, qty_change=-10, needed=0, margin=30.0):
    return {"product_id": pid, "name": f"P{pid}", "product_class": cls, "cash_impact": impact,
            "recommended_qty_change": qty_change, "discount_pct": 10, "days_since_last_sale": 80,
            "days_of_stock": 50, "scale_up_cash_needed": needed, "margin_pct": margin}


LOAN = {"options": [
    {"product_id": 1, "name": "Small", "lender": "L1", "rate": 12, "tenure_months": 12, "recommended_amount": 30_000,
     "monthly_installment": 2_700},
    {"product_id": 2, "name": "Big", "lender": "L2", "rate": 14, "tenure_months": 24, "recommended_amount": 200_000,
     "monthly_installment": 9_600},
]}


def kinds(plan, optional=None):
    return [a["kind"] for a in plan["actions"] if optional is None or a["optional"] == optional]


def test_no_gap_only_collection_is_needed():
    plan = build_plan(TODAY, forecast(), [customer(1, 10_000, 0.8)], {"products": [product(5, "slow", 5_000)]},
                      [], LOAN)
    assert plan["gap"] == 0 and plan["gap_covered"]
    assert kinds(plan, optional=False) == ["collect"]
    assert "financing" not in kinds(plan)


def test_low_risk_actions_cover_the_gap_first():
    plan = build_plan(TODAY, forecast(gap=20_000, bills=[(5, 30_000)], drawings=40_000),
                      [customer(1, 10_000, 0.9)], {"products": [product(5, "dead", 50_000)]}, [], LOAN)
    needed = {a["kind"] for a in plan["actions"] if not a["optional"]}
    # collect 9,000 (low) + drawings cut 20,000 (low) cover 20,000: no medium-risk steps needed
    assert needed == {"collect", "cut_expense"}
    assert {"delay_payable", "clear_stock"} <= set(kinds(plan, optional=True))
    assert plan["expected_from_plan"] >= 20_000 and plan["remaining_gap"] == 0


def test_financing_only_for_what_is_left():
    plan = build_plan(TODAY, forecast(gap=50_000), [customer(1, 10_000, 0.5)], {"products": []}, [], LOAN)
    fin = [a for a in plan["actions"] if a["kind"] == "financing"]
    assert len(fin) == 1 and not fin[0]["optional"]
    assert fin[0]["cash_impact"] == 45_000          # 50,000 gap - 5,000 expected collection
    assert fin[0]["data"]["option"]["name"] == "Big"  # smallest option that covers 45,000
    assert plan["gap_covered"]


def test_financing_without_a_fitting_loan_is_high_risk():
    plan = build_plan(TODAY, forecast(gap=50_000), [], {"products": []}, [], {"options": []})
    fin = plan["actions"][-1]
    assert fin["kind"] == "financing" and fin["risk"] == "high" and fin["cash_impact"] == 50_000


def test_only_bills_before_the_gap_are_delayed():
    plan = build_plan(TODAY, forecast(gap=10_000, shortage_day=9, bills=[(4, 5_000), (20, 8_000)]),
                      [], {"products": []}, [], LOAN)
    delays = [a for a in plan["actions"] if a["kind"] == "delay_payable"]
    assert [a["target_ref"] for a in delays] == ["bill:1"]


def test_scale_up_now_or_later():
    now = build_plan(TODAY, forecast(), [], {"products": [
        product(1, "star", -6_000, qty_change=60, needed=6_000)]}, [], LOAN)
    later = build_plan(TODAY, forecast(gap=5_000), [], {"products": [
        product(1, "star", 0, qty_change=0, needed=6_000)]}, [], LOAN)
    a_now = next(a for a in now["actions"] if a["kind"] == "scale_up")
    a_later = next(a for a in later["actions"] if a["kind"] == "scale_up")
    assert a_now["cash_impact"] == -6_000 and "now" in a_now["title"]
    assert a_later["cash_impact"] == 0 and "6,000 is spare" in a_later["title"]


def test_spending_spike_becomes_a_cut():
    insights = [{"category": "Transport", "direction": "up", "last_30_days": 15_000, "monthly_average": 10_000,
                 "change_pct": 50}]
    plan = build_plan(TODAY, forecast(gap=3_000), [], {"products": []}, insights, LOAN)
    cut = next(a for a in plan["actions"] if a["kind"] == "cut_expense")
    assert cut["cash_impact"] == 5_000 and not cut["optional"]


def test_every_action_is_explained_and_ranked():
    plan = build_plan(TODAY, forecast(gap=80_000, bills=[(3, 10_000)], drawings=20_000),
                      [customer(1, 30_000, 0.6), customer(2, 5_000, 0.2)],
                      {"products": [product(3, "slow", 9_000), product(4, "star", 0, 0, needed=5_000)]}, [], LOAN)
    ranks = [a["rank"] for a in plan["actions"]]
    assert ranks == list(range(1, len(ranks) + 1))
    for a in plan["actions"]:
        assert a["reasoning"] and a["risk"] in ("low", "medium", "high") and a["days_to_impact"] >= 0
    needed = [a["optional"] for a in plan["actions"]]
    assert needed == sorted(needed)  # needed steps come before optional ones


def test_action_plan_api(client, demo_headers):
    plan = client.get("/action-plan", headers=demo_headers).json()
    assert plan["actions"] and plan["gap"] >= 0 and "remaining_gap" in plan
    first = plan["actions"][0]
    done = client.post(f"/actions/{first['id']}/mark-done", headers=demo_headers,
                       json={"actual_amount": 4_000, "note": "Called, paid half"}).json()
    assert done["status"] == "done"
    assert client.post(f"/actions/{first['id']}/mark-done", headers=demo_headers).status_code == 409

    again = client.get("/action-plan", headers=demo_headers).json()  # recomputed: status survives
    same = next(a for a in again["actions"] if a["id"] == first["id"])
    assert same["status"] == "done" and same["actual_amount"] == 4_000
    assert again["realized_so_far"] == 4_000 and again["done_count"] == 1

    second = again["actions"][1]
    assert client.post(f"/actions/{second['id']}/dismiss", headers=demo_headers, json={}).json()["status"] == "dismissed"
    assert client.post(f"/actions/{second['id']}/reopen", headers=demo_headers).json()["status"] == "open"
    log = client.get(f"/actions/{second['id']}/log", headers=demo_headers).json()
    assert [entry["action"] for entry in log] == ["dismissed", "reopened"]
    client.post(f"/actions/{first['id']}/reopen", headers=demo_headers)  # leave demo data as found


def test_action_plan_isolation(client, demo_headers):
    from tests.test_api import signup
    h = signup(client, "planner-other@example.com")
    demo_action = client.get("/action-plan", headers=demo_headers).json()["actions"][0]["id"]
    assert client.post(f"/actions/{demo_action}/mark-done", headers=h).status_code == 404
    empty = client.get("/action-plan", headers=h).json()
    assert empty["gap"] == 0 and all(a["kind"] != "financing" for a in empty["actions"])
