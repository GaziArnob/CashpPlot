"""Reminder delivery: nothing leaves without credentials, the owner confirms every send, failures send nothing."""

import httpx
import pytest

from app import messaging
from app.config import get_settings


class FakeResp:
    def __init__(self, code=200):
        self.status_code = code


@pytest.fixture()
def live(monkeypatch):
    """Pretend every channel has credentials, and record the outgoing calls."""
    s = get_settings()
    for k, v in dict(brevo_api_key="k", brevo_sender_email="me@example.com", whatsapp_token="t",
                     whatsapp_phone_number_id="123", twilio_account_sid="AC1", twilio_auth_token="a",
                     twilio_from="+15550001111").items():
        monkeypatch.setattr(s, k, v)
    class Calls(list):
        code = {"code": 200}

    calls = Calls()

    def fake_post(url, **kw):
        calls.append((url, kw))
        return FakeResp(calls.code["code"])

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def _draft(client, headers):
    customers = client.get("/recovery/priority", headers=headers).json()["customers"]
    inv_id = next(c for c in customers if c["invoices"])["invoices"][0]["invoice_id"]
    return client.post(f"/recovery/reminder/{inv_id}?polish=false", headers=headers).json()


def _customer_contact(client, headers, reminder):
    from app.db import SessionLocal
    from app.models import Customer, Invoice, Reminder
    db = SessionLocal()
    try:
        c = db.get(Invoice, db.get(Reminder, reminder["id"]).invoice_id).customer
        c.email, c.phone = "buyer@example.com", "+1 (415) 555-0123"
        db.commit()
    finally:
        db.close()


def test_not_configured_is_recorded_as_manual_and_sends_nothing(client, demo_headers, monkeypatch):
    s = get_settings()
    for k in ("brevo_api_key", "whatsapp_token", "twilio_account_sid"):
        monkeypatch.setattr(s, k, "")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("a message was sent without credentials"))
    assert client.get("/messaging/channels", headers=demo_headers).json() == {"email": False, "whatsapp": False, "sms": False}
    r = client.post(f"/reminders/{_draft(client, demo_headers)['id']}/send", headers=demo_headers, json={"channel": "email"})
    assert r.status_code == 200 and r.json()["status"] == "sent" and r.json()["delivery"] == "manual"


def test_each_channel_calls_its_provider_with_the_owners_text(client, demo_headers, live):
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    for channel, host in (("email", "api.brevo.com"), ("whatsapp", "graph.facebook.com"), ("sms", "api.twilio.com")):
        r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers,
                        json={"channel": channel, "message": f"Edited by the owner via {channel}"})
        assert r.status_code == 200 and r.json()["delivery"] == "delivered", r.text
        url, kw = live[-1]
        assert host in url
        body = str(kw.get("json") or kw.get("data"))
        assert f"Edited by the owner via {channel}" in body
    sent_to = " ".join(str(kw.get("json") or kw.get("data")) for _, kw in live)
    assert "buyer@example.com" in sent_to and "415555" in sent_to.replace("+1 (415) 555-0123", "415555").replace("14155550123", "415555")


def test_provider_failure_keeps_the_draft(client, demo_headers, live):
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    live.code["code"] = 401
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "sms"})
    assert r.status_code == 502 and "Nothing was sent" in r.json()["detail"]
    assert next(x for x in client.get("/reminders", headers=demo_headers).json() if x["id"] == reminder["id"])["status"] == "draft"


def test_missing_contact_is_a_clear_error_when_the_channel_is_live(client, demo_headers, live):
    reminder = _draft(client, demo_headers)
    from app.db import SessionLocal
    from app.models import Invoice, Reminder
    db = SessionLocal()
    try:
        c = db.get(Invoice, db.get(Reminder, reminder["id"]).invoice_id).customer
        c.email, c.phone = None, None
        db.commit()
    finally:
        db.close()
    assert client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"}).status_code == 422
    assert client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "sms"}).status_code == 422
    assert not live


def test_phone_normalisation():
    assert messaging.normalize_phone("+1 (415) 555-0123") == "+14155550123"
    assert messaging.normalize_phone("0415 555 0123") is None
    assert messaging.normalize_phone(None) is None


def test_whatsapp_uses_the_approved_template_when_one_is_set(client, demo_headers, live, monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_template_name", "payment_reminder")
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp"})
    assert r.status_code == 200 and r.json()["delivery"] == "delivered"
    url, kw = live[-1]
    body = kw["json"]
    assert "graph.facebook.com" in url and body["type"] == "template" and body["to"] == "14155550123"
    assert body["template"]["name"] == "payment_reminder" and body["template"]["language"]["code"] == "en_US"
    params = [p["text"] for p in body["template"]["components"][0]["parameters"]]
    assert len(params) == 4 and "$" in params[2] and params[3].count("-") == 2     # customer, business, amount, due date
    assert all("\n" not in p for p in params)


def test_whatsapp_template_variables_have_no_line_breaks():
    assert messaging._clean("Hello\n\n  there\t  you") == "Hello there you"
