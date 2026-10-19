"""The credit score for small and new businesses: a fair income scale, honest messages, and what data to add."""

from datetime import date, timedelta

from app.engines.credit import NO_DATA_TEXT, NO_HISTORY_TEXT, TIPS, confidence_for
from tests.test_api import signup


def add_months(client, h, months, income=6000, expense=4500):
    today = date.today()
    for m in range(1, months + 1):
        d = (today.replace(day=1) - timedelta(days=30 * m)).replace(day=15)
        client.post("/transactions", headers=h, json={"date": d.isoformat(), "amount": income, "type": "income", "category": "Sales"})
        client.post("/transactions", headers=h, json={"date": d.isoformat(), "amount": expense, "type": "expense", "category": "Costs"})


def factor(c, key):
    return next(f for f in c["factors"] if f["key"] == key)


def test_a_new_business_gets_a_low_confidence_score_and_a_list_of_what_to_add(client):
    h = signup(client, "credit-new@example.com")
    c = client.get("/credit-score", headers=h).json()
    assert c["confidence"]["level"] == "low"
    text = " ".join(c["confidence"]["missing"])
    assert "No income is recorded" in text and "3 months" in text and "loans and supplier bills" in text
    assert all(f["tip"] == TIPS[f["key"]] for f in c["factors"])
    assert c["reasons_negative"] == [NO_DATA_TEXT] and c["reasons_positive"] == []   # no records: nothing to blame


def test_no_repayment_history_is_not_called_late_payment(client):
    h = signup(client, "credit-nohist@example.com")
    add_months(client, h, 9)
    c = client.get("/credit-score", headers=h).json()
    assert c["inputs"]["obligations_due"] == 0
    assert NO_HISTORY_TEXT in c["reasons_negative"]                  # held at neutral, and said so
    assert not any("Late installments" in r for r in c["reasons_negative"])



def test_a_small_business_earns_credit_for_its_income(client):
    h = signup(client, "credit-small@example.com")
    add_months(client, h, 9)                                          # about 6,300 a month: modest, not zero
    c = client.get("/credit-score", headers=h).json()
    income = factor(c, "income_level")
    assert 0.2 < income["value"] < 0.6 and c["inputs"]["avg_monthly_income"] >= 6000
    assert c["confidence"]["level"] == "high" and 600 <= c["score"] <= 760


def test_more_income_raises_the_score(client):
    small = signup(client, "credit-income-a@example.com")
    big = signup(client, "credit-income-b@example.com")
    add_months(client, small, 6, income=3000, expense=2500)
    add_months(client, big, 6, income=40000, expense=30000)
    a, b = (client.get("/credit-score", headers=h).json() for h in (small, big))
    assert factor(b, "income_level")["value"] > factor(a, "income_level")["value"]
    assert b["score"] > a["score"]


def test_confidence_levels():
    base = {"avg_monthly_income": 5000, "months_used": 12, "obligations_due": 4}
    assert confidence_for(base) == {"level": "high", "months_used": 12, "missing": []}
    assert confidence_for({**base, "months_used": 4})["level"] == "medium"
    assert confidence_for({**base, "months_used": 2})["level"] == "low"
    assert confidence_for({**base, "avg_monthly_income": 0})["level"] == "low"
