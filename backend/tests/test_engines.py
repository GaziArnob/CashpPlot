from datetime import date, timedelta

from app.ai.tools import Aliaser, ungrounded_numbers
from app.engines import collection, credit, forecast
from app.engines.data import BillRow, BusinessData, Inv, Txn
from app.engines.loan import emi, max_principal

TODAY = date(2026, 10, 17)


def steady_business(days=120, daily_in=10_000, daily_out=8_000, balance=50_000) -> BusinessData:
    d = BusinessData(business_id=1, started_at=TODAY - timedelta(days=1000), opening_balance=balance,
                     cash_threshold=20_000)
    for i in range(days, 0, -1):
        day = TODAY - timedelta(days=i)
        d.transactions.append(Txn(day, daily_in, "income", "Sales"))
        d.transactions.append(Txn(day, daily_out, "expense", "Inventory"))
    return d


def test_emi_and_max_principal_are_inverses():
    m = emi(100_000, 12, 12)
    assert round(m, 2) == 8884.88
    assert round(max_principal(m, 12, 12)) == 100_000
    assert max_principal(0, 12, 12) == 0


def test_forecast_without_events_has_no_shortage():
    d = steady_business()
    fc = forecast.forecast(d, TODAY, 30)
    assert fc["method"] == "holt_winters"
    assert fc["first_shortage"] is None
    # Net +2,000 a day.
    assert abs(fc["series"][-1]["balance"] - (fc["start_balance"] + 30 * 2_000)) < 1_000


def test_forecast_flags_shortage_from_bill():
    d = steady_business()
    start = d.balance_on(TODAY)
    bill = start + 5 * 2_000 - 20_000 + 7_000  # lands 7,000 under the threshold on day 5
    d.bills.append(BillRow(1, 1, "Supplier", bill, TODAY + timedelta(days=5), None))
    fc = forecast.forecast(d, TODAY, 30)
    assert fc["first_shortage"]["date"] == (TODAY + timedelta(days=5)).isoformat()
    assert abs(fc["first_shortage"]["gap"] - 7_000) < 500
    assert fc["drivers"][0]["supplier"] == "Supplier"


def test_overdue_invoices_are_not_counted_as_inflow():
    d = steady_business()
    d.invoices.append(Inv(1, 7, 15_000, TODAY - timedelta(days=25), TODAY - timedelta(days=10), None))
    fc = forecast.forecast(d, TODAY, 7)
    assert fc["overdue_receivables"] == 15_000
    assert fc["expected_inflows"] == []


def test_collection_ranking_and_tone():
    d = steady_business()
    d.customers = {1: "Alpha", 2: "Beta"}
    d.invoices += [
        Inv(1, 1, 20_000, TODAY - timedelta(days=60), TODAY - timedelta(days=45), None),
        Inv(2, 2, 5_000, TODAY - timedelta(days=20), TODAY - timedelta(days=3), None),
    ]
    ranked = collection.score_customers(d, TODAY, shortage_gap=10_000)["customers"]
    assert [r["customer_name"] for r in ranked] == ["Alpha", "Beta"]
    assert ranked[0]["tone"] == "final" and ranked[1]["tone"] == "friendly"
    assert ranked[0]["closes_shortage"] and not ranked[1]["closes_shortage"]


def test_credit_score_bounds_and_explanations():
    d = steady_business(days=400)
    result = credit.score(d, TODAY)
    assert 300 <= result["score"] <= 900
    total = sum(f["weight"] for f in result["factors"])
    assert abs(total - 1.0) < 1e-9
    assert result["band"] in {"Excellent", "Good", "Fair", "Needs improvement"}
    assert result["reasons_positive"] or result["reasons_negative"]


def test_credit_score_drops_with_receivables():
    d = steady_business(days=400)
    base = credit.score(d, TODAY)["score"]
    d.invoices.append(Inv(1, 1, 300_000, TODAY - timedelta(days=60), TODAY - timedelta(days=45), None))
    assert credit.score(d, TODAY)["score"] < base


def test_grounding_check_and_aliases():
    results = [{"gap": 12020, "date": "2026-10-26"}]
    assert ungrounded_numbers("You may be short about 12,000 on Oct 26, 2026.", results) == []
    assert ungrounded_numbers("You may be short 45,000.", results) == ["45,000"]
    a = Aliaser()
    alias = a.customer(3, "Rahim Store")
    assert a.restore(f"Call {alias} first.") == "Call Rahim Store first."
    assert a.restore("Call **Customer C3** first.") == "Call **Rahim Store** first."
    assert a.restore("Customer C99 is unknown.") == "Customer C99 is unknown."
