"""Alembic environment: uses the app's settings and models, batch mode for SQLite."""

import sys
from logging.config import fileConfig
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the backend folder

import sqlalchemy as sa
from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.config import get_settings
from app.db import Base
from app.security import EncryptedString

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# The app's DATABASE_URL wins unless a caller (tests, seed) set one explicitly.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    # Encrypted columns are plain strings in the database; render them that way.
    if type_ == "type" and isinstance(obj, EncryptedString):
        return f"sa.String(length={obj.impl.length})"
    return False


def _configure(**kwargs):
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        target_metadata=target_metadata,
        render_as_batch=url.startswith("sqlite"),  # SQLite can't ALTER most things in place
        render_item=render_item,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True,
               dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

_ = sa  # keeps the import for rendered type expressions
