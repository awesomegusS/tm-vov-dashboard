"""Init schema hyperliquid_vaults_discovery

Revision ID: a5aaa2b59ad0
Revises: 
Create Date: 2025-12-29 09:03:10.892124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a5aaa2b59ad0'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Ensure schema exists; actual tables are created in subsequent revision.
    op.execute("CREATE SCHEMA IF NOT EXISTS hyperliquid_vaults_discovery")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop schema and all contained objects
    op.execute("DROP SCHEMA IF EXISTS hyperliquid_vaults_discovery CASCADE")
