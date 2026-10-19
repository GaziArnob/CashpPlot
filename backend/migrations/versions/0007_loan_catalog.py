"""loan catalog: the eight sample loan types for every database

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19

A database that has no loan products gets the catalog. One that already has some (a seeded demo) is left alone.
"""

import sqlalchemy as sa
from alembic import op

from app.loan_catalog import LOAN_TYPES

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

COLUMNS = ("name", "lender", "kind", "min_amount", "max_amount", "rate", "tenure_months", "min_score")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM loan_products")).scalar():
        return
    table = sa.table("loan_products", *(sa.column(c) for c in COLUMNS))
    op.bulk_insert(table, [dict(zip(COLUMNS, row)) for row in LOAN_TYPES])


def downgrade() -> None:
    names = [row[0] for row in LOAN_TYPES]
    bind = op.get_bind()
    for n in names:
        bind.execute(sa.text("DELETE FROM loan_products WHERE name = :n"), {"n": n})
