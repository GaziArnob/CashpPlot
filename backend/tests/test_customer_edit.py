"""Editing a customer's name, phone and email."""

from tests.test_api import signup


def make(client, h, **fields):
    return client.post("/customers", headers=h, json={"name": "Old Name", "phone": "+14155550123", "email": "old@example.com", **fields}).json()["id"]


def test_edit_changes_only_the_fields_sent(client):
    h = signup(client, "edit-a@example.com")
    cid = make(client, h)
    r = client.put(f"/customers/{cid}", headers=h, json={"phone": "+8801643980679"})
    assert r.status_code == 200 and r.json()["phone"] == "+8801643980679"
    assert r.json()["name"] == "Old Name" and r.json()["email"] == "old@example.com"        # untouched
    r = client.put(f"/customers/{cid}", headers=h, json={"name": "  New Name  ", "email": "new@example.com"})
    assert r.json()["name"] == "New Name" and r.json()["email"] == "new@example.com" and r.json()["phone"] == "+8801643980679"
    assert client.get(f"/customers/{cid}", headers=h).json()["name"] == "New Name"           # the profile and the list follow
    assert next(c for c in client.get("/customers", headers=h).json() if c["id"] == cid)["email"] == "new@example.com"


def test_phone_and_email_can_be_cleared_but_not_the_name(client):
    h = signup(client, "edit-b@example.com")
    cid = make(client, h)
    r = client.put(f"/customers/{cid}", headers=h, json={"phone": "", "email": ""})
    assert r.status_code == 200 and r.json()["phone"] is None and r.json()["email"] is None
    cid2 = make(client, h)
    r = client.put(f"/customers/{cid2}", headers=h, json={"phone": None, "email": None})
    assert r.json()["phone"] is None and r.json()["email"] is None
    assert client.put(f"/customers/{cid}", headers=h, json={"name": ""}).status_code == 422
    assert client.put(f"/customers/{cid}", headers=h, json={"name": "   "}).status_code == 422
    assert client.put(f"/customers/{cid}", headers=h, json={"name": None}).status_code == 422
    assert client.get(f"/customers/{cid}", headers=h).json()["name"] == "Old Name"


def test_bad_input_is_refused(client):
    h = signup(client, "edit-c@example.com")
    cid = make(client, h)
    assert client.put(f"/customers/{cid}", headers=h, json={"email": "not-an-email"}).status_code == 422
    assert client.put(f"/customers/{cid}", headers=h, json={"phone": "1" * 31}).status_code == 422
    assert client.put(f"/customers/{cid}", headers=h, json={"name": "x" * 161}).status_code == 422
    assert client.put(f"/customers/{cid}", headers=h, json={}).status_code == 200            # nothing to change is fine


def test_a_customer_belongs_to_one_business_and_staff_can_edit(client):
    h = signup(client, "edit-d@example.com")
    cid = make(client, h)
    other = signup(client, "edit-d-other@example.com")
    assert client.put(f"/customers/{cid}", headers=other, json={"name": "Hijack"}).status_code == 404
    assert client.put("/customers/999999", headers=h, json={"name": "x"}).status_code == 404
    assert client.put(f"/customers/{cid}", json={"name": "x"}).status_code == 401
    client.post("/team", headers=h, json={"name": "Sam", "email": "edit-staff@example.com", "password": "Passw0rd!x"})
    tok = client.post("/auth/login", json={"email": "edit-staff@example.com", "password": "Passw0rd!x"}).json()["access_token"]
    assert client.put(f"/customers/{cid}", headers={"Authorization": f"Bearer {tok}"}, json={"phone": "+8801700000000"}).status_code == 200
    assert client.get(f"/customers/{cid}", headers=h).json()["phone"] == "+8801700000000"


def test_the_stored_phone_and_email_are_encrypted_but_readable(client):
    from sqlalchemy import text

    from app.db import SessionLocal
    h = signup(client, "edit-e@example.com")
    cid = make(client, h)
    client.put(f"/customers/{cid}", headers=h, json={"phone": "+8801643980679"})
    db = SessionLocal()
    try:
        raw = db.execute(text("select phone from customers where id = :i"), {"i": cid}).scalar()
    finally:
        db.close()
    assert raw and "8801643980679" not in raw                      # not stored in plain text
    assert client.get(f"/customers/{cid}", headers=h).json()
    assert next(c for c in client.get("/customers", headers=h).json() if c["id"] == cid)["phone"] == "+8801643980679"
