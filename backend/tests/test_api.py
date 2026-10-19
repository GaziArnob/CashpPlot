from datetime import date, timedelta

from seed.seed import DEMO_EMAIL


def signup(client, email, onboard=True):
    r = client.post("/auth/signup", json={"name": "Test", "email": email, "password": "Passw0rd!x"})
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if onboard:
        r = client.post("/onboarding", headers=h, json={"name": "Test Shop", "started_at": "2024-01-01",
                                                        "opening_balance": 10000, "cash_threshold": 5000})
        assert r.status_code == 201, r.text
    return h


def test_health(client):
    assert client.get("/health").json()["llm_providers"] == ["templates"]


def test_requires_auth(client):
    assert client.get("/dashboard/summary").status_code == 401
    assert client.get("/dashboard/summary", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_dashboard(client, demo_headers, seeded):
    r = client.get("/dashboard/summary", headers=demo_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balance"] == 65_000
    assert body["cash_alert"]["gap"] == seeded["first_shortage"]["gap"]
    assert body["top_collections"][0]["customer_name"] in {"Summit Wholesale", "Harbor Market"}
    assert "credit score" in body["summary"]
    assert body["notifications"]


def test_cashflow_and_calendar(client, demo_headers):
    fc = client.get("/cashflow/forecast?days=30", headers=demo_headers).json()
    assert len(fc["series"]) == 30 and fc["first_shortage"]
    assert any(d.get("supplier") == "Northwind Distributors" for d in fc["drivers"])
    cal = client.get("/cashflow/calendar", headers=demo_headers).json()
    assert cal["days"] and all("projected_balance" in d for d in cal["days"])


def test_recovery_reminder_and_send(client, demo_headers):
    pr = client.get("/recovery/priority", headers=demo_headers).json()
    names = [c["customer_name"] for c in pr["customers"]]
    assert "Harbor Market" in names
    rahim = next(c for c in pr["customers"] if c["customer_name"] == "Harbor Market")
    inv = next(i for i in rahim["invoices"] if i["days_overdue"] == 10)
    r = client.post(f"/recovery/reminder/{inv['invoice_id']}", headers=demo_headers)
    assert r.status_code == 201, r.text
    rem = r.json()
    assert rem["tone"] == "firm" and "Harbor Market" in rem["message"] and rem["status"] == "draft"
    sent = client.post(f"/reminders/{rem['id']}/send", headers=demo_headers, json={"channel": "whatsapp"}).json()
    assert sent["status"] == "sent"


def test_credit_loan_whatif(client, demo_headers):
    c = client.get("/credit-score", headers=demo_headers).json()
    assert 300 <= c["score"] <= 900 and c["factors"]
    assert len(client.get("/credit-score/history", headers=demo_headers).json()) >= 6
    readiness = client.get("/loan/readiness", headers=demo_headers).json()
    assert "not a loan approval" in readiness["disclaimer"]
    recs = client.get("/loan/recommendations", headers=demo_headers).json()
    costs = [o["cost_per_100"] for o in recs["options"]]
    assert costs == sorted(costs)
    w = client.post("/loan/what-if", headers=demo_headers, json={"loan_amount": 100000}).json()
    assert w["scenario"]["min_balance"]["balance"] > w["base"]["min_balance"]["balance"]


def test_agent_fallback_answers(client, demo_headers):
    r = client.post("/agent/chat", headers=demo_headers, json={"message": "Will I run short on cash next week?"})
    body = r.json()
    assert body["provider"] == "templates"
    assert "short by about" in body["answer"]
    r = client.post("/agent/chat", headers=demo_headers, json={"message": "What is my credit score?"})
    assert "credit score is" in r.json()["answer"]
    stream = client.post("/agent/chat/stream", headers=demo_headers, json={"message": "Who owes me money?"})
    assert "event: done" in stream.text
    assert len(client.get("/agent/history", headers=demo_headers).json()) >= 6


def test_reports_and_pdf(client, demo_headers):
    last = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    p = client.get(f"/reports/pnl?month={last}", headers=demo_headers).json()
    assert p["total_income"] > 0 and p["total_expense"] > 0
    insights = client.get("/reports/insights", headers=demo_headers).json()
    assert any(i["category"] == "Transport" and i["direction"] == "up" for i in insights)
    pdf = client.get(f"/reports/export?month={last}", headers=demo_headers)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_tenant_isolation(client, demo_headers):
    demo_invoice = client.get("/invoices", headers=demo_headers).json()[0]["id"]
    other = signup(client, "other@example.com")
    assert client.patch(f"/invoices/{demo_invoice}/paid", headers=other).status_code == 404
    assert client.get("/invoices", headers=other).json() == []
    assert client.get("/customers", headers=other).json() == []


def test_onboarding_required(client):
    h = signup(client, "noshop@example.com", onboard=False)
    assert client.get("/dashboard/summary", headers=h).status_code == 409


def test_transactions_csv_and_invoice_payment(client):
    h = signup(client, "csv@example.com")
    csv_data = "date,amount,type,category,description\n2026-10-01,5000,income,Sales,Cash\n" \
               "02/10/2026,-1200,,Transport,Fuel\nbad,row,,,\n"
    r = client.post("/transactions/import", headers=h, files={"file": ("t.csv", csv_data, "text/csv")})
    assert r.json()["imported"] == 2 and r.json()["errors"]
    items = client.get("/transactions?type=expense", headers=h).json()["items"]
    assert items[0]["amount"] == 1200 and items[0]["category"] == "Transport"

    cust = client.post("/customers", headers=h, json={"name": "Buyer", "phone": "0170"}).json()
    inv = client.post("/invoices", headers=h, json={"customer_id": cust["id"], "amount": 3000,
                                                    "issue_date": "2026-10-01", "due_date": "2026-10-15"}).json()
    paid = client.patch(f"/invoices/{inv['id']}/paid", headers=h).json()
    assert paid["status"] == "paid"
    cats = client.get("/transactions/categories", headers=h).json()
    assert "Invoice payment" in cats["income"]


def test_customer_phone_encrypted_at_rest(client, demo_headers):
    from sqlalchemy import text

    from app.db import engine
    with engine.connect() as conn:
        raw = conn.execute(text("select phone from customers limit 1")).scalar()
    assert raw and not raw.startswith("555")
    profile = client.get("/customers", headers=demo_headers).json()[0]
    assert profile["phone"].startswith("555")


def test_lender_access_flow(client, demo_headers):
    g = client.post("/lender-access", headers=demo_headers,
                    json={"lender_name": "Harbor SME Bank", "scope": ["credit_score"], "days_valid": 7}).json()
    view = client.get("/lender/view", headers={"X-Lender-Token": g["token"]}).json()
    assert "credit_score" in view and "pnl_last_month" not in view
    client.delete(f"/lender-access/{g['id']}", headers=demo_headers)
    assert client.get("/lender/view", headers={"X-Lender-Token": g["token"]}).status_code == 403


def test_login_lockout(client):
    signup(client, "lock@example.com", onboard=False)
    for _ in range(5):
        r = client.post("/auth/login", json={"email": "lock@example.com", "password": "wrong-pass"})
        assert r.status_code == 401
    r = client.post("/auth/login", json={"email": "lock@example.com", "password": "Passw0rd!x"})
    assert r.status_code == 423


def test_refresh_rotation(client):
    signup(client, "refresh@example.com", onboard=False)
    assert client.post("/auth/refresh").status_code == 403  # missing CSRF header
    r1 = client.post("/auth/refresh", headers={"X-Requested-With": "fetch"})
    assert r1.status_code == 200
    old = client.cookies.get("refresh_token")
    r2 = client.post("/auth/refresh", headers={"X-Requested-With": "fetch"})
    assert r2.status_code == 200 and client.cookies.get("refresh_token") != old


def test_rate_limit(client):
    codes = [client.post("/auth/login", json={"email": "x@example.com", "password": "nope"}).status_code
             for _ in range(11)]
    assert codes[-1] == 429


def test_export_and_delete_account(client):
    h = signup(client, "bye@example.com")
    assert client.get("/settings/export", headers=h).json()["business"]["name"] == "Test Shop"
    assert client.delete("/settings/account", headers=h).status_code == 204
    assert client.get("/auth/me", headers=h).status_code == 401


def test_demo_user_still_works(client, demo_headers):
    assert client.get("/auth/me", headers=demo_headers).json()["email"] == DEMO_EMAIL


def test_agent_tool_loop_with_fake_llm(client, demo_headers, monkeypatch):
    """The LLM path: a tool call, pseudonymized data out, real names restored in the answer."""
    import json

    from app.ai import providers
    seen = []

    def fake_chat(messages, tools=None, mode="cloud"):
        seen.append(messages)
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        if not tool_msgs:
            return providers.LLMResult(text=None, provider="fake", tool_calls=[
                {"id": "1", "name": "get_overdue_customers", "arguments": {"limit": 1}}])
        top = json.loads(tool_msgs[-1]["content"])["customers"][0]
        return providers.LLMResult(provider="fake", text=(
            f"Collect from {top['customer']} first: {top['outstanding']:,} outstanding. "
            f"Also 999,999 is made up."))

    monkeypatch.setattr(providers, "chat", fake_chat)
    body = client.post("/agent/chat", headers=demo_headers, json={"message": "Who first?"}).json()
    assert body["provider"] == "fake" and body["tools_used"] == ["get_overdue_customers"]
    tool_payload = [m for m in seen[-1] if m["role"] == "tool"][0]["content"]
    assert "Customer C" in tool_payload and "Hasan" not in tool_payload and "Rahim" not in tool_payload
    assert "Customer C" not in body["answer"]
    assert body["unverified_figures"] == ["999,999"] and not body["grounded"]
