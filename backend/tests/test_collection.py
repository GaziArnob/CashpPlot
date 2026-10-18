"""Collection scoring: buckets, history without look-ahead, probability model, actions, credit limits."""

import re
from datetime import date, timedelta

import pytest

from app.ai.templates import reminder
from app.engines import collection as col
from app.engines.data import BusinessData, Inv, PaymentRow

TODAY = date(2026, 10, 17)


def business() -> BusinessData:
    return BusinessData(business_id=1, started_at=TODAY - timedelta(days=900), opening_balance=0, cash_threshold=0)


def add_paid(d: BusinessData, inv_id: int, cid: int, amount: float, issue: date, delay: int, parts: int = 1):
    """A fully paid invoice (15-day terms) paid `delay` days after its due date, in `parts` payments."""
    due = issue + timedelta(days=15)
    paid = due + timedelta(days=delay)
    d.invoices.append(Inv(inv_id, cid, amount, issue, due, paid, amount))
    for k in range(parts):
        d.payments.append(PaymentRow(inv_id, paid - timedelta(days=(parts - 1 - k) * 5), amount / parts))


@pytest.mark.parametrize("days,bucket", [(-5, "current"), (0, "current"), (1, "0-30"), (30, "0-30"),
                                         (31, "31-60"), (60, "31-60"), (61, "61-90"), (90, "61-90"), (91, "90+")])
def test_aging_buckets(days, bucket):
    assert col.aging_bucket(days) == bucket


def test_history_ignores_later_payments():
    d = business()
    add_paid(d, 1, 7, 1_000, TODAY - timedelta(days=60), delay=-2)   # paid on time, 47 days ago
    add_paid(d, 2, 7, 1_000, TODAY - timedelta(days=30), delay=10)   # paid late, 5 days ago
    early = col.history(d, 7, TODAY - timedelta(days=20))
    now = col.history(d, 7, TODAY)
    assert early.paid_invoices == 1 and early.on_time_rate == 1.0
    assert now.paid_invoices == 2 and now.on_time_rate == 0.5


def test_partial_rate():
    d = business()
    add_paid(d, 1, 7, 1_000, TODAY - timedelta(days=90), delay=0, parts=2)
    add_paid(d, 2, 7, 1_000, TODAY - timedelta(days=60), delay=0)
    assert col.history(d, 7, TODAY).partial_rate == 0.5


def test_rule_probability_shape():
    new = col.History(0, None, None, 0.0)
    good = col.History(10, 1.0, -1, 0.0)
    due_soon = Inv(1, 1, 1_000, TODAY - timedelta(days=10), TODAY + timedelta(days=3), None)
    overdue_10 = Inv(2, 1, 1_000, TODAY - timedelta(days=25), TODAY - timedelta(days=10), None)
    overdue_80 = Inv(3, 1, 1_000, TODAY - timedelta(days=95), TODAY - timedelta(days=80), None)
    far = Inv(4, 1, 1_000, TODAY, TODAY + timedelta(days=30), None)
    assert col.rule_probability(due_soon, good, TODAY) > col.rule_probability(due_soon, new, TODAY)
    assert col.rule_probability(overdue_10, good, TODAY) > col.rule_probability(overdue_80, good, TODAY)
    assert col.rule_probability(far, good, TODAY) < 0.2
    partial = col.History(5, 0.5, 5, 0.6)
    plain = col.History(5, 0.5, 5, 0.0)
    assert col.rule_probability(overdue_10, partial, TODAY) > col.rule_probability(overdue_10, plain, TODAY)


def test_model_falls_back_to_rules_with_little_data():
    d = business()
    add_paid(d, 1, 7, 1_000, TODAY - timedelta(days=90), delay=0)
    m = col.PayModel(d, TODAY)
    assert m.method == "rules" and m.samples < col.MIN_TRAINING_SAMPLES


def test_model_trains_and_learns_who_pays():
    d = business()
    k = 0
    for cid, delay in ((1, -3), (2, 40)):  # customer 1 always early, customer 2 always very late
        for w in range(30):
            k += 1
            add_paid(d, k, cid, 2_000, TODAY - timedelta(days=400 - 12 * w), delay=delay)
    m = col.PayModel(d, TODAY)
    assert m.method == "logistic_regression"
    reliable, late = col.history(d, 1, TODAY), col.history(d, 2, TODAY)
    inv = Inv(999, 1, 2_000, TODAY - timedelta(days=12), TODAY + timedelta(days=3), None)
    assert m.predict(inv, 2_000, reliable, TODAY) > m.predict(inv, 2_000, late, TODAY)


@pytest.mark.parametrize("bucket,p,top,expected,softened", [
    ("90+", 0.5, False, "stop_credit", False),
    ("31-60", 0.1, False, "stop_credit", False),      # unlikely to pay: stop credit even if not that old
    ("61-90", 0.5, False, "visit", False),
    ("31-60", 0.5, False, "call", False),
    ("0-30", 0.45, False, "discount", False),         # mid probability on a big balance
    ("0-30", 0.8, False, "send_reminder", False),
    ("90+", 0.5, True, "visit", True),                # top customer: one step gentler
    ("61-90", 0.5, True, "call", True),
])
def test_recommended_actions(bucket, p, top, expected, softened):
    action, soft = col.recommend_action(bucket, p, outstanding=50_000, big_balance=20_000, due_soon=False,
                                        top_customer=top)
    assert (action, soft) == (expected, softened)


def test_not_due_actions():
    assert col.recommend_action("current", 0.5, 1_000, 20_000, due_soon=True, top_customer=False)[0] == "send_reminder"
    assert col.recommend_action("current", 0.5, 1_000, 20_000, due_soon=False, top_customer=False)[0] == "wait"


def test_credit_limits():
    d = business()
    for w in range(6):  # reliable: always on time, ~10k a month
        add_paid(d, 100 + w, 1, 5_000, TODAY - timedelta(days=80 - 14 * w), delay=-1)
    for w in range(6):  # unreliable: always late, same volume
        add_paid(d, 200 + w, 2, 5_000, TODAY - timedelta(days=80 - 14 * w), delay=20)
    good = col.credit_limit(d, 1, col.history(d, 1, TODAY), 0, TODAY)
    bad = col.credit_limit(d, 2, col.history(d, 2, TODAY), 10, TODAY)
    assert good["amount"] > bad["amount"] > 0 and good["amount"] % 500 == 0
    assert col.credit_limit(d, 2, col.history(d, 2, TODAY), 95, TODAY)["amount"] == 0
    assert col.credit_limit(d, 3, col.History(0, None, None, 0.0), 0, TODAY)["amount"] == col.NEW_CUSTOMER_LIMIT


def test_score_customers_edge_cases():
    d = business()
    assert col.score_customers(d, TODAY)["customers"] == []  # no invoices at all
    d.customers = {1: "Known", 2: "Brand New"}
    add_paid(d, 1, 1, 3_000, TODAY - timedelta(days=60), delay=0)
    d.invoices.append(Inv(2, 1, 8_000, TODAY - timedelta(days=50), TODAY - timedelta(days=35), None))
    d.invoices.append(Inv(3, 2, 4_000, TODAY - timedelta(days=2), TODAY + timedelta(days=13), None))
    rows = col.score_customers(d, TODAY, shortage_gap=5_000)["customers"]
    by = {r["customer_name"]: r for r in rows}
    assert set(by) == {"Known", "Brand New"}
    assert all(0 <= r["score"] <= 100 for r in rows)
    assert by["Known"]["rank"] == 1 and by["Known"]["closes_shortage"] and by["Known"]["aging_bucket"] == "31-60"
    assert by["Brand New"]["new_customer"] and by["Brand New"]["action"] == "wait"
    assert by["Brand New"]["credit_limit"] == col.NEW_CUSTOMER_LIMIT


def test_partially_paid_invoice_scores_on_the_remainder():
    d = business()
    d.customers = {1: "Part"}
    d.invoices.append(Inv(1, 1, 10_000, TODAY - timedelta(days=30), TODAY - timedelta(days=15), None, 6_000))
    row = col.score_customers(d, TODAY)["customers"][0]
    assert row["outstanding"] == 4_000 and row["invoices"][0]["original_amount"] == 10_000


def test_bangla_reminder_formatting():
    text = reminder("discount", customer="Rahim Store", business="Karim Traders", amount=15_000, currency="BDT",
                    due_date="2026-10-07", days=10, lang="bn", discount_deadline="2026-10-20")
    assert "১৫,০০০ টাকা" in text and "১৪,৭০০ টাকা" in text and "অক্টোবর" in text and "২%" in text
    assert not re.search(r"[0-9]", text)  # every figure in Bangla digits
    en = reminder("final", customer="Rahim Store", business="Karim Traders", amount=15_000, currency="BDT",
                  due_date="2026-10-07", days=10, lang="en")
    assert "BDT 15,000" in en and "10 days overdue" in en


def test_collections_api(client, demo_headers):
    from app.db import SessionLocal
    from app.models import CollectionScore
    r = client.get("/collections/priority", headers=demo_headers).json()
    assert r["customers"] and r["model"]["method"] in ("logistic_regression", "rules")
    assert r["expected_in_7_days"] <= r["total_outstanding"]
    scores = [c["score"] for c in r["customers"]]
    assert scores == sorted(scores, reverse=True)
    db = SessionLocal()
    try:
        assert db.query(CollectionScore).count() == len(r["customers"])  # today's snapshot, no duplicates
        client.get("/collections/priority", headers=demo_headers)
        assert db.query(CollectionScore).count() == len(r["customers"])
    finally:
        db.close()

    rahim = next(c for c in r["customers"] if c["customer_name"] == "Rahim Store")
    bn = client.post(f"/collections/{rahim['customer_id']}/reminder?lang=bn", headers=demo_headers).json()
    assert "Rahim Store" in bn["message"] and "টাকা" in bn["message"] and bn["status"] == "draft"
    assert bn["generated_by"] == "template:bn"
    en = client.post(f"/collections/{rahim['customer_id']}/reminder?lang=en&polish=false",
                     headers=demo_headers).json()
    assert f"BDT {rahim['outstanding']:,}" in en["message"]

    applied = client.post(f"/customers/{rahim['customer_id']}/credit-limit", headers=demo_headers, json={}).json()
    assert applied["credit_limit"] == rahim["credit_limit"]
    assert client.get(f"/collections/{rahim['customer_id']}/history", headers=demo_headers).json()


def test_collections_api_isolation_and_empty(client, demo_headers):
    from tests.test_api import signup
    h = signup(client, "collect-empty@example.com")
    assert client.get("/collections/priority", headers=h).json()["customers"] == []
    cust = client.post("/customers", headers=h, json={"name": "Owes Nothing"}).json()
    assert client.post(f"/collections/{cust['id']}/reminder", headers=h).status_code == 409
    demo_customer = client.get("/collections/priority", headers=demo_headers).json()["customers"][0]["customer_id"]
    assert client.post(f"/collections/{demo_customer}/reminder", headers=h).status_code == 404
