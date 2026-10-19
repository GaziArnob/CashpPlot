"""The credit score improvement planner: every promised gain must match what the score engine really gives."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from app.engines import credit
from app.engines.credit_plan import plan
from app.engines.data import BillRow, BusinessData, Inv, RepaymentRow, Txn
from tests.test_api import signup

TODAY = date(2026, 10, 20)

PRODUCTS = [{"id": i, "name": n, "min_score": s} for i, (n, s) in enumerate(
    [("Micro", 500), ("Quick", 550), ("Booster", 600), ("Growth", 620), ("Working", 650), ("Term", 700)], 1)]


def business(income=6000, expense=4500, months=9, invoices=(), bills=(), repayments=()):
    txns = []
    for m in range(1, months + 1):
        d = (TODAY.replace(day=1) - timedelta(days=30 * m)).replace(day=15)
        txns += [Txn(d, income, "income", "Sales"), Txn(d, expense, "expense", "Costs")]
    return BusinessData(business_id=1, started_at=date(2024, 6, 1), opening_balance=0, cash_threshold=0,
                        transactions=txns, invoices=list(invoices), customers={1: "Slow Co", 2: "Late Ltd"},
                        bills=list(bills), repayments=list(repayments))


def inv(i, customer, amount, due, paid=None):
    return Inv(i, customer, amount, due - timedelta(days=30), due, paid)


def action(p, key):
    return next(a for a in p["actions"] if a["id"] == key)


def real_score(data):
    return credit.score(data, TODAY)["score"]


def test_collecting_an_overdue_invoice_gives_exactly_what_the_score_would(client):
    late = inv(1, 1, 8000, TODAY - timedelta(days=20))
    d = business(invoices=[late])
    p = plan(d, TODAY, PRODUCTS)
    gain = action(p, "collect:1")["points"]
    paid = business(invoices=[replace(late, paid_date=TODAY)])
    assert real_score(paid) - real_score(d) == gain and gain >= 50


def test_paying_on_time_matches_the_score_with_three_more_on_time_payments():
    d = business()
    p = plan(d, TODAY, PRODUCTS)
    gain = action(p, "on_time")["points"]
    on_time = [BillRow(i, 1, "Sup", 100, TODAY - timedelta(days=10 * i), TODAY - timedelta(days=10 * i + 1)) for i in (1, 2, 3)]
    assert real_score(business(bills=on_time)) - real_score(d) == gain and gain > 0
    assert "no repayment history" in action(p, "on_time")["detail"]


def test_growing_income_matches_the_score_with_twenty_percent_more_income():
    d = business()
    gain = action(plan(d, TODAY, PRODUCTS), "income")["points"]
    assert real_score(business(income=7200)) - real_score(d) == gain and gain >= 1


def test_a_missed_repayment_history_shows_the_count_and_still_helps_to_pay_on_time():
    missed = [BillRow(1, 1, "Sup", 100, TODAY - timedelta(days=40), None), BillRow(2, 1, "Sup", 100, TODAY - timedelta(days=60), TODAY - timedelta(days=61))]
    p = plan(business(bills=missed), TODAY, PRODUCTS)
    assert "1 of 2 paid on time" in action(p, "on_time")["detail"]


def test_actions_are_sorted_biggest_first_and_the_plan_names_the_next_goals():
    d = business(invoices=[inv(1, 1, 8000, TODAY - timedelta(days=20)), inv(2, 2, 3000, TODAY - timedelta(days=45))])
    p = plan(d, TODAY, PRODUCTS)
    pts = [a["points"] for a in p["actions"]]
    assert pts == sorted(pts, reverse=True) and all(x >= 1 for x in pts)
    ids = {a["id"] for a in p["actions"]}
    assert {"collect:1", "collect:all"} <= ids
    assert "collect:2" not in ids        # collecting only the 3,000 still leaves receivables over a month's income: no gain, so not shown
    assert p["next_band"]["points_needed"] == p["next_band"]["score"] - p["score"]
    assert p["next_loan"]["min_score"] > p["score"] and p["next_loan"]["points_needed"] > 0
    ev = p["if_you_do_everything"]
    assert ev["score"] > p["score"] and ev["points"] == ev["score"] - p["score"]
    assert all(p["score"] < next(x["min_score"] for x in PRODUCTS if x["name"] == n) <= ev["score"] for n in ev["unlocks"])


def test_reachability_is_honest():
    d = business()
    low = business(income=2000, expense=2600, months=4)             # losing money: a weak score, so goals exist above it
    for data in (d, low):
        p = plan(data, TODAY, PRODUCTS)
        after = p["if_you_do_everything"]["score"]
        if p["next_band"]:
            assert p["next_band"]["reachable"] == (after >= p["next_band"]["score"])
        if p["next_loan"]:
            assert p["next_loan"]["reachable"] == (after >= p["next_loan"]["min_score"])
    assert plan(low, TODAY, PRODUCTS)["next_loan"] is not None


def test_an_empty_business_is_told_what_data_to_add_instead_of_fake_gains():
    empty = BusinessData(business_id=1, started_at=date(2026, 9, 1), opening_balance=0, cash_threshold=0)
    p = plan(empty, TODAY, PRODUCTS)
    assert p["needs_data"] and "No income is recorded" in p["needs_data"][0]
    assert not any(a["id"] in ("collect:all", "income") for a in p["actions"])


def test_the_top_band_has_no_next_band():
    rich = business(income=400_000, expense=250_000, months=12)
    p = plan(rich, TODAY, PRODUCTS)
    assert p["score"] >= 750 and p["next_band"] is None and p["band"] == "Excellent"


# ---- through the API

def test_api_returns_the_plan_for_the_demo_and_a_new_business(client, demo_headers):
    d = client.get("/credit-score/plan", headers=demo_headers).json()
    assert d["score"] == client.get("/credit-score", headers=demo_headers).json()["score"]
    assert {"actions", "needs_data", "if_you_do_everything", "disclaimer", "next_loan"} <= set(d)
    h = signup(client, "plan-new@example.com")
    n = client.get("/credit-score/plan", headers=h).json()
    assert n["needs_data"] and n["next_loan"]["min_score"] > n["score"]


def test_api_access_rules(client):
    h = signup(client, "plan-acl@example.com")
    assert client.get("/credit-score/plan").status_code == 401
    client.post("/billing/plan", headers=h, json={"plan": "free", "confirm": True})
    assert client.get("/credit-score/plan", headers=h).status_code == 402
    client.post("/team", headers=h, json={"name": "Sam", "email": "plan-staff@example.com", "password": "Passw0rd!x"})
    staff = client.post("/auth/login", json={"email": "plan-staff@example.com", "password": "Passw0rd!x"}).json()["access_token"]
    assert client.get("/credit-score/plan", headers={"Authorization": f"Bearer {staff}"}).status_code == 403
