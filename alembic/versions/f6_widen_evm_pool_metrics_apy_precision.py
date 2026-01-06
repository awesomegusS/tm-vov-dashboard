"""Widen APY precision for evm_pool_metrics.

Revision ID: f6widenevmapy
Revises: e5createevmpools
Create Date: 2026-01-06

"""

from alembic import op
import sqlalchemy as sa


revision = "f6widenevmapy"
down_revision = "e5createevmpools"
branch_labels = None
depends_on = None


SCHEMA = "hyperliquid_vaults_discovery"
TABLE = "evm_pool_metrics"


def upgrade() -> None:
    """Upgrade schema."""
    for col in ("apy_base", "apy_reward", "apy_total"):
        op.alter_column(
            TABLE,
            col,
            schema=SCHEMA,
            existing_type=sa.Numeric(10, 6),
            type_=sa.Numeric(20, 6),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    for col in ("apy_base", "apy_reward", "apy_total"):
        op.alter_column(
            TABLE,
            col,
            schema=SCHEMA,
            existing_type=sa.Numeric(20, 6),
            type_=sa.Numeric(10, 6),
            existing_nullable=True,
        )
