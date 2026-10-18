"""Row-level security on a real PostgreSQL. Skipped unless RLS_TEST_URL points at an empty test database.

    RLS_TEST_URL=postgresql+psycopg://cashpilot:PASSWORD@localhost:5432/cashpilot pytest tests/test_rls_postgres.py

The role in the URL must not be a superuser (superusers skip row-level security).
"""

import os
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("RLS_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="RLS_TEST_URL is not set")


@pytest.fixture()
def pg():
    from alembic import command
    from alembic.config import Config

    from app.db import ALEMBIC_INI, Base
    from app import models  # noqa: F401

    engine = create_engine(URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    cfg.set_main_option("sqlalchemy.url", URL.replace("%", "%%"))
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


def _session(engine, business_id=None, enforce=True):
    from app.db import _apply_tenant_context  # noqa: F401  (registers on SessionLocal only)
    from sqlalchemy import event

    Session = sessionmaker(bind=engine, autoflush=False)
    event.listen(Session, "after_begin", _apply_tenant_context)
    s = Session()
    s.info["enforce_rls"] = enforce
    if business_id:
        s.info["business_id"] = business_id
    return s


def _seed(engine):
    from app.models import Business, Customer, User
    s = _session(engine, enforce=False)
    ids = []
    for n in (1, 2):
        u = User(name=f"Owner {n}", email=f"o{n}@example.com", password_hash="x")
        s.add(u)
        s.flush()
        b = Business(user_id=u.id, name=f"Biz {n}", type="Retail", started_at=date(2025, 1, 1))
        s.add(b)
        s.flush()
        s.add(Customer(business_id=b.id, name=f"Customer of {n}"))
        ids.append(b.id)
    s.commit()
    s.close()
    return ids


def test_each_business_sees_only_its_own_rows(pg):
    from app.models import Customer
    a, b = _seed(pg)
    s = _session(pg, a)
    assert [c.name for c in s.query(Customer).all()] == ["Customer of 1"]       # no business_id filter written
    s.close()
    s = _session(pg, b)
    assert [c.name for c in s.query(Customer).all()] == ["Customer of 2"]
    s.close()


def test_no_context_sees_nothing_and_bypass_sees_all(pg):
    from app.models import Customer
    _seed(pg)
    s = _session(pg)                      # enforcing, but no business chosen
    assert s.query(Customer).count() == 0
    s.close()
    s = _session(pg, enforce=False)
    assert s.query(Customer).count() == 2
    s.close()


def test_cannot_write_into_another_business(pg):
    from app.models import Customer
    a, b = _seed(pg)
    s = _session(pg, a)
    s.add(Customer(business_id=b, name="Planted"))
    with pytest.raises(DBAPIError):
        s.commit()
    s.rollback()
    assert s.execute(text("DELETE FROM customers WHERE business_id = :b"), {"b": b}).rowcount == 0   # not visible
    s.close()
