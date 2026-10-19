"""Recording an existing loan: schedule, what counts as late, the effect on the forecast, and removal."""

from datetime import date, timedelta

from tests.test_api import signup


def months_ago(n):
    d = date.today().replace(day=1)
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d.isoformat()


def loan(**over):
    return {"lender": "Test Bank", "principal": 12000, "rate": 12, "tenure_months": 12, "start_date": months_ago(4),
            "installments_paid": 4, **over}


def test_paid_installments_are_not_counted_as_late(client):
    h = signup(client, "loan-paid@example.com")
    made = client.post("/loans", headers=h, json=loan()).json()
    row = next(x for x in client.get("/loans", headers=h).json() if x["id"] == made["id"])
    assert row["paid_installments"] == 4 and row["overdue_installments"] == 0 and row["status"] == "active"
    assert row["remaining_to_pay"] == round(made["emi"] * 8, -1) or abs(row["remaining_to_pay"] - made["emi"] * 8) < 10
    sched = client.get(f"/loans/{made['id']}", headers=h).json()["schedule"]
    assert len(sched) == 12 and [s["paid_date"] is not None for s in sched[:5]] == [True] * 4 + [False]
    assert not any(s["overdue"] for s in sched)
    # paid-before installments add no expenses: those payments are already in the owner's own records
    assert client.get("/transactions?category=Loan%20repayment", headers=h).json()["total"] == 0


def test_forgetting_to_say_what_was_paid_shows_late_installments(client):
    h = signup(client, "loan-late@example.com")
    made = client.post("/loans", headers=h, json=loan(installments_paid=0)).json()
    row = next(x for x in client.get("/loans", headers=h).json() if x["id"] == made["id"])
    assert row["overdue_installments"] == 4 and row["next_due"]["due_date"] < date.today().isoformat()


def test_paying_the_next_installment_records_the_expense_and_closes_the_loan(client):
    h = signup(client, "loan-close@example.com")
    made = client.post("/loans", headers=h, json=loan(tenure_months=3, installments_paid=2, start_date=months_ago(2))).json()
    nxt = client.get(f"/loans/{made['id']}", headers=h).json()["next_due"]
    assert client.patch(f"/repayments/{nxt['id']}/paid", headers=h).status_code == 200
    row = client.get(f"/loans/{made['id']}", headers=h).json()
    assert row["status"] == "closed" and row["paid_installments"] == 3 and row["next_due"] is None
    assert client.get("/transactions?category=Loan%20repayment", headers=h).json()["total"] == 1


def test_a_loan_fully_paid_before_today_starts_closed(client):
    h = signup(client, "loan-done@example.com")
    made = client.post("/loans", headers=h, json=loan(tenure_months=3, installments_paid=3, start_date=months_ago(5))).json()
    assert client.get(f"/loans/{made['id']}", headers=h).json()["status"] == "closed"


def test_validation_and_privacy(client):
    h = signup(client, "loan-valid@example.com")
    assert client.post("/loans", headers=h, json=loan(installments_paid=13)).status_code == 422
    assert client.post("/loans", headers=h, json=loan(principal=0)).status_code == 422
    assert client.post("/loans", headers=h, json=loan(rate=150)).status_code == 422
    made = client.post("/loans", headers=h, json=loan()).json()
    other = signup(client, "loan-other@example.com")
    assert client.get(f"/loans/{made['id']}", headers=other).status_code == 404
    assert client.delete(f"/loans/{made['id']}", headers=other).status_code == 404
    assert client.delete(f"/loans/{made['id']}", headers=h).status_code == 204
    assert client.get(f"/loans/{made['id']}", headers=h).status_code == 404


def test_a_new_loan_lowers_the_forecast(client, demo_headers):
    def lowest():
        return client.get("/cashflow/forecast?days=30", headers=demo_headers).json()["min_balance"]["balance"]
    before = lowest()
    made = client.post("/loans", headers=demo_headers, json=loan(principal=60000, installments_paid=0, start_date=months_ago(0))).json()
    try:
        assert lowest() < before                       # its first installment falls inside the 30 days
    finally:
        client.delete(f"/loans/{made['id']}", headers=demo_headers)
    assert lowest() == before
