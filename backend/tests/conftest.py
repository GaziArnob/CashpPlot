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
