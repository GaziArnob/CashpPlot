"""The live demo account is created without touching existing data."""
from app.db import SessionLocal
from app.models import Business, Transaction, User


def test_ensure_demo_account_adds_it_once_and_keeps_other_accounts(client, monkeypatch):
    import seed.seed as seed_module
    from seed.seed import ensure_demo_account

    # the test database already has demo@example.com, so use a second demo address for the empty case
    DEMO_EMAIL = "demo-live@example.com"
    monkeypatch.setattr(seed_module, "DEMO_EMAIL", DEMO_EMAIL)

    client.post("/auth/signup", json={"name": "Real Owner", "email": "real@example.com", "password": "Longpassword1"})
    assert ensure_demo_account() is True
    assert ensure_demo_account() is False                      # second start-up changes nothing
    db = SessionLocal()
    try:
        emails = {u.email for u in db.query(User)}
        assert {DEMO_EMAIL, "demo@example.com", "real@example.com"} <= emails       # the existing account survived
        demo = db.query(User).filter(User.email == DEMO_EMAIL).one()
        biz = db.query(Business).filter(Business.user_id == demo.id).one()
        assert db.query(Transaction).filter(Transaction.business_id == biz.id).count() > 100
    finally:
        db.close()
    r = client.post("/auth/login", json={"email": DEMO_EMAIL, "password": "Demo@12345"})
    assert r.status_code == 200
