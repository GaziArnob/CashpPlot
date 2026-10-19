"""Stripe checkout and webhook, and the Plaid bank import. Every outgoing call is faked."""

import hashlib
import hmac
import json
import time

import httpx
import pytest

from app import stripe_client
from app.config import get_settings
from tests.test_api import signup

SECRET = "whsec_test"


class Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d


@pytest.fixture()
def stripe_on(monkeypatch):
    s = get_settings()
    for k, v in dict(billing_mode="stripe", stripe_secret_key="sk_test_x", stripe_price_id="price_1",
                     stripe_webhook_secret=SECRET).items():
        monkeypatch.setattr(s, k, v)
    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, url, kw.get("data")))
        if url.endswith("/checkout/sessions"):
            return Resp({"url": "https://checkout.stripe.com/pay/cs_test_1"})
        if url.endswith("/billing_portal/sessions"):
            return Resp({"url": "https://billing.stripe.com/session/x"})
        return Resp({"id": "sub_1", "status": "canceled"})

    monkeypatch.setattr(httpx, "request", fake_request)
    return calls


def signed(event: dict, secret=SECRET, when=None):
    body = json.dumps(event).encode()
    t = str(int(when if when is not None else time.time()))
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"}


def _business_id(email):
    from app.db import SessionLocal
    from app.models import Business, User
    db = SessionLocal()
    try:
        return db.query(Business).join(User, User.id == Business.user_id).filter(User.email == email).one().id
    finally:
        db.close()


def _set_business(email, **fields):
    from app.db import SessionLocal
    from app.models import Business
    db = SessionLocal()
    try:
        b = db.get(Business, _business_id(email))
        for k, v in fields.items():
            setattr(b, k, v)
        db.commit()
        return b.id
    finally:
        db.close()


def test_checkout_sends_the_owner_to_stripe_and_never_changes_the_plan(client, stripe_on):
    h = signup(client, "stripe-a@example.com")
    plan = client.get("/billing/plan", headers=h).json()
    assert plan["can_checkout"] is True and plan["billing_mode"] == "stripe"
    r = client.post("/billing/checkout", headers=h)
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.com/")
    method, url, data = stripe_on[-1]
    assert data["mode"] == "subscription" and data["line_items[0][price]"] == "price_1"
    assert data["client_reference_id"] == str(_business_id("stripe-a@example.com"))
    assert client.post("/billing/plan", headers=h, json={"plan": "pro", "confirm": True}).status_code == 409


def test_webhook_needs_a_valid_signature(client, stripe_on):
    ev = {"type": "checkout.session.completed", "data": {"object": {"mode": "subscription", "client_reference_id": "1",
                                                                    "payment_status": "paid", "customer": "cus_1"}}}
    body, headers = signed(ev, secret="wrong")
    assert client.post("/billing/webhook", content=body, headers=headers).status_code == 400
    body, headers = signed(ev, when=time.time() - 3600)  # too old: a replay
    assert client.post("/billing/webhook", content=body, headers=headers).status_code == 400
    assert client.post("/billing/webhook", content=body).status_code == 400
    assert stripe_client.verify_webhook(b"{}", "t=1,v1=zz") is None


def test_payment_upgrades_and_cancellation_downgrades(client, stripe_on):
    h = signup(client, "stripe-b@example.com")
    bid = _set_business("stripe-b@example.com", plan="free", plan_expires_at=None)
    assert client.get("/billing/plan", headers=h).json()["effective_plan"] == "free"
    paid = {"type": "checkout.session.completed", "data": {"object": {
        "mode": "subscription", "client_reference_id": str(bid), "payment_status": "paid",
        "customer": "cus_b", "subscription": "sub_b"}}}
    body, headers = signed(paid)
    assert client.post("/billing/webhook", content=body, headers=headers).status_code == 200
    plan = client.get("/billing/plan", headers=h).json()
    assert plan["effective_plan"] == "pro" and plan["has_subscription"] is True
    assert client.post("/billing/portal", headers=h).json()["url"].startswith("https://billing.stripe.com/")
    gone = {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_b"}}}
    body, headers = signed(gone)
    client.post("/billing/webhook", content=body, headers=headers)
    assert client.get("/billing/plan", headers=h).json()["effective_plan"] == "free"


def test_an_unpaid_checkout_does_not_upgrade(client, stripe_on):
    h = signup(client, "stripe-e@example.com")
    bid = _set_business("stripe-e@example.com", plan="free", plan_expires_at=None)
    unpaid = {"type": "checkout.session.completed", "data": {"object": {
        "mode": "subscription", "client_reference_id": str(bid), "payment_status": "unpaid", "customer": "x"}}}
    body, headers = signed(unpaid)
    client.post("/billing/webhook", content=body, headers=headers)
    assert client.get("/billing/plan", headers=h).json()["effective_plan"] == "free"


def test_deleting_an_account_cancels_its_subscription_first(client, stripe_on, monkeypatch):
    h = signup(client, "stripe-c@example.com")
    _set_business("stripe-c@example.com", stripe_subscription_id="sub_c")
    assert client.delete("/settings/account", headers=h).status_code == 204
    assert any(m == "DELETE" and u.endswith("/subscriptions/sub_c") for m, u, _ in stripe_on)

    h2 = signup(client, "stripe-d@example.com")
    _set_business("stripe-d@example.com", stripe_subscription_id="sub_d")
    monkeypatch.setattr(httpx, "request", lambda *a, **k: Resp({"error": {"message": "boom"}}, 500))
    r = client.delete("/settings/account", headers=h2)
    assert r.status_code == 502 and client.get("/auth/me", headers=h2).status_code == 200   # kept, not half-deleted


# Plaid

@pytest.fixture()
def plaid_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "plaid_client_id", "id")
    monkeypatch.setattr(s, "plaid_secret", "secret")
    state = {"pages": []}

    def fake_post(url, **kw):
        if url.endswith("/link/token/create"):
            return Resp({"link_token": "link-sandbox-1"})
        if url.endswith("/item/public_token/exchange"):
            return Resp({"access_token": "access-sandbox-1", "item_id": "item_1"})
        if url.endswith("/transactions/sync"):
            return Resp(state["pages"].pop(0))
        return Resp({})

    monkeypatch.setattr(httpx, "post", fake_post)
    return state


def _txn(i, amount, **kw):
    return {"transaction_id": f"tx{i}", "date": "2026-10-10", "amount": amount, "iso_currency_code": "USD",
            "name": f"Merchant {i}", "pending": False, "personal_finance_category": {"primary": "FOOD_AND_DRINK"}, **kw}


def test_bank_connect_and_sync_imports_once(client, plaid_on):
    h = signup(client, "plaid-a@example.com")
    assert client.get("/bank/status", headers=h).json()["configured"] is True
    assert client.post("/bank/link-token", headers=h).json()["link_token"] == "link-sandbox-1"
    c = client.post("/bank/exchange", headers=h, json={"public_token": "public-sandbox-1", "institution_name": "Test Bank"}).json()
    plaid_on["pages"] = [
        {"added": [_txn(1, 12.5), _txn(2, -300), _txn(3, 5, pending=True), _txn(4, 9, iso_currency_code="EUR")],
         "modified": [], "removed": [], "next_cursor": "c1", "has_more": True},
        {"added": [_txn(5, 40)], "modified": [], "removed": [], "next_cursor": "c2", "has_more": False},
    ]
    r = client.post(f"/bank/{c['id']}/sync", headers=h).json()
    assert r == {"imported": 3, "skipped": 2, "removed": 0}
    items = client.get("/transactions?limit=50", headers=h).json()["items"]
    by_desc = {t["description"]: t for t in items}
    assert by_desc["Merchant 1"]["type"] == "expense" and by_desc["Merchant 1"]["amount"] == 12.5     # money out
    assert by_desc["Merchant 2"]["type"] == "income" and by_desc["Merchant 2"]["amount"] == 300       # money in
    assert by_desc["Merchant 1"]["category"] == "Food And Drink" and by_desc["Merchant 1"]["source"] == "bank"
    # The next sync changes one, removes one, and re-sends one: still no duplicates.
    plaid_on["pages"] = [{"added": [_txn(1, 12.5)], "modified": [_txn(5, 45)], "removed": [{"transaction_id": "tx2"}],
                          "next_cursor": "c3", "has_more": False}]
    r = client.post(f"/bank/{c['id']}/sync", headers=h).json()
    assert r["imported"] == 0 and r["removed"] == 1
    items = client.get("/transactions?limit=50", headers=h).json()["items"]
    assert len(items) == 2 and {t["amount"] for t in items} == {12.5, 45}


def test_bank_token_never_leaves_the_server_and_access_is_scoped(client, plaid_on):
    h = signup(client, "plaid-b@example.com")
    c = client.post("/bank/exchange", headers=h, json={"public_token": "public-sandbox-2", "institution_name": "B"}).json()
    assert "access-sandbox-1" not in json.dumps(client.get("/bank/status", headers=h).json()) + json.dumps(c)
    other = signup(client, "plaid-c@example.com")
    assert client.post(f"/bank/{c['id']}/sync", headers=other).status_code == 404
    assert client.delete(f"/bank/{c['id']}", headers=other).status_code == 404
    assert client.delete(f"/bank/{c['id']}", headers=h).status_code == 204
    assert client.get("/bank/status", headers=h).json()["connections"] == []


def test_bank_not_configured_and_free_plan_locked(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "plaid_client_id", "")
    h = signup(client, "plaid-d@example.com")
    assert client.get("/bank/status", headers=h).json()["configured"] is False
    assert client.post("/bank/link-token", headers=h).status_code == 503
    _set_business("plaid-d@example.com", plan="free", plan_expires_at=None)
    assert client.get("/bank/status", headers=h).status_code == 402
