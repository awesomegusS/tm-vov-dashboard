"""Add vault description, relationship, pnl and timestamps

Revision ID: b1addvaultcols
Revises: a5aaa2b59ad0
Create Date: 2025-12-29 17:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1addvaultcols'
down_revision = 'a5aaa2b59ad0'
branch_labels = None
depends_on = None

SCHEMA = 'hyperliquid_vaults_discovery'


def upgrade() -> None:
    # create schema if missing
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # create vaults table
    op.create_table(
        'vaults',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('vault_address', sa.String(42), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('leader_address', sa.String(42), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_closed', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('relationship_type', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        schema=SCHEMA,
    )

    # create vault_metrics table (time-series style with composite PK)
    op.create_table(
        'vault_metrics',
        sa.Column('time', sa.DateTime(timezone=True), primary_key=True, server_default=sa.text('now()')),
        sa.Column('vault_address', sa.String(42), sa.ForeignKey(f"{SCHEMA}.vaults.vault_address"), primary_key=True),
        sa.Column('tvl_usd', sa.Numeric(20, 2), nullable=True),
        sa.Column('apr', sa.Numeric(10, 6), nullable=True),
        sa.Column('leader_commission', sa.Numeric(10, 6), nullable=True),
        sa.Column('follower_count', sa.Integer(), nullable=True),
        sa.Column('pnl_day', sa.Numeric(20, 2), nullable=True),
        sa.Column('pnl_week', sa.Numeric(20, 2), nullable=True),
        sa.Column('pnl_month', sa.Numeric(20, 2), nullable=True),
        sa.Column('pnl_all_time', sa.Numeric(20, 2), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        schema=SCHEMA,
    )


def downgrade() -> None:
    # drop tables
    op.drop_table('vault_metrics', schema=SCHEMA)
    op.drop_table('vaults', schema=SCHEMA)
    # optionally drop schema
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
