"""Supplier negotiation assistant: dated cash flow, late receipts, scheduling, financing costs, safety rules."""

from datetime import date, timedelta

import pytest

from app.ai import negotiation, providers
from app.engines import payables as pe
from app.engines import payables_recommend as pr
from app.engines.data import BillRow, BusinessData, Inv, PaymentRow, Txn

TODAY = date(2026, 10, 17)


def d(n: int) -> date:
    return TODAY + timedelta(days=n)


def shop(balance=100_000, threshold=20_000, days=120, daily_in=10_000, daily_out=9_000) -> BusinessData:
    """A steady business whose cash balance TODAY is `balance` (opening balance is set to make it so)."""
    b = BusinessData(business_id=1, started_at=TODAY - timedelta(days=900),
                     opening_balance=balance - days * (daily_in - daily_out), cash_threshold=threshold)
    for i in range(days, 0, -1):
        day = TODAY - timedelta(days=i)
        b.transactions.append(Txn(day, daily_in, "income", "Sales"))
        b.transactions.append(Txn(day, daily_out, "expense", "Inventory"))
    return b


def paid_invoice(b, inv_id, cid, amount, issue, delay):
    due = issue + timedelta(days=15)
    paid = due + timedelta(days=delay)
    b.invoices.append(Inv(inv_id, cid, amount, issue, due, paid, amount))
    b.payments.append(PaymentRow(inv_id, paid, amount))


def customer_with_delay(b, cid, delay, n=4):
    b.customers[cid] = f"C{cid}"
    for k in range(n):
        paid_invoice(b, 900 + cid * 10 + k, cid, 1_000, TODAY - timedelta(days=200 - 30 * k), delay)


# Dated cash flow

def test_balance_reconciles_with_its_components():
    b = shop()
    b.bills.append(BillRow(1, 1, "Sup", 30_000, d(5), None))
    cf = pe.dated_cashflow(b, TODAY, 30, extra=[(d(3), 5_000, "test")])
    running = cf["start_balance"]
    for r in cf["series"]:
        running += r["estimated_in"] - r["estimated_out"] - r["confirmed_out"] + r["adjustment"]
        assert abs(running - r["balance"]) <= len(cf["series"])  # per-row rounding only
    assert len(cf["series"]) == 30


def test_bill_is_confirmed_and_counted_once():
    b = shop()
    base = pe.dated_cashflow(b, TODAY)
    b.bills.append(BillRow(1, 1, "Sup", 30_000, d(5), None))
    cf = pe.dated_cashflow(b, TODAY)
    row = next(r for r in cf["series"] if r["date"] == d(5).isoformat())
    assert row["confirmed_out"] == 30_000 and sum(r["confirmed_out"] for r in cf["series"]) == 30_000
    assert base["series"][-1]["balance"] - cf["series"][-1]["balance"] == pytest.approx(30_000, abs=2)
    assert [e for e in cf["outflows"] if e["kind"] == "bill"][0]["basis"] == "confirmed"


def test_receivable_counted_once_on_expected_date():
    b = shop()
    customer_with_delay(b, 1, delay=0)
    base = pe.dated_cashflow(b, TODAY)
    b.invoices.append(Inv(1, 1, 10_000, d(-10), d(5), None))
    cf = pe.dated_cashflow(b, TODAY)
    row = next(r for r in cf["series"] if r["date"] == d(5).isoformat())
    assert row["receivables_in"] == 10_000
    assert cf["series"][-1]["balance"] - base["series"][-1]["balance"] == pytest.approx(10_000, abs=2)
    assert cf["receipts"][0]["kind"] == "estimate"


def test_late_receipt_uses_the_customers_usual_delay():
    b = shop()
    customer_with_delay(b, 1, delay=10)
    b.invoices.append(Inv(1, 1, 10_000, d(-10), d(5), None))
    r = pe.expected_receipts(b, TODAY, d(30))[0]
    assert r["expected_date"] == d(15).isoformat() and r["days_late_expected"] == 10
    assert r["weight"] == 1.0 and not r["at_risk"] and "10 days after due" in r["basis"]


def test_invoice_later_than_usual_is_at_risk_and_discounted():
    b = shop()
    customer_with_delay(b, 1, delay=5)
    b.invoices.append(Inv(1, 1, 10_000, d(-40), d(-20), None))  # 20 days overdue, usually 5 late
    r = pe.expected_receipts(b, TODAY, d(30))[0]
    assert r["at_risk"] and r["expected_date"] == d(7).isoformat()
    assert r["weight"] == pe.AT_RISK_WEIGHT and r["counted"] == 6_000


def test_new_customer_gets_a_cautious_estimate():
    b = shop()
    b.customers[7] = "Newbie"
    b.invoices.append(Inv(1, 7, 10_000, d(-5), d(10), None))
    r = pe.expected_receipts(b, TODAY, d(30))[0]
    assert r["expected_date"] == d(10 + pe.NEW_CUSTOMER_DELAY).isoformat()
    assert r["weight"] == pe.NEW_CUSTOMER_WEIGHT and "no payment record" in r["basis"]


def test_partly_paid_invoice_counts_the_remainder_and_paid_ones_not_at_all():
    b = shop()
    customer_with_delay(b, 1, delay=0)
    b.invoices.append(Inv(1, 1, 10_000, d(-10), d(5), None, amount_paid=4_000))
    b.invoices.append(Inv(2, 1, 5_000, d(-10), d(6), d(-1), 5_000))  # fully paid already
    receipts = pe.expected_receipts(b, TODAY, d(30))
    assert [r["invoice_id"] for r in receipts] == [1] and receipts[0]["outstanding"] == 6_000


def test_receipt_after_the_window_is_listed_but_not_counted():
    b = shop()
    customer_with_delay(b, 1, delay=0)
    b.invoices.append(Inv(1, 1, 10_000, d(10), d(45), None))
    cf = pe.dated_cashflow(b, TODAY)
    assert cf["receipts"][0]["in_window"] is False and sum(r["receivables_in"] for r in cf["series"]) == 0


def test_accepted_plan_replaces_the_due_date_payment_without_double_counting():
    b = shop()
    bill = BillRow(1, 1, "Sup", 10_000, d(5), None)
    b.bills.append(bill)
    one = pe.dated_cashflow(b, TODAY)
    bill.schedule, bill.plan_id = [(d(12), 4_000), (d(20), 6_000)], 77
    split = pe.dated_cashflow(b, TODAY)
    assert sum(r["confirmed_out"] for r in one["series"]) == 10_000
    assert sum(r["confirmed_out"] for r in split["series"]) == 10_000          # same total, not 20,000
    assert next(r for r in split["series"] if r["date"] == d(5).isoformat())["confirmed_out"] == 0
    assert next(r for r in split["series"] if r["date"] == d(12).isoformat())["confirmed_out"] == 4_000


def test_partly_paid_bill_only_owes_the_rest():
    b = shop()
    b.bills.append(BillRow(1, 1, "Sup", 10_000, d(5), None, amount_paid=3_000))
    cf = pe.dated_cashflow(b, TODAY)
    assert sum(r["confirmed_out"] for r in cf["series"]) == 7_000


def test_overdue_bill_is_paid_on_the_first_day():
    b = shop()
    b.bills.append(BillRow(1, 1, "Sup", 10_000, d(-4), None))
    cf = pe.dated_cashflow(b, TODAY)
    assert cf["series"][0]["confirmed_out"] == 10_000


# Conflicts

def test_conflict_is_found_and_explained():
    b = shop(balance=40_000)
    b.bills.append(BillRow(1, 1, "Meghna", 60_000, d(6), None))
    cf = pe.dated_cashflow(b, TODAY)
    found = pe.conflicts(cf)
    assert found and found[0]["start"] == d(6).isoformat() and found[0]["worst_gap"] > 0
    assert "Meghna" in found[0]["explanation"] and found[0]["causes"][0]["supplier"] == "Meghna"


def test_no_conflict_when_cash_is_comfortable():
    b = shop(balance=500_000)
    b.bills.append(BillRow(1, 1, "Sup", 10_000, d(6), None))
    assert pe.conflicts(pe.dated_cashflow(b, TODAY)) == []


def test_conflict_explanation_names_money_that_arrives_too_late():
    b = shop(balance=40_000)
    customer_with_delay(b, 1, delay=0)
    b.bills.append(BillRow(1, 1, "Sup", 60_000, d(6), None))
    b.invoices.append(Inv(1, 1, 5_000, d(-10), d(20), None))
    assert "arrives too late" in pe.conflicts(pe.dated_cashflow(b, TODAY))[0]["explanation"]


# Payment plans

def tight_case():
    b = shop(balance=40_000)
    b.bills.append(BillRow(1, 1, "Sup", 60_000, d(6), None))
    return b, pe.dated_cashflow(b, TODAY)


BILL = {"bill_id": 1, "supplier_id": 1, "supplier": "Sup", "outstanding": 60_000, "due_date": d(6).isoformat()}


def test_extension_that_clears_the_tight_window_keeps_cash_safe():
    b, cf = tight_case()
    opts = {o["kind"]: o for o in pe.bill_options(cf, BILL, {"late_fee_pct_month": 1.5})}
    assert not opts["pay_on_time"]["keeps_cash_safe"]
    assert opts["extension"]["min_balance_after"] > opts["pay_on_time"]["min_balance_after"]
    assert opts["extension"]["days_extended"] > 0


def test_every_option_pays_the_whole_bill_in_the_right_order():
    b, cf = tight_case()
    for o in pe.bill_options(cf, BILL, {}):
        assert sum(i["amount"] for i in o["installments"]) == BILL["outstanding"]
        dates = [i["due_date"] for i in o["installments"]]
        assert dates == sorted(dates) and all(x >= d(6).isoformat() for x in dates)


def test_partial_pays_a_rounded_first_part_then_the_rest():
    b, cf = tight_case()
    part = next(o for o in pe.bill_options(cf, BILL, {}) if o["kind"] == "partial")
    first, rest = part["installments"]
    assert 0 < first["amount"] < BILL["outstanding"] and first["amount"] % pe.ROUND_TO == 0
    assert first["amount"] + rest["amount"] == BILL["outstanding"] and rest["due_date"] > first["due_date"]


def test_late_fee_is_prorated_by_days_and_zero_without_terms():
    assert pe._late_fee(10_000, d(0), d(30), 1.5) == 150
    assert pe._late_fee(10_000, d(0), d(15), 2.0) == 100
    assert pe._late_fee(10_000, d(0), d(0), 1.5) == 0 and pe._late_fee(10_000, d(0), d(30), None) == 0


def test_overdue_bill_option_starts_on_day_one():
    b = shop(balance=40_000)
    b.bills.append(BillRow(1, 1, "Sup", 60_000, d(-3), None))
    cf = pe.dated_cashflow(b, TODAY)
    bill = {**BILL, "due_date": d(-3).isoformat()}
    on_time = next(o for o in pe.bill_options(cf, bill, {}) if o["kind"] == "pay_on_time")
    assert on_time["installments"][0]["due_date"] == d(1).isoformat()


# Financing

OFFER = {"id": 1, "provider": "Demo", "name": "Demo offer", "kind": "overdraft", "advance_rate_pct": None,
         "fee_pct": 0.5, "monthly_rate_pct": 1.8, "min_amount": 0, "max_amount": 200_000, "max_days": 60,
         "lead_days": 1, "is_demo": True}


def test_overdraft_cost_is_fee_plus_prorated_interest():
    f = pe.financing_options(TODAY, 10_000, d(7), 30, [OFFER], [])[0]
    assert (f["principal"], f["fees"], f["interest"]) == (10_000, 50, 180)
    assert f["total_repayment"] == 10_230 and f["total_cost"] == 230 and f["cost_per_100"] == 2.3
    assert f["repayments"] == [{"date": d(31).isoformat(), "amount": 10_180, "source": "your cash"}]
    assert f["is_demo"] and "DEMO" in f["label"] and f["meets_deadline"]


def test_term_loan_repayments_add_up_to_the_total():
    loan = {**OFFER, "id": 2, "kind": "short_term_loan", "fee_pct": 1.0, "monthly_rate_pct": 1.2, "max_days": 180,
            "lead_days": 5, "min_amount": 25_000}
    f = pe.financing_options(TODAY, 50_000, d(10), 90, [loan], [])[0]
    assert f["principal"] == 50_000 and len(f["repayments"]) == 3 and f["fees"] == 500
    assert sum(r["amount"] for r in f["repayments"]) + f["fees"] == pytest.approx(f["total_repayment"], abs=3)
    assert f["interest"] > 0 and f["total_cost"] == f["fees"] + f["interest"]


def test_invoice_financing_cost_is_worked_out_per_invoice():
    offer = {**OFFER, "id": 3, "kind": "invoice_financing", "advance_rate_pct": 80.0, "fee_pct": 1.0,
             "monthly_rate_pct": 1.5, "lead_days": 2, "min_amount": 5_000}
    receipts = [{"invoice_id": 9, "customer": "Lima", "outstanding": 10_000, "expected_date": d(22).isoformat(),
                 "at_risk": False, "in_window": True}]
    f = pe.financing_options(TODAY, 8_000, d(10), 30, [offer], receipts)[0]
    # advance 8,000 on day 2; paid back on day 22 = 20 days: interest 8,000 x 1.5% x 20/30 = 80; fee 1% of 10,000 = 100
    assert (f["principal"], f["fees"], f["interest"]) == (8_000, 100, 80)
    assert f["total_repayment"] == 8_180 and f["repayments"][0]["amount"] == 8_180
    assert f["repayments"][0]["date"] == d(22).isoformat() and f["covers_need"]


def test_invoice_financing_skips_risky_tiny_and_already_due_invoices():
    offer = {**OFFER, "id": 3, "kind": "invoice_financing", "advance_rate_pct": 80.0, "fee_pct": 1.0,
             "monthly_rate_pct": 1.5, "lead_days": 2, "min_amount": 5_000}
    base = {"customer": "X", "in_window": True, "at_risk": False, "expected_date": d(20).isoformat()}
    receipts = [{**base, "invoice_id": 1, "outstanding": 10_000, "at_risk": True},
                {**base, "invoice_id": 2, "outstanding": 1_000},
                {**base, "invoice_id": 3, "outstanding": 10_000, "expected_date": d(1).isoformat()}]
    assert pe.financing_options(TODAY, 5_000, d(10), 30, [offer], receipts) == []


def test_offer_that_arrives_after_the_deadline_is_flagged():
    slow = {**OFFER, "lead_days": 9}
    f = pe.financing_options(TODAY, 10_000, d(5), 30, [slow], [])[0]
    assert f["meets_deadline"] is False


def test_sizing_scales_cost_with_the_amount():
    f = pe.financing_options(TODAY, 100_000, d(7), 30, [OFFER], [])[0]
    small = pr.size_financing(f, 20_000)
    assert small["principal"] == 20_000 and small["total_cost"] == pytest.approx(f["total_cost"] * 0.2, abs=2)
    assert small["repayments"][0]["amount"] < f["repayments"][0]["amount"]
    floor = pr.size_financing(f, 1_000)  # never below the product's minimum
    assert floor["principal"] == max(1_000, OFFER["min_amount"])


# Recommendation

def synthetic_cf(balances: dict[int, float], threshold=20_000, days=30):
    series = [{"date": d(k).isoformat(), "balance": balances.get(k, 60_000), "below_threshold":
               balances.get(k, 60_000) < threshold} for k in range(1, days + 1)]
    return {"as_of": TODAY.isoformat(), "start_balance": 60_000, "threshold": threshold, "series": series,
            "outflows": [], "receipts": []}


def financing(name, funds_day, repay_day, principal=20_000, repay=20_600):
    return {"offer_id": hash(name) % 1000, "provider": "Demo", "name": name, "kind": name, "principal": principal,
            "fees": 300, "interest": 300, "total_cost": 600, "total_repayment": repay, "meets_deadline": True,
            "funds_available": d(funds_day).isoformat(), "repayments": [{"date": d(repay_day).isoformat(),
                                                                         "amount": repay, "source": "x"}],
            "risk": "medium", "effective_annual_rate_pct": 36.0, "repaid_from": "your cash",
            "label": "DEMO", "is_demo": True, "min_amount": 0, "max_amount": 1e6, "days": 20}


def test_financing_repaid_before_the_dip_gets_no_credit():
    cf = synthetic_cf({k: 5_000 for k in range(10, 15)})            # dip on days 10-14 only
    early = financing("early_repay", funds_day=2, repay_day=5)      # repaid before the dip: useless, costs 600
    late = financing("late_repay", funds_day=2, repay_day=20)       # still held through the dip
    assert pr.path_with(cf, pr.step_effects({"type": "financing", "financing": early}, cf))["min_balance"] == 4_400  # worse by its cost
    assert pr.path_with(cf, pr.step_effects({"type": "financing", "financing": late}, cf))["min_balance"] >= 20_000
    rec = pr.recommend(cf, [], [early, late], {}, [], TODAY)
    assert [s["name"] for s in rec["steps"]] == ["late_repay"]
    assert rec["lowest_balance_after"] >= 20_000 and rec["remaining_gap"] == 0
    assert next(a for a in rec["alternatives"] if a["name"] == "early_repay")["why_not"] == \
        "does not raise the lowest balance"


def test_supplier_change_comes_before_debt_when_it_is_enough():
    cf = synthetic_cf({k: 5_000 for k in range(10, 15)})
    cf["outflows"] = [{"date": d(10).isoformat(), "kind": "bill", "bill_id": 1, "supplier": "Sup", "amount": 30_000}]
    plan = {"kind": "extension", "bill_id": 1, "reasoning": "Move it.", "estimated_fee": 100, "fee_basis": "terms",
            "installments": [{"due_date": d(20).isoformat(), "amount": 30_000}], "min_balance_after": 35_000,
            "days_below_after": 0, "keeps_cash_safe": True, "days_extended": 10}
    on_time = {**plan, "kind": "pay_on_time", "installments": [{"due_date": d(10).isoformat(), "amount": 30_000}]}
    bills = [{"bill_id": 1, "supplier_id": 1, "supplier": "Sup", "outstanding": 30_000, "due_date": d(10).isoformat()}]
    rec = pr.recommend(cf, [[on_time, plan]], [financing("overdraft", 1, 20)], {1: {"on_time_rate": 0.9}}, bills, TODAY)
    assert [s["type"] for s in rec["steps"]] == ["supplier_plan"] and rec["total_cost"] == 100
    assert "on time 90%" in rec["steps"][0]["why"] and rec["steps"][0]["needs_agreement"] is True


def test_no_conflict_means_no_steps():
    rec = pr.recommend(synthetic_cf({}), [], [], {}, [], TODAY)
    assert rec["steps"] == [] and rec["remaining_gap"] == 0 and "No payment conflict" in rec["headline"]


def test_unfixable_gap_is_reported_honestly():
    cf = synthetic_cf({k: -50_000 for k in range(10, 20)})
    rec = pr.recommend(cf, [], [financing("small", 1, 25, principal=5_000, repay=5_100)], {}, [], TODAY)
    assert rec["remaining_gap"] > 0 and "still be short" in rec["headline"] or not rec["steps"]


# Negotiation messages

FIELDS = dict(supplier="Meghna", business="Evergreen Traders", currency="USD", amount=39_200, due_date="2026-10-27",
              on_time_rate=0.92)


def test_template_includes_the_exact_figures():
    inst = [{"due_date": "2026-10-27", "amount": 9_500}, {"due_date": "2026-11-26", "amount": 29_700}]
    en = negotiation.template("partial", installments=inst, **FIELDS)
    assert "$9,500" in en and "$29,700" in en and "Nov 26, 2026" in en and "92%" in en and "$39,200" in en


def test_history_line_only_when_the_record_is_good():
    one = [{"due_date": "2026-11-26", "amount": 39_200}]
    assert "on time" not in negotiation.template("extension", installments=one, **{**FIELDS, "on_time_rate": 0.4})
    assert "on time" not in negotiation.template("extension", installments=one, **{**FIELDS, "on_time_rate": None})


def masked(text: str) -> str:
    return text.replace(FIELDS["supplier"], "[SUPPLIER]").replace(FIELDS["business"], "[BUSINESS]")


def test_rewrite_with_changed_figures_is_rejected(monkeypatch):
    one = [{"due_date": "2026-11-26", "amount": 39_200}]
    base = negotiation.template("extension", installments=one, **FIELDS)
    monkeypatch.setattr(providers, "chat", lambda m, tools=None, mode="cloud": providers.LLMResult(
        text=masked(base).replace("39,200", "93,200"), provider="fake"))
    text, by = negotiation.generate("extension", installments=one, **FIELDS)
    assert by == "template" and text == base and "93,200" not in text


def test_rewrite_that_loses_the_placeholders_is_rejected(monkeypatch):
    one = [{"due_date": "2026-11-26", "amount": 39_200}]
    base = negotiation.template("extension", installments=one, **FIELDS)
    monkeypatch.setattr(providers, "chat", lambda m, tools=None, mode="cloud": providers.LLMResult(
        text="Hi there, can we pay $39,200 on Nov 26, 2026 instead? Thanks.", provider="fake"))
    assert negotiation.generate("extension", installments=one, **FIELDS) == (base, "template")


def test_good_rewrite_is_kept_and_real_names_are_put_back(monkeypatch):
    one = [{"due_date": "2026-11-26", "amount": 39_200}]
    monkeypatch.setattr(providers, "chat", lambda m, tools=None, mode="cloud": providers.LLMResult(
        text=masked(negotiation.template("extension", installments=one, **FIELDS)).replace(
            "I hope you are well.", "Hope you're doing well."), provider="fake"))
    text, by = negotiation.generate("extension", installments=one, **FIELDS)
    assert by == "fake" and "Hope you're doing well." in text
    assert FIELDS["supplier"] in text and FIELDS["business"] in text and "[SUPPLIER]" not in text


def test_the_llm_never_sees_the_real_names(monkeypatch):
    seen = []

    def spy(messages, tools=None, mode="cloud"):
        seen.append(" ".join(m["content"] for m in messages))
        raise providers.NoLLMAvailable("spy")
    monkeypatch.setattr(providers, "chat", spy)
    negotiation.generate("extension", installments=[{"due_date": "2026-11-26", "amount": 39_200}], **FIELDS)
    assert seen and FIELDS["supplier"] not in seen[0] and FIELDS["business"] not in seen[0]
    assert "[SUPPLIER]" in seen[0] and "[BUSINESS]" in seen[0]


def test_no_llm_uses_the_template(monkeypatch):
    def none(m, tools=None, mode="cloud"):
        raise providers.NoLLMAvailable("none")
    monkeypatch.setattr(providers, "chat", none)
    assert negotiation.generate("extension", installments=[{"due_date": "2026-11-26", "amount": 39_200}],
                                **FIELDS)[1] == "template"


# API

def make_business(client, email):
    """A small business with no history: balance 10,000, safety level 5,000, one 8,000 bill due in 5 days."""
    from tests.test_api import signup
    h = signup(client, email)
    today = date.today()
    sup = client.post("/suppliers", headers=h, json={"name": "Test Supplier", "phone": "0171"}).json()
    bill = client.post("/bills", headers=h, json={"supplier_id": sup["id"], "amount": 8_000,
                                                  "due_date": (today + timedelta(days=5)).isoformat()}).json()
    return h, sup, bill


def plan_body(bill, parts, kind="partial"):
    today = date.today()
    return {"bill_id": bill["id"], "kind": kind, "installments": [
        {"due_date": (today + timedelta(days=n)).isoformat(), "amount": a} for n, a in parts]}


def test_requires_auth(client):
    for path in ("/payables/analysis", "/payment-plans", "/negotiation-drafts", "/financing/compare?amount=1000"):
        assert client.get(path).status_code == 401


def test_analysis_on_the_demo_business(client, demo_headers):
    r = client.get("/payables/analysis", headers=demo_headers).json()
    assert len(r["cashflow"]["series"]) == 30 and r["conflicts"] and r["upcoming_bills"]
    assert r["recommendation"]["steps"] and r["recommendation"]["lowest_balance_after"] >= r["cashflow"]["threshold"]
    assert all(f["is_demo"] and "DEMO" in f["label"] for f in r["financing"])
    assert all(f["total_repayment"] == f["principal"] + f["fees"] + f["interest"] for f in r["financing"])
    assert "never" in r["disclaimer"].lower() or "without your approval" in r["disclaimer"]
    assert all(rec["basis"] == "confirmed" for rec in r["cashflow"]["outflows"])
    assert all(x["kind"] == "estimate" for x in r["cashflow"]["receipts"])


def test_recommendation_history(client, demo_headers):
    before = len(client.get("/payables/recommendations", headers=demo_headers).json())
    run = client.post("/payables/recommendations", headers=demo_headers).json()
    history = client.get("/payables/recommendations", headers=demo_headers).json()
    assert len(history) == before + 1 and history[0]["id"] == run["id"] and history[0]["steps"]
    detail = client.get(f"/payables/recommendations/{run['id']}", headers=demo_headers).json()
    assert detail["recommendation"]["headline"] == history[0]["headline"]


def test_financing_compare_endpoint(client, demo_headers):
    r = client.get("/financing/compare?amount=30000&needed_by_days=10&duration_days=30", headers=demo_headers).json()
    assert r["options"] and "never applies" in r["disclaimer"]
    for o in r["options"]:
        assert o["total_cost"] == o["fees"] + o["interest"] and o["repayments"]
    assert client.get("/financing/compare?amount=0", headers=demo_headers).status_code == 422


def test_plan_validation(client):
    h, sup, bill = make_business(client, "plan-validation@example.com")
    ok = plan_body(bill, [(5, 3_000), (20, 5_000)])
    assert client.post("/payment-plans", headers=h, json={**ok, "installments": ok["installments"][:1]}).status_code == 422  # sum
    assert client.post("/payment-plans", headers=h, json=plan_body(bill, [(-2, 8_000)])).status_code == 422               # past
    assert client.post("/payment-plans", headers=h, json=plan_body(bill, [(5, 4_000), (5, 4_000)])).status_code == 422    # same day
    assert client.post("/payment-plans", headers=h, json=plan_body(bill, [(900, 8_000)])).status_code == 422              # too far
    assert client.post("/payment-plans", headers=h, json={**ok, "bill_id": 999999}).status_code == 404
    assert client.post("/payment-plans", headers=h, json=ok).status_code == 201


def test_full_plan_flow_with_explicit_approvals(client):
    h, sup, bill = make_business(client, "plan-flow@example.com")
    before = client.get("/payables/analysis", headers=h).json()
    assert before["conflicts"]
    plan = client.post("/payment-plans", headers=h, json=plan_body(bill, [(5, 3_000), (25, 5_000)])).json()
    assert plan["status"] == "draft" and plan["affects_forecast"] is False

    during = client.get("/payables/analysis", headers=h).json()                        # a draft changes nothing
    assert during["cashflow"]["series"] == before["cashflow"]["series"]

    assert client.post(f"/payment-plans/{plan['id']}/approve", headers=h, json={}).status_code == 422  # needs confirm
    assert client.post(f"/payment-plans/{plan['id']}/supplier-response", headers=h,
                       json={"accepted": True, "confirm": True}).status_code == 409                    # not approved yet
    approved = client.post(f"/payment-plans/{plan['id']}/approve", headers=h, json={"confirm": True}).json()
    assert approved["status"] == "approved" and approved["affects_forecast"] is False
    assert client.get("/payables/analysis", headers=h).json()["cashflow"]["series"] == before["cashflow"]["series"]

    edited = client.put(f"/payment-plans/{plan['id']}", headers=h,
                        json={"installments": plan_body(bill, [(5, 2_000), (25, 6_000)])["installments"]}).json()
    assert edited["status"] == "draft" and edited["installments"][0]["amount"] == 2_000   # edit undoes approval
    client.post(f"/payment-plans/{plan['id']}/approve", headers=h, json={"confirm": True})

    accepted = client.post(f"/payment-plans/{plan['id']}/supplier-response", headers=h,
                           json={"accepted": True, "note": "Agreed by phone", "confirm": True}).json()
    assert accepted["status"] == "accepted" and accepted["affects_forecast"] is True

    after = client.get("/payables/analysis", headers=h).json()
    outflow = [e for e in after["cashflow"]["outflows"] if e["kind"] == "bill"]
    assert sorted(e["amount"] for e in outflow) == [2_000, 6_000] and sum(e["amount"] for e in outflow) == 8_000
    assert after["cashflow"]["series"] != before["cashflow"]["series"]
    assert not after["bill_options"]                                           # the bill is rescheduled already

    second = client.post("/payment-plans", headers=h, json=plan_body(bill, [(5, 8_000)])).json()
    client.post(f"/payment-plans/{second['id']}/approve", headers=h, json={"confirm": True})
    assert client.post(f"/payment-plans/{second['id']}/supplier-response", headers=h,
                       json={"accepted": True, "confirm": True}).status_code == 409   # one accepted plan per bill

    first = accepted["installments"][0]
    assert client.post(f"/payment-plans/installments/{first['id']}/paid", headers=h, json={}).status_code == 422
    paid = client.post(f"/payment-plans/installments/{first['id']}/paid", headers=h, json={"confirm": True}).json()
    assert paid["paid_so_far"] == 2_000 and paid["remaining"] == 6_000 and paid["status"] == "accepted"
    assert client.post(f"/payment-plans/installments/{first['id']}/paid", headers=h,
                       json={"confirm": True}).status_code == 409
    bills = client.get("/bills", headers=h).json()
    assert bills[0]["status"] == "partial" and bills[0]["amount_paid"] == 2_000
    expenses = client.get("/transactions?type=expense", headers=h).json()["items"]
    assert [e["amount"] for e in expenses if e["category"] == "Bill payment"] == [2_000]

    last = accepted["installments"][1]
    done = client.post(f"/payment-plans/installments/{last['id']}/paid", headers=h, json={"confirm": True}).json()
    assert done["status"] == "completed"
    assert client.get("/bills", headers=h).json()[0]["status"] == "paid"
    assert client.post(f"/payment-plans/{plan['id']}/cancel", headers=h).status_code == 409


def test_rejected_plan_leaves_the_forecast_alone(client):
    h, sup, bill = make_business(client, "plan-rejected@example.com")
    before = client.get("/payables/analysis", headers=h).json()["cashflow"]["series"]
    plan = client.post("/payment-plans", headers=h, json=plan_body(bill, [(30, 8_000)], "extension")).json()
    client.post(f"/payment-plans/{plan['id']}/approve", headers=h, json={"confirm": True})
    res = client.post(f"/payment-plans/{plan['id']}/supplier-response", headers=h,
                      json={"accepted": False, "note": "No", "confirm": True}).json()
    assert res["status"] == "rejected"
    assert client.get("/payables/analysis", headers=h).json()["cashflow"]["series"] == before
    assert client.put(f"/payment-plans/{plan['id']}", headers=h,
                      json={"installments": plan_body(bill, [(30, 8_000)])["installments"]}).status_code == 409


def test_paying_the_bill_normally_after_a_partial_installment(client):
    h, sup, bill = make_business(client, "plan-pay-rest@example.com")
    plan = client.post("/payment-plans", headers=h, json=plan_body(bill, [(5, 3_000), (25, 5_000)])).json()
    client.post(f"/payment-plans/{plan['id']}/approve", headers=h, json={"confirm": True})
    client.post(f"/payment-plans/{plan['id']}/supplier-response", headers=h, json={"accepted": True, "confirm": True})
    client.post(f"/payment-plans/installments/{plan['installments'][0]['id']}/paid", headers=h, json={"confirm": True})
    paid = client.patch(f"/bills/{bill['id']}/paid", headers=h).json()
    assert paid["status"] == "paid" and paid["amount_paid"] == 8_000
    spent = sum(e["amount"] for e in client.get("/transactions?type=expense", headers=h).json()["items"]
                if e["category"] == "Bill payment")
    assert spent == 8_000                                                         # 3,000 + the 5,000 left, not 11,000


def test_drafts_are_editable_and_never_sent(client):
    h, sup, bill = make_business(client, "drafts@example.com")
    plan = client.post("/payment-plans", headers=h, json=plan_body(bill, [(5, 3_000), (25, 5_000)])).json()
    en = client.post("/negotiation-drafts", headers=h, json={"bill_id": bill["id"], "plan_id": plan["id"]}).json()
    assert "Test Supplier" in en["message"] and "$3,000" in en["message"] and en["status"] == "draft"
    assert en["generated_by"] == "template"
    assert en["sent_by_app"] is False and "never sends" in en["note"]
    edited = client.put(f"/negotiation-drafts/{en['id']}", headers=h, json={"message": "Salam, my own words."}).json()
    assert edited["message"] == "Salam, my own words." and edited["status"] == "draft"
    assert client.post(f"/negotiation-drafts/{en['id']}/mark-sent", headers=h, json={}).status_code == 422
    sent = client.post(f"/negotiation-drafts/{en['id']}/mark-sent", headers=h, json={"confirm": True}).json()
    assert sent["status"] == "marked_sent" and sent["sent_by_app"] is False
    assert len(client.get("/negotiation-drafts", headers=h).json()) == 1
    assert client.delete(f"/negotiation-drafts/{en['id']}", headers=h).status_code == 204
    other_bill = client.post("/bills", headers=h, json={"supplier_id": sup["id"], "amount": 100,
                                                        "due_date": date.today().isoformat()}).json()
    assert client.post("/negotiation-drafts", headers=h, json={"bill_id": other_bill["id"],
                                                               "plan_id": plan["id"]}).status_code == 422


def test_tenant_isolation(client, demo_headers):
    h, sup, bill = make_business(client, "iso-owner@example.com")
    plan = client.post("/payment-plans", headers=h, json=plan_body(bill, [(5, 8_000)], "extension")).json()
    draft = client.post("/negotiation-drafts", headers=h, json={"bill_id": bill["id"]}).json()
    run = client.post("/payables/recommendations", headers=h).json()
    from tests.test_api import signup
    other = signup(client, "iso-other@example.com")
    assert client.get(f"/payment-plans/{plan['id']}", headers=other).status_code == 404
    assert client.post(f"/payment-plans/{plan['id']}/approve", headers=other, json={"confirm": True}).status_code == 404
    assert client.put(f"/negotiation-drafts/{draft['id']}", headers=other, json={"message": "x"}).status_code == 404
    assert client.get(f"/payables/recommendations/{run['id']}", headers=other).status_code == 404
    assert client.post("/payment-plans", headers=other, json=plan_body(bill, [(5, 8_000)])).status_code == 404
    assert client.post("/negotiation-drafts", headers=other, json={"bill_id": bill["id"]}).status_code == 404
    assert client.get("/payment-plans", headers=other).json() == []
    demo_bill = client.get("/payables/analysis", headers=demo_headers).json()["upcoming_bills"][0]["bill_id"]
    assert client.post("/payment-plans", headers=h, json=plan_body({"id": demo_bill}, [(5, 1_000)])).status_code == 404


def test_empty_business_has_nothing_to_report(client):
    from tests.test_api import signup
    h = signup(client, "payables-empty@example.com")
    r = client.get("/payables/analysis", headers=h).json()
    assert r["conflicts"] == [] and r["upcoming_bills"] == [] and r["financing"] == []
    assert r["recommendation"]["steps"] == [] and "No payment conflict" in r["recommendation"]["headline"]
