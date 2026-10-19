"""bank connections, bank transaction ids, stripe ids

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

CONDITION = ("current_setting('app.bypass_rls', true) = 'on' "
             "OR business_id = NULLIF(current_setting('app.business_id', true), '')::integer")


def upgrade() -> None:
    with op.batch_alter_table("businesses") as batch:
        batch.add_column(sa.Column("stripe_customer_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("stripe_subscription_id", sa.String(64), nullable=True))
        batch.create_index("ix_businesses_stripe_customer_id", ["stripe_customer_id"])
        batch.create_index("ix_businesses_stripe_subscription_id", ["stripe_subscription_id"])
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("external_id", sa.String(64), nullable=True))
        batch.create_unique_constraint("uq_transactions_external", ["business_id", "external_id"])
    op.create_table(
        "bank_connections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("business_id", sa.Integer, sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("institution_name", sa.String(160), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("access_token", sa.String(512), nullable=False),
        sa.Column("sync_cursor", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_bank_connections_business_id", "bank_connections", ["business_id"])
    if op.get_bind().dialect.name == "postgresql":  # same tenant rule as migration 0005
        op.execute('ALTER TABLE "bank_connections" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "bank_connections" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_isolation ON "bank_connections" USING ({CONDITION}) WITH CHECK ({CONDITION})')


def downgrade() -> None:
    op.drop_table("bank_connections")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("uq_transactions_external", type_="unique")
        batch.drop_column("external_id")
    with op.batch_alter_table("businesses") as batch:
        batch.drop_index("ix_businesses_stripe_subscription_id")
        batch.drop_index("ix_businesses_stripe_customer_id")
        batch.drop_column("stripe_subscription_id")
        batch.drop_column("stripe_customer_id")
