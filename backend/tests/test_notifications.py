"""Notification center: what raises an alert, that it is raised once, muting, read/delete, and urgent email."""

from datetime import date, timedelta

import httpx
import pytest

from app.config import get_settings
from tests.test_api import signup

PASSWORD = "Passw0rd!x"


def iso(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def alerts(client, h, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/notifications?{q}", headers=h).json()["items"]


def trigger(client, h):
    assert client.get("/dashboard/summary", headers=h).status_code == 200


def set_business(email, **fields):
    from app.db import SessionLocal
    from app.models import Business, User
    db = SessionLocal()
    try:
        b = db.query(Business).join(User, User.id == Business.user_id).filter(User.email == email).one()
        for k, v in fields.items():
            setattr(b, k, v)
        db.commit()
        return b.id
    finally:
        db.close()


def seed_situation(client, h):
    """An invoice due in 2 days, a bill due tomorrow, a bill already late, a loan installment due soon."""
    cust = client.post("/customers", headers=h, json={"name": "Due Soon Cafe"}).json()["id"]
    client.post("/invoices", headers=h, json={"customer_id": cust, "amount": 400, "issue_date": iso(-20), "due_date": iso(2)})
    sup = client.post("/suppliers", headers=h, json={"name": "Bean Supplier"}).json()["id"]
    client.post("/bills", headers=h, json={"supplier_id": sup, "amount": 250, "due_date": iso(1)})
    client.post("/bills", headers=h, json={"supplier_id": sup, "amount": 90, "due_date": iso(-3)})
    client.post("/loans", headers=h, json={"lender": "Test Bank", "principal": 3000, "rate": 12, "tenure_months": 6,
                                           "start_date": iso(-28), "installments_paid": 0})


def test_rules_raise_alerts_with_a_link_and_a_severity(client):
    h = signup(client, "notify-rules@example.com")
    seed_situation(client, h)
    set_business("notify-rules@example.com", plan_expires_at=None)
    from app.models import utcnow
    set_business("notify-rules@example.com", plan_expires_at=utcnow() + timedelta(days=2))   # trial ending
    trigger(client, h)
    items = alerts(client, h)
    by_type = {}
    for n in items:
        by_type.setdefault(n["type"], []).append(n)
    assert {"invoice_due", "bill_due", "loan_due", "trial"} <= set(by_type)
    assert "Due Soon Cafe" in by_type["invoice_due"][0]["message"] and by_type["invoice_due"][0]["link"] == "/ledger"
    bills = by_type["bill_due"]
    assert len(bills) == 2 and sorted(b["severity"] for b in bills) == ["critical", "warning"]   # the late one is critical
    assert any("was due" in b["message"] for b in bills) and any("is due" in b["message"] for b in bills)
    assert by_type["loan_due"][0]["link"] == "/loan" and by_type["trial"][0]["link"] == "/settings#plan"
    assert all(n["label"] and n["is_read"] is False for n in items)


def test_the_same_thing_is_raised_only_once(client):
    h = signup(client, "notify-once@example.com")
    seed_situation(client, h)
    trigger(client, h)
    first = len(alerts(client, h))
    assert first >= 3
    trigger(client, h)
    trigger(client, h)
    client.post("/jobs/daily/run", headers=h)
    assert len(alerts(client, h)) == first


def test_it_is_raised_again_after_its_cooldown(client):
    h = signup(client, "notify-cool@example.com")
    seed_situation(client, h)
    trigger(client, h)
    before = len(alerts(client, h, limit=200))
    from app.db import SessionLocal
    from app.models import Notification, utcnow
    db = SessionLocal()
    try:
        for n in db.query(Notification).filter(Notification.type == "bill_due").all():
            if "Bean Supplier" in n.message:
                n.created_at = utcnow() - timedelta(days=10)       # longer ago than the 3-day cooldown
        db.commit()
    finally:
        db.close()
    trigger(client, h)
    assert len(alerts(client, h, limit=200)) > before


def test_muted_types_are_never_created(client):
    h = signup(client, "notify-mute@example.com")
    seed_situation(client, h)
    p = client.put("/notifications/preferences", headers=h, json={"muted": ["invoice_due", "nonsense"], "email": False}).json()
    assert [t["type"] for t in p["types"] if t["muted"]] == ["invoice_due"]
    trigger(client, h)
    types = {n["type"] for n in alerts(client, h)}
    assert "invoice_due" not in types and "bill_due" in types and "loan_due" in types


def test_read_read_all_and_dismiss(client):
    h = signup(client, "notify-read@example.com")
    seed_situation(client, h)
    trigger(client, h)
    s = client.get("/notifications/summary", headers=h).json()
    assert s["unread"] >= 3 and len(s["latest"]) <= 6 and s["latest"][0]["created_at"]
    assert s["total"] == len(alerts(client, h, limit=200)) >= s["unread"]
    first = alerts(client, h)[0]
    assert client.patch(f"/notifications/{first['id']}/read", headers=h).json()["is_read"] is True
    assert client.get("/notifications/summary", headers=h).json()["unread"] == s["unread"] - 1
    assert all(n["is_read"] is False for n in alerts(client, h, unread_only="true"))
    assert client.post("/notifications/read-all", headers=h).json()["marked"] == s["unread"] - 1
    assert client.get("/notifications/summary", headers=h).json()["unread"] == 0
    assert alerts(client, h, unread_only="true") == []
    assert client.delete(f"/notifications/{first['id']}", headers=h).status_code == 204
    assert first["id"] not in [n["id"] for n in alerts(client, h)]
    assert client.delete(f"/notifications/{first['id']}", headers=h).status_code == 404


def test_access_rules(client):
    h = signup(client, "notify-acl@example.com")
    seed_situation(client, h)
    trigger(client, h)
    mine = alerts(client, h)[0]["id"]
    other = signup(client, "notify-acl-other@example.com")
    assert alerts(client, other) == []
    assert client.patch(f"/notifications/{mine}/read", headers=other).status_code == 404
    assert client.delete(f"/notifications/{mine}", headers=other).status_code == 404
    assert client.get("/notifications").status_code == 401
    client.post("/team", headers=h, json={"name": "Sam", "email": "notify-staff@example.com", "password": PASSWORD})
    staff = client.post("/auth/login", json={"email": "notify-staff@example.com", "password": PASSWORD}).json()["access_token"]
    sh = {"Authorization": f"Bearer {staff}"}
    for path in ("/notifications", "/notifications/summary", "/notifications/preferences"):
        assert client.get(path, headers=sh).status_code == 403
    # the free plan still gets its alerts
    set_business("notify-acl-other@example.com", plan="free", plan_expires_at=None)
    assert client.get("/notifications/summary", headers=other).status_code == 200


# Urgent email

class Resp:
    status_code = 200


@pytest.fixture()
def brevo(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "brevo_api_key", "k")
    monkeypatch.setattr(s, "brevo_sender_email", "me@example.com")
    sent = []
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (sent.append(kw["json"]), Resp())[1])
    return sent


def test_critical_alerts_are_emailed_once_when_the_owner_asks(client, brevo):
    h = signup(client, "notify-mail@example.com")
    seed_situation(client, h)
    assert client.get("/notifications/preferences", headers=h).json()["email_available"] is True
    client.post("/jobs/daily/run", headers=h)
    assert brevo == []                                                  # not asked for yet
    client.put("/notifications/preferences", headers=h, json={"muted": [], "email": True})
    client.post("/jobs/daily/run", headers=h)
    assert len(brevo) == 1                                              # the one critical (late) bill
    mail = brevo[0]
    assert mail["to"] == [{"email": "notify-mail@example.com"}] and "Bean Supplier" in mail["textContent"]
    assert "Supplier bills" in mail["subject"]
    client.post("/jobs/daily/run", headers=h)
    assert len(brevo) == 1                                              # never twice


def test_no_email_when_email_is_not_connected(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "brevo_api_key", "")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("an email was sent without credentials"))
    h = signup(client, "notify-nomail@example.com")
    seed_situation(client, h)
    p = client.put("/notifications/preferences", headers=h, json={"muted": [], "email": True}).json()
    assert p["email"] is True and p["email_available"] is False
    client.post("/jobs/daily/run", headers=h)
