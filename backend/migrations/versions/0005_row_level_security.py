"""row level security for tenant tables (PostgreSQL only)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-19

Every table that has a business_id gets a policy: a row is visible and writable only when its business_id
equals the business the request was scoped to (app.business_id), or when the session runs with the
bypass flag (background jobs, the seed, a lender opening a shared view). The app sets both settings at the
start of every transaction (app/db.py). FORCE makes the policy apply to the table owner as well, so the
application role does not skip it. audit_log is left out: login events have no business.

SQLite has no row-level security; this migration does nothing there and isolation stays in the application.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

CONDITION = ("current_setting('app.bypass_rls', true) = 'on' "
             "OR business_id = NULLIF(current_setting('app.business_id', true), '')::integer")


def _tenant_tables() -> list[str]:
    insp = sa.inspect(op.get_bind())
    return sorted(t for t in insp.get_table_names()
                  if t != "audit_log" and "business_id" in {c["name"] for c in insp.get_columns(t)})


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _tenant_tables():
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON "{table}" USING ({CONDITION}) WITH CHECK ({CONDITION})')


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _tenant_tables():
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
