"""Each alert rule: what triggers it, what does not, and the message and link."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app import alert_rules as rules
from app.engines.data import Txn
from tests.test_api import signup
from tests.test_notifications import alerts, iso, set_business, trigger


def kinds(client, h):
    return {n["type"] for n in alerts(client, h, limit=200)}


def of_type(client, h, kind):
    return [n for n in alerts(client, h, limit=200) if n["type"] == kind]


def db_run(email, fn):
    from app.db import SessionLocal
    from app.models import Business, User
    db = SessionLocal()
    try:
        b = db.query(Business).join(User, User.id == Business.user_id).filter(User.email == email).one()
        out = fn(db, b)
        db.commit()
        return out
    finally:
        db.close()


# ---- cash

def test_cash_already_below_the_safety_level(client):
    h = signup(client, "rule-cashlow@example.com")                    # balance 10000, safety level 5000
    trigger(client, h)
    assert "cash_low" not in kinds(client, h)
    set_business("rule-cashlow@example.com", cash_threshold=20000)
    trigger(client, h)
    n = of_type(client, h, "cash_low")[0]
    assert n["severity"] == "critical" and n["link"] == "/cashflow" and "already below" in n["message"]


# ---- invoices

def test_late_invoices_are_alerted_one_to_thirty_days_and_not_beyond(client):
    h = signup(client, "rule-late@example.com")
    cust = client.post("/customers", headers=h, json={"name": "Slow Payer"}).json()["id"]
    for due, amount in ((-10, 300), (-45, 900)):
        client.post("/invoices", headers=h, json={"customer_id": cust, "amount": amount, "issue_date": iso(due - 20), "due_date": iso(due)})
    trigger(client, h)
    late = of_type(client, h, "invoice_late")
    assert len(late) == 1 and "10 days late" in late[0]["message"] and "Slow Payer" in late[0]["message"]
    assert "overdue" in kinds(client, h)                              # the 45-day one is the customer-level alert


def test_at_most_ten_late_invoice_alerts_per_check(client):
    h = signup(client, "rule-latecap@example.com")
    cust = client.post("/customers", headers=h, json={"name": "Many"}).json()["id"]
    for i in range(14):
        client.post("/invoices", headers=h, json={"customer_id": cust, "amount": 100 + i, "issue_date": iso(-40), "due_date": iso(-5)})
    trigger(client, h)
    assert len(of_type(client, h, "invoice_late")) == rules.LATE_INVOICE_LIMIT


# ---- supplier plan

def test_an_accepted_plan_payment_alerts_but_a_draft_does_not(client):
    h = signup(client, "rule-plan@example.com")
    sup = client.post("/suppliers", headers=h, json={"name": "Plan Supplier"}).json()["id"]
    bill = client.post("/bills", headers=h, json={"supplier_id": sup, "amount": 500, "due_date": iso(30)}).json()["id"]

    def add(status, due):
        from app.models import PaymentPlan, PaymentPlanInstallment

        def fn(db, b):
            plan = PaymentPlan(business_id=b.id, bill_id=bill, kind="custom", status=status)
            db.add(plan)
            db.flush()
            db.add(PaymentPlanInstallment(business_id=b.id, plan_id=plan.id, due_date=due, amount=250))
        db_run("rule-plan@example.com", fn)

    add("draft", date.today() + timedelta(days=1))
    trigger(client, h)
    assert of_type(client, h, "plan_due") == []
    add("accepted", date.today() - timedelta(days=1))                  # an agreed date already missed
    trigger(client, h)
    n = of_type(client, h, "plan_due")[0]
    assert n["severity"] == "critical" and "Plan Supplier" in n["message"] and n["link"] == "/payables"


# ---- stock

def test_low_and_out_of_stock_alerts_only_for_products_that_sell(client):
    h = signup(client, "rule-stock@example.com")

    def product(name, stock, sold):
        pid = client.post("/products", headers=h, json={"name": name, "unit_cost": 2, "unit_price": 5, "stock_qty": stock}).json()["id"]
        for k, qty in enumerate(sold):
            client.post("/sale-items", headers=h, json={"product_id": pid, "date": iso(-3 - k * 7), "qty": qty})
        return pid

    product("Fast Seller", 100, [45, 45])        # 10 left, ~3 a day: about 3 days
    product("Sold Out", 40, [20, 20])            # none left
    product("Plenty", 500, [10])                 # years of stock
    product("Never Sells", 3, [])                # not selling, so no alert
    trigger(client, h)
    msgs = {n["message"]: n for n in of_type(client, h, "low_stock")}
    assert any("Fast Seller will run out" in m for m in msgs) and any("Sold Out is out of stock" in m for m in msgs)
    assert not any("Plenty" in m or "Never Sells" in m for m in msgs)
    assert next(n for m, n in msgs.items() if "Sold Out" in m)["severity"] == "critical"


def test_stock_alerts_need_the_pro_plan(client):
    h = signup(client, "rule-stock-free@example.com")
    pid = client.post("/products", headers=h, json={"name": "Free Plan Item", "unit_cost": 2, "unit_price": 5, "stock_qty": 10}).json()["id"]
    client.post("/sale-items", headers=h, json={"product_id": pid, "date": iso(-2), "qty": 10})
    set_business("rule-stock-free@example.com", plan="free", plan_expires_at=None)
    trigger(client, h)
    assert "low_stock" not in kinds(client, h)


# ---- credit score

def test_a_credit_score_drop_of_twenty_points_or_more(client):
    h = signup(client, "rule-credit@example.com")

    def snapshots(db, b):
        from app.models import CreditScore, utcnow
        db.add(CreditScore(business_id=b.id, score=700, band="Good", factors={}, calculated_at=utcnow() - timedelta(days=3)))
        db.add(CreditScore(business_id=b.id, score=690, band="Good", factors={}, calculated_at=utcnow() - timedelta(days=2)))
    db_run("rule-credit@example.com", snapshots)
    c = SimpleNamespace(today=date.today())
    db_run("rule-credit@example.com", lambda db, b: rules.credit_score_drop(db, b, c))
    assert of_type(client, h, "credit_drop") == []                    # a 10-point dip is normal

    def lower(db, b):
        from app.models import CreditScore, utcnow
        db.add(CreditScore(business_id=b.id, score=655, band="Fair", factors={}, calculated_at=utcnow() - timedelta(days=1)))
    db_run("rule-credit@example.com", lower)
    db_run("rule-credit@example.com", lambda db, b: rules.credit_score_drop(db, b, c))
    n = of_type(client, h, "credit_drop")[0]
    assert "fell from 690 to 655" in n["message"] and n["link"] == "/credit-score"


# ---- spending and sales (date-independent: the rule is given a fixed "today")

TODAY = date(2026, 10, 20)


def ctx(transactions):
    return SimpleNamespace(today=TODAY, data=SimpleNamespace(transactions=transactions), fc={}, ranked=[])


def months(kind, amounts, category="Supplies"):
    """One transaction on the 5th of each of the three months before October 2026."""
    return [Txn(date(2026, m, 5), a, kind, category) for m, a in zip((7, 8, 9), amounts)]


def raised(email, kind):
    return of_type_db(email, kind)


def of_type_db(email, kind):
    from app.models import Notification
    return db_run(email, lambda db, b: [n.message for n in db.query(Notification).filter(
        Notification.business_id == b.id, Notification.type == kind).all()])


def test_spending_running_well_above_the_usual_pace(client):
    signup(client, "rule-spend@example.com")
    usual = months("expense", [3000, 3000, 3000])
    this_month = [Txn(date(2026, 10, 8), 4200, "expense", "Supplies")]    # usual pace by the 20th is 3000 x 20/31 = 1935
    db_run("rule-spend@example.com", lambda db, b: rules.spending_spike(db, b, ctx(usual + this_month)))
    msg = raised("rule-spend@example.com", "spending_spike")[0]
    assert "above your usual pace" in msg and "117%" in msg


def test_normal_spending_owner_drawings_and_early_month_raise_nothing(client):
    signup(client, "rule-spend-ok@example.com")
    usual = months("expense", [3000, 3000, 3000])
    ok = [Txn(date(2026, 10, 8), 2200, "expense", "Supplies")]
    drawings = [Txn(date(2026, 10, 9), 9000, "expense", "Owner drawings")]
    db_run("rule-spend-ok@example.com", lambda db, b: rules.spending_spike(db, b, ctx(usual + ok + drawings)))
    early = SimpleNamespace(today=date(2026, 10, 4), data=SimpleNamespace(transactions=usual + [Txn(date(2026, 10, 2), 9000, "expense", "x")]))
    db_run("rule-spend-ok@example.com", lambda db, b: rules.spending_spike(db, b, early))
    short_history = [Txn(date(2026, 9, 5), 100, "expense", "x"), Txn(date(2026, 10, 8), 9000, "expense", "x")]
    db_run("rule-spend-ok@example.com", lambda db, b: rules.spending_spike(db, b, ctx(short_history)))
    assert raised("rule-spend-ok@example.com", "spending_spike") == []


def test_sales_falling_below_sixty_percent_of_the_period_before(client):
    signup(client, "rule-sales@example.com")
    prior = [Txn(TODAY - timedelta(days=20), 4000, "income", "Sales")]        # days 15-28 ago
    recent = [Txn(TODAY - timedelta(days=3), 1500, "income", "Sales")]       # last 14 days
    db_run("rule-sales@example.com", lambda db, b: rules.sales_drop(db, b, ctx(prior + recent)))
    msg = raised("rule-sales@example.com", "sales_drop")[0]
    assert "62% lower" in msg and "$1,500" in msg and "$4,000" in msg


def test_steady_sales_and_a_young_business_raise_nothing(client):
    signup(client, "rule-sales-ok@example.com")
    steady = [Txn(TODAY - timedelta(days=20), 4000, "income", "Sales"), Txn(TODAY - timedelta(days=3), 3000, "income", "Sales")]
    db_run("rule-sales-ok@example.com", lambda db, b: rules.sales_drop(db, b, ctx(steady)))
    fresh = [Txn(TODAY - timedelta(days=20), 4000, "income", "Sales"), Txn(TODAY - timedelta(days=3), 100, "income", "Sales")]
    set_business("rule-sales-ok@example.com", started_at=TODAY - timedelta(days=10))       # under 28 days old
    db_run("rule-sales-ok@example.com", lambda db, b: rules.sales_drop(db, b, ctx(fresh)))
    assert raised("rule-sales-ok@example.com", "sales_drop") == []


# ---- follow-ups

def test_follow_up_alerts_for_referrals_goals_and_bank(client):
    h = signup(client, "rule-follow@example.com")

    def setup(db, b):
        from app.models import BankConnection, Goal, LenderReferral, utcnow
        db.add(LenderReferral(business_id=b.id, lender_name="Sample SME Bank", product_name="SME Term Loan", requested_amount=9000,
                              score_snapshot=700, band_snapshot="Good", shared_fields=["credit_score"], status="submitted",
                              created_at=utcnow() - timedelta(days=20), updated_at=utcnow() - timedelta(days=20)))
        db.add(LenderReferral(business_id=b.id, lender_name="Fresh Bank", product_name="Fresh", requested_amount=1000,
                              score_snapshot=700, band_snapshot="Good", shared_fields=["credit_score"], status="submitted"))
        db.add(LenderReferral(business_id=b.id, lender_name="Done Bank", product_name="Done", requested_amount=1000,
                              score_snapshot=700, band_snapshot="Good", shared_fields=["credit_score"], status="funded",
                              updated_at=utcnow() - timedelta(days=60)))
        db.add(Goal(business_id=b.id, title="New oven", target_amount=5000, current_amount=1200, deadline=date.today() + timedelta(days=6)))
        db.add(Goal(business_id=b.id, title="Reached goal", target_amount=500, current_amount=500, deadline=date.today() + timedelta(days=6)))
        db.add(Goal(business_id=b.id, title="Far away", target_amount=500, current_amount=1, deadline=date.today() + timedelta(days=90)))
        db.add(BankConnection(business_id=b.id, institution_name="Stale Bank", item_id="i1", access_token="t",
                              created_at=utcnow() - timedelta(days=10)))
        db.add(BankConnection(business_id=b.id, institution_name="Synced Bank", item_id="i2", access_token="t",
                              created_at=utcnow() - timedelta(days=10), last_synced_at=utcnow() - timedelta(days=1)))
    db_run("rule-follow@example.com", setup)
    trigger(client, h)
    ref, goal, bank = (of_type(client, h, k) for k in ("referral", "goal", "bank"))
    assert len(ref) == 1 and "SME Term Loan" in ref[0]["message"] and "20 days" in ref[0]["message"]
    assert len(goal) == 1 and "New oven" in goal[0]["message"] and "$1,200 of $5,000" in goal[0]["message"]
    assert len(bank) == 1 and "Stale Bank" in bank[0]["message"] and bank[0]["link"] == "/transactions"


# ---- robustness

def test_a_failing_rule_does_not_stop_the_others(client, monkeypatch):
    h = signup(client, "rule-robust@example.com")
    set_business("rule-robust@example.com", cash_threshold=50000)

    def boom(db, business, c):
        raise RuntimeError("broken rule")
    monkeypatch.setattr(rules, "RULES", [boom] + [r for r in rules.RULES if r.__name__ != "boom"])
    trigger(client, h)                                                  # the page still loads
    assert "cash_low" in kinds(client, h)                               # and the other rules still ran


def test_every_rule_type_has_a_label_for_the_settings_page(client, demo_headers):
    from app import notify
    prefs = client.get("/notifications/preferences", headers=demo_headers).json()["types"]
    assert {t["type"] for t in prefs} == set(notify.TYPES) and len(prefs) >= 14
