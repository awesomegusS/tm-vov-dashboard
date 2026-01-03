"""Create top_500_vaults table

Revision ID: c2top500vaults
Revises: b1addvaultcols
Create Date: 2026-01-03

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c2top500vaults"
down_revision = "b1addvaultcols"
branch_labels = None
depends_on = None

SCHEMA = "hyperliquid_vaults_discovery"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "top_500_vaults",
        sa.Column(
            "vault_address",
            sa.String(42),
            sa.ForeignKey(f"{SCHEMA}.vaults.vault_address"),
            primary_key=True,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("tvl_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("metrics_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_top_500_vaults_rank",
        "top_500_vaults",
        ["rank"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_top_500_vaults_rank", table_name="top_500_vaults", schema=SCHEMA)
    op.drop_table("top_500_vaults", schema=SCHEMA)
