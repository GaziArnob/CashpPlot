"""Staff roles, plans, two-factor sign-in, the AI mode and lender referrals."""

from datetime import timedelta

import pytest

from app import plans
from app.ai import providers
from app.security import totp_code
from tests.test_api import signup

PASSWORD = "Passw0rd!x"


def login(client, email, password=PASSWORD, code=None):
    body = {"email": email, "password": password, **({"code": code} if code else {})}
    return client.post("/auth/login", json=body)


def headers(r):
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def owner_with_staff(client, tag):
    owner = signup(client, f"owner-{tag}@example.com")
    r = client.post("/team", headers=owner, json={"name": "Sam Staff", "email": f"staff-{tag}@example.com", "password": PASSWORD})
    assert r.status_code == 201, r.text
    sr = login(client, f"staff-{tag}@example.com")
    assert sr.status_code == 200, sr.text
    return owner, headers(sr), r.json()


# Staff

def test_staff_can_record_work_but_not_see_the_owners_view(client):
    owner, staff, member = owner_with_staff(client, "scope")
    assert member["role"] == "staff" and client.get("/auth/me", headers=staff).json()["role"] == "staff"

    # What staff are for
    assert client.post("/transactions", headers=staff, json={"date": "2026-10-01", "amount": 50, "type": "income",
                                                             "category": "Sales"}).status_code == 201
    cust = client.post("/customers", headers=staff, json={"name": "Walk-in Co"}).json()
    assert client.post("/invoices", headers=staff, json={"customer_id": cust["id"], "amount": 100,
                                                         "issue_date": "2026-10-01", "due_date": "2026-10-20"}).status_code == 201
    assert client.get("/customers", headers=staff).status_code == 200
    assert client.get("/settings", headers=staff).json()["currency"] == "USD"      # read-only business basics
    # They work inside the owner's business: the owner sees what staff recorded.
    assert [c["name"] for c in client.get("/customers", headers=owner).json()] == ["Walk-in Co"]

    # What they must not reach
    for method, path in [("get", "/dashboard/summary"), ("get", "/credit-score"), ("get", "/loan/readiness"),
                         ("get", "/reports/pnl"), ("get", "/payables/analysis"), ("get", "/team"),
                         ("get", "/billing/plan"), ("get", "/lender-access"), ("get", "/referrals"),
                         ("get", "/cash-advisor/summary"), ("get", "/action-plan"), ("get", "/products/performance"),
                         ("get", "/collections/priority"), ("get", "/settings/export"), ("get", "/agent/suggestions")]:
        r = getattr(client, method)(path, headers=staff)
        assert r.status_code == 403, (path, r.status_code)
    assert client.put("/settings", headers=staff, json={"name": "Hacked"}).status_code == 403
    assert client.delete("/settings/account", headers=staff).status_code == 403
    assert client.post("/team", headers=staff, json={"name": "X", "email": "x@example.com", "password": PASSWORD}).status_code == 403
    assert client.post("/onboarding", headers=staff, json={"name": "Mine", "started_at": "2025-01-01"}).status_code == 403


def test_staff_are_tied_to_their_own_business(client):
    owner_a, staff_a, _ = owner_with_staff(client, "iso-a")
    owner_b, staff_b, _ = owner_with_staff(client, "iso-b")
    client.post("/customers", headers=staff_a, json={"name": "A's customer"})
    assert client.get("/customers", headers=staff_b).json() == []
    other_id = client.get("/customers", headers=owner_a).json()[0]["id"]
    assert client.get(f"/customers/{other_id}", headers=staff_b).status_code == 404
    team_a = client.get("/team", headers=owner_a).json()["members"]
    # An owner can't manage another owner's staff.
    assert client.delete(f"/team/{team_a[0]['id']}", headers=owner_b).status_code == 404


def test_team_management(client):
    owner, staff, member = owner_with_staff(client, "mgmt")
    assert client.post("/team", headers=owner, json={"name": "Dup", "email": "staff-mgmt@example.com",
                                                     "password": PASSWORD}).status_code == 409
    assert client.post("/team", headers=owner, json={"name": "Weak", "email": "weak@example.com",
                                                     "password": "short"}).status_code == 422
    # New password works, old one doesn't, and sign-in elsewhere ends.
    assert client.post(f"/team/{member['id']}/password", headers=owner, json={"password": "Brand-new-pass1"}).status_code == 200
    assert login(client, "staff-mgmt@example.com").status_code == 401
    assert login(client, "staff-mgmt@example.com", "Brand-new-pass1").status_code == 200
    # Removing switches the login off at once, including a token already issued.
    assert client.delete(f"/team/{member['id']}", headers=owner).json()["active"] is False
    assert client.get("/customers", headers=staff).status_code == 401
    assert login(client, "staff-mgmt@example.com", "Brand-new-pass1").status_code == 401
    assert client.post(f"/team/{member['id']}/reactivate", headers=owner).json()["active"] is True
    assert login(client, "staff-mgmt@example.com", "Brand-new-pass1").status_code == 200


def test_staff_limit(client, monkeypatch):
    from app.api import team
    monkeypatch.setattr(team, "MAX_STAFF", 1)
    owner, _, _ = owner_with_staff(client, "limit")
    assert client.post("/team", headers=owner, json={"name": "Two", "email": "two-limit@example.com",
                                                     "password": PASSWORD}).status_code == 409


def test_deleting_the_account_removes_staff_and_every_record(client):
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import Customer, User
    owner, staff, member = owner_with_staff(client, "delete")
    client.post("/customers", headers=owner, json={"name": "Gone soon"})
    assert client.delete("/settings/account", headers=owner).status_code == 204
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(User).where(User.email.like("%-delete@example.com"))) == 0
        assert db.scalar(select(func.count()).select_from(Customer).where(Customer.name == "Gone soon")) == 0
    finally:
        db.close()
    assert login(client, "staff-delete@example.com").status_code == 401


# Plans

def test_new_business_starts_on_a_pro_trial(client):
    h = signup(client, "trial@example.com")
    p = client.get("/billing/plan", headers=h).json()
    assert p["effective_plan"] == "pro" and p["trial"] is True and 1 <= p["days_left"] <= plans.TRIAL_DAYS
    assert p["billing_mode"] == "demo" and "no payment" in p["note"]
    assert client.get("/credit-score", headers=h).status_code == 200


def test_free_plan_keeps_the_basics_and_locks_pro_features(client):
    h = signup(client, "free@example.com")
    assert client.post("/billing/plan", headers=h, json={"plan": "free"}).status_code == 422        # needs confirm
    assert client.post("/billing/plan", headers=h, json={"plan": "free", "confirm": True}).json()["effective_plan"] == "free"
    # Still free
    assert client.get("/dashboard/summary", headers=h).status_code == 200
    assert client.get("/cashflow/forecast?days=7", headers=h).status_code == 200
    assert client.post("/customers", headers=h, json={"name": "C"}).status_code == 201
    assert client.get("/transactions", headers=h).status_code == 200
    # Pro only
    for path in ("/cashflow/forecast?days=30", "/credit-score", "/loan/readiness", "/collections/priority", "/reports/pnl",
                 "/cash-advisor/summary", "/payables/analysis", "/products/performance", "/agent/suggestions",
                 "/referrals", "/lender-access", "/recovery/priority"):
        r = client.get(path, headers=h)
        assert r.status_code == 402 and r.json()["detail"].startswith("Upgrade to Pro"), (path, r.status_code)
    assert client.post("/billing/plan", headers=h, json={"plan": "pro", "confirm": True}).json()["effective_plan"] == "pro"
    assert client.get("/credit-score", headers=h).status_code == 200


def test_an_ended_trial_falls_back_to_free(client):
    from app.db import SessionLocal
    from app.models import Business, User, utcnow
    h = signup(client, "expired@example.com")
    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.email == "expired@example.com").one()
        b = db.query(Business).filter(Business.user_id == owner.id).one()
        b.plan_expires_at = utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()
    p = client.get("/billing/plan", headers=h).json()
    assert p["effective_plan"] == "free" and p["trial_ended"] is True
    assert client.get("/credit-score", headers=h).status_code == 402


def test_payments_are_not_pretended(client, monkeypatch):
    from types import SimpleNamespace

    from app.api import billing
    h = signup(client, "nopay@example.com")
    monkeypatch.setattr(billing, "get_settings", lambda: SimpleNamespace(billing_mode="live"))
    assert client.get("/billing/plan", headers=h).json()["payments_connected"] is True
    assert client.post("/billing/plan", headers=h, json={"plan": "pro", "confirm": True}).status_code == 501


# Two-factor sign-in

def test_two_factor_sign_in(client):
    email = "twofa@example.com"
    h = signup(client, email)
    assert client.post("/auth/2fa/enable", headers=h, json={"code": "123456"}).status_code == 409   # setup first
    setup = client.post("/auth/2fa/setup", headers=h).json()
    secret = setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/CashPilot:") and secret in setup["otpauth_uri"]
    assert login(client, email).status_code == 200                                                 # not on yet
    assert client.post("/auth/2fa/enable", headers=h, json={"code": "000000"}).status_code == 422
    assert client.post("/auth/2fa/enable", headers=h, json={"code": totp_code(secret)}).json() == {"enabled": True}
    assert client.get("/auth/me", headers=h).json()["totp_enabled"] is True

    needs_code = login(client, email)
    assert needs_code.status_code == 401 and needs_code.json()["detail"] == "Two-factor code required"
    assert login(client, email, code="000000").json()["detail"] == "Invalid two-factor code"
    assert login(client, email, "wrong-password", code=totp_code(secret)).status_code == 401
    ok = login(client, email, code=totp_code(secret))
    assert ok.status_code == 200 and client.get("/auth/me", headers=headers(ok)).status_code == 200

    assert client.post("/auth/2fa/disable", headers=h, json={"password": "nope-nope", "code": totp_code(secret)}).status_code == 401
    assert client.post("/auth/2fa/disable", headers=h, json={"password": PASSWORD, "code": totp_code(secret)}).json() == {"enabled": False}
    assert login(client, email).status_code == 200


def test_totp_matches_the_standard_test_vector():
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert totp_code(secret, at=59) == "287082"          # RFC 6238, appendix B
    assert totp_code(secret, at=1111111109) == "081804"


# AI mode

class FakeProvider:
    def __init__(self, name):
        self.name, self.calls = name, 0

    def chat(self, messages, tools=None):
        self.calls += 1
        return providers.LLMResult(text="hello", provider=self.name)


@pytest.mark.parametrize("mode,used", [("cloud", {"groq", "ollama"}), ("local", {"ollama"}), ("off", set())])
def test_ai_mode_limits_where_text_is_made(monkeypatch, mode, used):
    fakes = [FakeProvider("groq"), FakeProvider("ollama")]
    monkeypatch.setattr(providers, "build_providers", lambda: fakes)
    if mode == "off":
        with pytest.raises(providers.NoLLMAvailable):
            providers.chat([{"role": "user", "content": "hi"}], mode=mode)
    else:
        providers.chat([{"role": "user", "content": "hi"}], mode=mode)
    assert {f.name for f in fakes if f.calls} == ({"groq"} if mode == "cloud" else used)
    assert providers.any_configured(mode) is (mode != "off")


def test_local_mode_without_a_local_model_uses_templates(client, monkeypatch):
    h = signup(client, "localai@example.com")
    assert client.put("/settings", headers=h, json={"ai_mode": "local"}).json()["ai_mode"] == "local"
    monkeypatch.setattr(providers, "build_providers", lambda: [FakeProvider("groq")])  # only a hosted model exists
    assert client.get("/agent/suggestions", headers=h).json()["llm_configured"] is False
    r = client.post("/agent/chat", headers=h, json={"message": "Will I run short on cash?"}).json()
    assert r["provider"] == "templates"
    assert client.put("/settings", headers=h, json={"ai_mode": "weird"}).status_code == 422


# Lender referrals

def test_referral_flow_and_rules(client, demo_headers):
    products = client.get("/loan/recommendations", headers=demo_headers).json()["options"]
    pid, amount = products[0]["product_id"], products[0]["recommended_amount"]
    body = {"loan_product_id": pid, "amount": amount, "share": ["credit_score", "pnl"], "confirm": True}

    assert client.post("/referrals", headers=demo_headers, json={**body, "confirm": False}).status_code == 422
    assert client.post("/referrals", headers=demo_headers, json={**body, "share": []}).status_code == 422
    assert client.post("/referrals", headers=demo_headers, json={**body, "loan_product_id": 99999}).status_code == 404
    assert client.post("/referrals", headers=demo_headers, json={**body, "amount": 1}).status_code == 422   # below the minimum
    r = client.post("/referrals", headers=demo_headers, json=body)
    assert r.status_code == 201, r.text
    ref = r.json()
    assert ref["status"] == "submitted" and ref["shared_fields"] == ["credit_score", "pnl"] and ref["score_snapshot"] > 0
    assert "not a loan application" in ref["disclaimer"]
    assert client.post("/referrals", headers=demo_headers, json=body).status_code == 409                    # already open

    def mark(status):
        return client.post(f"/referrals/{ref['id']}/status", headers=demo_headers, json={"status": status})
    assert mark("funded").status_code == 409                    # can't skip "contacted"
    assert mark("contacted").json()["status"] == "contacted"
    assert mark("funded").json()["status"] == "funded"
    assert mark("withdrawn").status_code == 409                 # finished
    listing = client.get("/referrals", headers=demo_headers).json()
    assert listing["summary"]["by_status"].get("funded", 0) >= 1 and listing["items"]


def test_referral_needs_a_high_enough_score_and_stays_private(client):
    from tests.test_api import signup as new_owner
    h = new_owner(client, "referral-new@example.com")                    # no history: low score
    top = max(client.get("/payables/analysis", headers=h).json().get("financing", []) or [{}], key=lambda x: 0)
    assert top is not None
    from app.db import SessionLocal
    from app.models import LoanProduct
    db = SessionLocal()
    try:
        strict = db.query(LoanProduct).order_by(LoanProduct.min_score.desc()).first()
        pid, amount = strict.id, strict.min_amount
    finally:
        db.close()
    r = client.post("/referrals", headers=h, json={"loan_product_id": pid, "amount": amount, "share": ["credit_score"],
                                                   "confirm": True})
    assert r.status_code == 422 and "below this product's minimum" in r.json()["detail"]
    assert client.get("/referrals", headers=h).json()["items"] == []
