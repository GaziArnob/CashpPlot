"""notification center: severity, link, dedupe key, email flag, owner preferences

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("severity", sa.String(10), nullable=False, server_default="info"))
        batch.add_column(sa.Column("link", sa.String(120), nullable=True))
        batch.add_column(sa.Column("dedupe_key", sa.String(120), nullable=True))
        batch.add_column(sa.Column("emailed_at", sa.DateTime, nullable=True))
        batch.create_index("ix_notifications_dedupe_key", ["dedupe_key"])
    with op.batch_alter_table("businesses") as batch:
        batch.add_column(sa.Column("muted_notifications", sa.JSON, nullable=False, server_default="[]"))
        batch.add_column(sa.Column("notify_email", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("businesses") as batch:
        batch.drop_column("notify_email")
        batch.drop_column("muted_notifications")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_index("ix_notifications_dedupe_key")
        batch.drop_column("emailed_at")
        batch.drop_column("dedupe_key")
        batch.drop_column("link")
        batch.drop_column("severity")
