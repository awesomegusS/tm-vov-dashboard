"""Create evm_pools and evm_pool_metrics tables.

Revision ID: e5createevmpools
Revises: d4droptvlusd
Create Date: 2026-01-06

"""

from alembic import op
import sqlalchemy as sa


revision = "e5createevmpools"
down_revision = "d4droptvlusd"
branch_labels = None
depends_on = None


SCHEMA = "hyperliquid_vaults_discovery"


def upgrade() -> None:
    """Upgrade schema."""
    # Ensure schema exists
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "evm_pools",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("pool_id", sa.String(255), nullable=False, unique=True),
        sa.Column("protocol", sa.String(50), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("symbol", sa.String(50), nullable=True),
        sa.Column("contract_address", sa.String(42), nullable=True),
        sa.Column("accepts_usdc", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # Keep timestamps as the last columns
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_evm_pools_pool_id",
        "evm_pools",
        ["pool_id"],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "evm_pool_metrics",
        sa.Column("time", sa.DateTime(timezone=True), primary_key=True, server_default=sa.text("now()")),
        sa.Column(
            "pool_id",
            sa.String(255),
            sa.ForeignKey(f"{SCHEMA}.evm_pools.pool_id"),
            primary_key=True,
        ),
        sa.Column("tvl_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("apy_base", sa.Numeric(10, 6), nullable=True),
        sa.Column("apy_reward", sa.Numeric(10, 6), nullable=True),
        sa.Column("apy_total", sa.Numeric(10, 6), nullable=True),
        # Keep timestamps as the last columns
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    # If TimescaleDB is installed, promote metrics table to a hypertable.
    # This is written defensively so local/dev DBs without Timescale still migrate.
    op.execute(
        f"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'create_hypertable') THEN
        PERFORM create_hypertable('{SCHEMA}.evm_pool_metrics', 'time', if_not_exists => TRUE);
    END IF;
END$$;
"""
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("evm_pool_metrics", schema=SCHEMA)
    op.drop_index("ix_evm_pools_pool_id", table_name="evm_pools", schema=SCHEMA)
    op.drop_table("evm_pools", schema=SCHEMA)
