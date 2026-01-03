"""Expand vault_metrics columns (and vaults tvl fields)

Revision ID: c3expandmetrics
Revises: c2top500vaults
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa

revision = "c3expandmetrics"
down_revision = "c2top500vaults"
branch_labels = None
depends_on = None

SCHEMA = "hyperliquid_vaults_discovery"


def upgrade() -> None:
    # Ensure schema exists
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # --- vaults additions (your flow writes these) ---
    with op.batch_alter_table("vaults", schema=SCHEMA) as batch:
        batch.add_column(sa.Column("tvl_usd", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("vault_create_time", sa.String(20), nullable=True))

    # --- vault_metrics additions (your VaultMetric model expects these) ---
    with op.batch_alter_table("vault_metrics", schema=SCHEMA) as batch:
        batch.add_column(sa.Column("max_distributable_tvl", sa.Numeric(20, 2), nullable=True))

        batch.add_column(sa.Column("vlm_day", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("vlm_week", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("vlm_month", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("vlm_all_time", sa.Numeric(20, 2), nullable=True))

        batch.add_column(sa.Column("max_drawdown_day", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("max_drawdown_week", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("max_drawdown_month", sa.Numeric(20, 2), nullable=True))
        batch.add_column(sa.Column("max_drawdown_all_time", sa.Numeric(20, 2), nullable=True))

        batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")))


def downgrade() -> None:
    with op.batch_alter_table("vault_metrics", schema=SCHEMA) as batch:
        batch.drop_column("created_at")
        batch.drop_column("max_drawdown_all_time")
        batch.drop_column("max_drawdown_month")
        batch.drop_column("max_drawdown_week")
        batch.drop_column("max_drawdown_day")
        batch.drop_column("vlm_all_time")
        batch.drop_column("vlm_month")
        batch.drop_column("vlm_week")
        batch.drop_column("vlm_day")
        batch.drop_column("max_distributable_tvl")

    with op.batch_alter_table("vaults", schema=SCHEMA) as batch:
        batch.drop_column("vault_create_time")
        batch.drop_column("tvl_usd")
