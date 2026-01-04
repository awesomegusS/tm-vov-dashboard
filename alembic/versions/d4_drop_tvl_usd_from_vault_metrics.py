"""Drop vault_metrics.tvl_usd

Revision ID: d4droptvlusd
Revises: c3expandmetrics
Create Date: 2026-01-04

"""

from alembic import op
import sqlalchemy as sa


revision = "d4droptvlusd"
down_revision = "c3expandmetrics"
branch_labels = None
depends_on = None


SCHEMA = "hyperliquid_vaults_discovery"


def upgrade() -> None:
    with op.batch_alter_table("vault_metrics", schema=SCHEMA) as batch:
        batch.drop_column("tvl_usd")


def downgrade() -> None:
    with op.batch_alter_table("vault_metrics", schema=SCHEMA) as batch:
        batch.add_column(sa.Column("tvl_usd", sa.Numeric(20, 2), nullable=True))
