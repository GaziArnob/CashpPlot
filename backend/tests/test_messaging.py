"""Reminder delivery: nothing leaves without credentials, the owner confirms every send, failures send nothing."""

import httpx
import pytest

from app import messaging
from app.config import get_settings


class FakeResp:
    body = None

    def __init__(self, code=200):
        self.status_code = code

    def json(self):
        if FakeResp.body is None:
            raise ValueError("no body")
        return FakeResp.body


@pytest.fixture()
def live(monkeypatch):
    """Pretend every channel has credentials, and record the outgoing calls."""
    s = get_settings()
    for k, v in dict(brevo_api_key="k", brevo_sender_email="me@example.com", whatsapp_token="t",
                     whatsapp_phone_number_id="123", twilio_account_sid="AC1", twilio_auth_token="a").items():
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
    for k in ("brevo_api_key", "whatsapp_token", "twilio_account_sid", "twilio_whatsapp_from", "mailjet_api_key", "smtp_host"):
        monkeypatch.setattr(s, k, "")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("a message was sent without credentials"))
    assert client.get("/messaging/channels", headers=demo_headers).json() == {"email": False, "whatsapp": False}
    r = client.post(f"/reminders/{_draft(client, demo_headers)['id']}/send", headers=demo_headers, json={"channel": "email"})
    assert r.status_code == 200 and r.json()["status"] == "sent" and r.json()["delivery"] == "manual"


def test_each_channel_calls_its_provider_with_the_owners_text(client, demo_headers, live):
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    for channel, host in (("email", "api.brevo.com"), ("whatsapp", "graph.facebook.com")):
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
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp"})
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
    assert client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp"}).status_code == 422
    assert not live
    assert client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "sms"}).status_code == 422   # no longer a channel


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


# Email through plain SMTP (a free Gmail mailbox works)

class FakeSMTP:
    sent = []
    mode = "ok"
    kind = "smtp"

    def __init__(self, host, port, timeout=None, context=None):
        if FakeSMTP.mode == "blocked":
            raise OSError(101, "Network is unreachable")      # what a host that blocks SMTP ports looks like
        self.log = {"kind": type(self).kind, "host": host, "port": port, "starttls": False}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.log["starttls"] = True

    def login(self, user, password):
        import smtplib
        if FakeSMTP.mode == "auth":
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        self.log["user"] = user

    def send_message(self, msg):
        import smtplib
        if FakeSMTP.mode == "down":
            raise smtplib.SMTPException("server unavailable")
        FakeSMTP.sent.append({**self.log, "to": msg["To"], "from": msg["From"], "subject": msg["Subject"],
                              "body": msg.get_content()})


class FakeSMTPSSL(FakeSMTP):
    kind = "ssl"


@pytest.fixture()
def gmail(monkeypatch):
    import smtplib
    s = get_settings()
    for k, v in dict(brevo_api_key="", smtp_host="smtp.gmail.com", smtp_port=587, smtp_user="owner@gmail.com",
                     smtp_password="app-password", smtp_from="").items():
        monkeypatch.setattr(s, k, v)
    FakeSMTP.sent, FakeSMTP.mode = [], "ok"
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("Brevo must not be used when only SMTP is set"))
    return FakeSMTP


def test_smtp_alone_turns_email_on_and_sends_the_owners_text(client, demo_headers, gmail):
    assert client.get("/messaging/channels", headers=demo_headers).json()["email"] is True
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers,
                    json={"channel": "email", "message": "Please pay when you can.\nThanks"})
    assert r.status_code == 200 and r.json()["delivery"] == "delivered"
    mail = gmail.sent[-1]
    assert mail["kind"] == "smtp" and mail["host"] == "smtp.gmail.com" and mail["starttls"] and mail["user"] == "owner@gmail.com"
    assert mail["to"] == "buyer@example.com" and "owner@gmail.com" in mail["from"]
    assert mail["body"].startswith("Please pay when you can.") and "Payment reminder from" in mail["subject"]


def test_smtp_on_port_465_uses_ssl_from_the_start(client, demo_headers, gmail, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_port", 465)
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    assert client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"}).status_code == 200
    assert gmail.sent[-1]["kind"] == "ssl" and gmail.sent[-1]["starttls"] is False


def test_smtp_failures_keep_the_draft_and_say_why(client, demo_headers, gmail):
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    gmail.mode = "auth"
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"})
    assert r.status_code == 502 and "username or password" in r.json()["detail"]
    gmail.mode = "down"
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"})
    assert r.status_code == 502 and "Nothing was sent" in r.json()["detail"]
    assert next(x for x in client.get("/reminders", headers=demo_headers).json() if x["id"] == reminder["id"])["status"] == "draft"
    assert gmail.sent == []


def test_brevo_wins_when_both_are_set(client, demo_headers, live, monkeypatch):
    import smtplib
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(s, "smtp_user", "owner@gmail.com")
    monkeypatch.setattr(s, "smtp_password", "x")
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail("SMTP used although Brevo is set"))
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    assert client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"}).status_code == 200
    assert "api.brevo.com" in live[-1][0]


def test_incomplete_smtp_settings_do_not_enable_email(client, demo_headers, monkeypatch):
    s = get_settings()
    for k, v in dict(brevo_api_key="", smtp_host="smtp.gmail.com", smtp_user="owner@gmail.com", smtp_password="").items():
        monkeypatch.setattr(s, k, v)
    assert client.get("/messaging/channels", headers=demo_headers).json()["email"] is False


def test_the_email_subject_cannot_carry_extra_headers():
    import smtplib
    FakeSMTP.sent, FakeSMTP.mode = [], "ok"
    s = get_settings()
    saved = (s.smtp_host, s.smtp_user, s.smtp_password, s.brevo_api_key, smtplib.SMTP)
    s.smtp_host, s.smtp_user, s.smtp_password, s.brevo_api_key = "h", "u@example.com", "p", ""
    smtplib.SMTP = FakeSMTP
    try:
        messaging.send("email", to_email="a@example.com", to_phone=None, subject="Hi\r\nBcc: evil@example.com", text="x")
    finally:
        s.smtp_host, s.smtp_user, s.smtp_password, s.brevo_api_key, smtplib.SMTP = saved
    assert FakeSMTP.sent[-1]["subject"] == "Hi Bcc: evil@example.com"


def test_a_host_that_blocks_smtp_gets_a_message_that_says_so(client, demo_headers, gmail):
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    gmail.mode = "blocked"
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"})
    detail = r.json()["detail"]
    assert r.status_code == 502 and "block SMTP" in detail and "Brevo or Mailjet" in detail and "Nothing was sent" in detail


# Mailjet (email over HTTPS, works on hosts that block SMTP)

@pytest.fixture()
def mailjet(monkeypatch):
    s = get_settings()
    for k, v in dict(brevo_api_key="", smtp_host="", mailjet_api_key="mj-key", mailjet_secret_key="mj-secret",
                     mailjet_sender_email="me@example.com").items():
        monkeypatch.setattr(s, k, v)
    class Calls(list):
        code = {"code": 200}

    calls = Calls()
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (calls.append((url, kw)), FakeResp(calls.code["code"]))[1])
    return calls


def test_mailjet_alone_turns_email_on_and_sends_over_https(client, demo_headers, mailjet):
    assert client.get("/messaging/channels", headers=demo_headers).json()["email"] is True
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers,
                    json={"channel": "email", "message": "Edited by the owner"})
    assert r.status_code == 200 and r.json()["delivery"] == "delivered"
    url, kw = mailjet[-1]
    msg = kw["json"]["Messages"][0]
    assert url == "https://api.mailjet.com/v3.1/send" and kw["auth"] == ("mj-key", "mj-secret")
    assert msg["From"]["Email"] == "me@example.com" and msg["To"] == [{"Email": "buyer@example.com"}]
    assert msg["TextPart"] == "Edited by the owner" and "Payment reminder from" in msg["Subject"]


def test_mailjet_rejection_keeps_the_draft(client, demo_headers, mailjet):
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    mailjet.code["code"] = 401
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"})
    assert r.status_code == 502 and "Mailjet rejected" in r.json()["detail"] and "Nothing was sent" in r.json()["detail"]


def test_incomplete_mailjet_settings_do_not_enable_email(client, demo_headers, monkeypatch):
    s = get_settings()
    for k, v in dict(brevo_api_key="", smtp_host="", mailjet_api_key="k", mailjet_secret_key="", mailjet_sender_email="a@b.co").items():
        monkeypatch.setattr(s, k, v)
    assert client.get("/messaging/channels", headers=demo_headers).json()["email"] is False


def test_provider_order_is_brevo_then_mailjet_then_smtp(client, demo_headers, mailjet, monkeypatch):
    import smtplib
    s = get_settings()
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail("SMTP used although an HTTPS provider is set"))
    monkeypatch.setattr(s, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(s, "smtp_user", "o@gmail.com")
    monkeypatch.setattr(s, "smtp_password", "x")
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"})
    assert "api.mailjet.com" in mailjet[-1][0]
    monkeypatch.setattr(s, "brevo_api_key", "b")
    monkeypatch.setattr(s, "brevo_sender_email", "b@example.com")
    client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"})
    assert "api.brevo.com" in mailjet[-1][0]


def test_mailjet_answering_200_with_an_error_status_is_not_reported_as_sent(client, demo_headers, mailjet):
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    FakeResp.body = {"Messages": [{"Status": "error", "Errors": [{"ErrorMessage": "Sender not validated: me@example.com"}]}]}
    try:
        r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"})
        assert r.status_code == 502 and "Sender not validated" in r.json()["detail"] and "Nothing was sent" in r.json()["detail"]
        assert next(x for x in client.get("/reminders", headers=demo_headers).json() if x["id"] == reminder["id"])["status"] == "draft"
        FakeResp.body = {"Messages": [{"Status": "success", "To": [{"Email": "buyer@example.com", "MessageID": 123456789}]}]}
        ok = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "email"}).json()
        assert ok["delivery"] == "delivered" and "123456789" in ok["delivery_note"]
    finally:
        FakeResp.body = None


def test_the_providers_own_reason_is_shown_when_it_refuses(client, demo_headers, twilio_only, monkeypatch):
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    twilio_only.code["code"] = 400
    FakeResp.body = {"code": 63016, "message": "The number +14155550123 has not joined the sandbox. Ask them to send the join phrase."}
    try:
        detail = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp"}).json()["detail"]
        assert "Twilio rejected the message (400)" in detail and "join" in detail and "Nothing was sent" in detail
        FakeResp.body = None                                                                        # no body: just the code
        detail = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp"}).json()["detail"]
        assert detail.startswith("Twilio rejected the message (400). Nothing")
        s = get_settings()
        monkeypatch.setattr(s, "whatsapp_token", "t")                                              # Meta's own WhatsApp
        monkeypatch.setattr(s, "whatsapp_phone_number_id", "999")
        FakeResp.body = {"error": {"message": "Recipient phone number not in allowed list"}}      # Meta's shape
        detail = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp"}).json()["detail"]
        assert "WhatsApp rejected the message (400)" in detail and "not in allowed list" in detail
    finally:
        FakeResp.body = None


# WhatsApp through Twilio

@pytest.fixture()
def twilio_only(monkeypatch):
    s = get_settings()
    for k, v in dict(whatsapp_token="", whatsapp_phone_number_id="", twilio_account_sid="AC1", twilio_auth_token="tok",
                     twilio_whatsapp_from="whatsapp:+14155238886").items():
        monkeypatch.setattr(s, k, v)

    class Calls(list):
        code = {"code": 201}

    calls = Calls()
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (calls.append((url, kw)), FakeResp(calls.code["code"]))[1])
    return calls


def test_twilio_sends_whatsapp_with_the_whatsapp_prefix(client, demo_headers, twilio_only):
    assert client.get("/messaging/channels", headers=demo_headers).json() == {"email": False, "whatsapp": True}
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    r = client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp", "message": "hi by whatsapp"})
    assert r.status_code == 200 and r.json()["delivery"] == "delivered", r.text
    url, kw = twilio_only[-1]
    assert "api.twilio.com" in url
    assert kw["data"] == {"To": "whatsapp:+14155550123", "From": "whatsapp:+14155238886", "Body": "hi by whatsapp"}
    assert "sandbox" in r.json()["delivery_note"]


def test_the_whatsapp_sender_gets_its_prefix_if_missing(client, demo_headers, twilio_only, monkeypatch):
    monkeypatch.setattr(get_settings(), "twilio_whatsapp_from", "+14155238886")
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp"})
    assert twilio_only[-1][1]["data"]["From"] == "whatsapp:+14155238886"


def test_metas_whatsapp_is_used_first_when_both_are_set(client, demo_headers, twilio_only, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_token", "t")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "999")
    reminder = _draft(client, demo_headers)
    _customer_contact(client, demo_headers, reminder)
    client.post(f"/reminders/{reminder['id']}/send", headers=demo_headers, json={"channel": "whatsapp"})
    assert "graph.facebook.com" in twilio_only[-1][0]


def test_twilio_without_a_whatsapp_sender_gives_no_whatsapp(client, demo_headers, twilio_only, monkeypatch):
    monkeypatch.setattr(get_settings(), "twilio_whatsapp_from", "")
    assert client.get("/messaging/channels", headers=demo_headers).json() == {"email": False, "whatsapp": False}


# Choosing the WhatsApp provider

@pytest.fixture()
def both_whatsapps(twilio_only, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_token", "meta-token")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "999")
    return twilio_only


def _send_whatsapp(client, headers):
    reminder = _draft(client, headers)
    _customer_contact(client, headers, reminder)
    return client.post(f"/reminders/{reminder['id']}/send", headers=headers, json={"channel": "whatsapp"})


def test_whatsapp_provider_auto_prefers_meta(client, demo_headers, both_whatsapps):
    assert messaging.whatsapp_provider() == "meta"
    assert _send_whatsapp(client, demo_headers).status_code == 200
    assert "graph.facebook.com" in both_whatsapps[-1][0]


def test_whatsapp_provider_twilio_wins_over_broken_meta_keys(client, demo_headers, both_whatsapps, monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_provider", "twilio")
    assert messaging.whatsapp_provider() == "twilio"
    assert _send_whatsapp(client, demo_headers).status_code == 200
    assert "api.twilio.com" in both_whatsapps[-1][0]


def test_whatsapp_provider_meta_ignores_twilio(client, demo_headers, both_whatsapps, monkeypatch):
    monkeypatch.setattr(get_settings(), "whatsapp_provider", "meta")
    assert _send_whatsapp(client, demo_headers).status_code == 200
    assert "graph.facebook.com" in both_whatsapps[-1][0]


def test_a_chosen_provider_without_its_keys_means_no_whatsapp(client, demo_headers, twilio_only, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_provider", "meta")                 # Meta chosen, but only Twilio is set up
    assert messaging.whatsapp_provider() is None
    assert client.get("/messaging/channels", headers=demo_headers).json()["whatsapp"] is False
    monkeypatch.setattr(s, "whatsapp_provider", "twilio")
    assert messaging.whatsapp_provider() == "twilio"
    monkeypatch.setattr(s, "whatsapp_provider", " Twilio ")             # stray spaces and capitals are fine
    assert messaging.whatsapp_provider() == "twilio"
