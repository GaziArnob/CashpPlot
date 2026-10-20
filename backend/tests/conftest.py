import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["OLLAMA_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ALERTS_LOG_PATH"] = f"{_tmp}/alerts.log"
# Tests must never use real accounts from the developer's .env (they could send real email, SMS or payments).
for _key in ("BREVO_API_KEY", "BREVO_SENDER_EMAIL", "MAILJET_API_KEY", "MAILJET_SECRET_KEY", "MAILJET_SENDER_EMAIL",
             "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID",
             "WHATSAPP_TEMPLATE_NAME", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "BIRD_API_KEY", "BIRD_TEMPLATE_SLUG", "BIRD_TEMPLATE_LANG",
             "BIRD_WHATSAPP_FROM", "STRIPE_SECRET_KEY",
             "STRIPE_PRICE_ID", "STRIPE_WEBHOOK_SECRET", "PLAID_CLIENT_ID", "PLAID_SECRET"):
    os.environ[_key] = ""
os.environ["BILLING_MODE"] = "demo"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import deps  # noqa: E402
from app.main import app  # noqa: E402
from seed.seed import DEMO_EMAIL, DEMO_PASSWORD, seed  # noqa: E402


@pytest.fixture(scope="session")
def seeded():
    return seed()


@pytest.fixture(autouse=True)
def reset_limits():
    for limiter in (deps.auth_limiter, deps.ai_limiter, deps.upload_limiter):
        limiter.reset()


@pytest.fixture(scope="session")
def client(seeded):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def demo_headers(client):
    r = client.post("/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
