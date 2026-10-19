from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
BASELINE_REVISION = "0001"


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # pre_ping: a serverless database (Neon) closes idle connections, so test one before using it
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


@event.listens_for(SessionLocal, "after_begin")
def _apply_tenant_context(session, transaction, connection):
    """On PostgreSQL, tell the database which business this transaction belongs to.

    Row-level security (migration 0005) then hides every other business's rows, even if a query forgets its
    own business_id filter. Request sessions enforce it; background jobs, the seed and tests run with it
    bypassed. SQLite has no such feature and is skipped.
    """
    if connection.dialect.name != "postgresql":
        return
    enforce = bool(session.info.get("enforce_rls"))
    connection.execute(
        text("SELECT set_config('app.business_id', :b, true), set_config('app.bypass_rls', :x, true)"),
        {"b": str(session.info.get("business_id") or ""), "x": "off" if enforce else "on"},
    )


def scope_to_business(db: Session, business_id: int) -> None:
    """Pin this request's session to one business (called once the caller's business is known)."""
    db.info["business_id"] = business_id
    if _is_postgres(db):
        db.execute(text("SELECT set_config('app.business_id', :b, true)"), {"b": str(business_id)})


def bypass_rls(db: Session) -> None:
    """For the few requests that must read across businesses (a lender opening a shared view by token)."""
    db.info["enforce_rls"] = False
    if _is_postgres(db):
        db.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    db.info["enforce_rls"] = True
    try:
        yield db
    finally:
        db.close()


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False  # keep the app's logging setup
    cfg.set_main_option("sqlalchemy.url", str(engine.url.render_as_string(hide_password=False)))
    return cfg


def init_db() -> None:
    """Bring the database schema up to the latest migration.

    A database created before migrations existed (tables but no alembic_version)
    is stamped at the baseline first, so only the newer migrations run on it.
    """
    from alembic import command

    cfg = _alembic_config()
    _warn_if_rls_is_bypassed()
    tables = set(inspect(engine).get_table_names())
    if "users" in tables and "alembic_version" not in tables:
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")


def _warn_if_rls_is_bypassed() -> None:
    """Superusers and BYPASSRLS roles skip row-level security, so it would silently do nothing."""
    import logging

    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.connect() as conn:
            skips = conn.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar()
    except Exception:
        return
    if skips:
        logging.getLogger(__name__).warning(
            "The database role skips row-level security (superuser or BYPASSRLS). Use a plain role so tenant isolation applies in the database too.")


def reset_db() -> None:
    """Drop everything (including the migration marker) and rebuild from migrations. Used by the seed."""
    from sqlalchemy import text

    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    init_db()
