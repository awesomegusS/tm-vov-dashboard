"""change vault_create_time to datetime

Revision ID: f9_change_vault_create_time
Revises: e8d4afffd4ec
Create Date: 2026-01-09 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9_change_vault_create_time'
down_revision = 'e8d4afffd4ec'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert String to DateTime with timezone
    # Assuming the string format is milliseconds epoch in string form (e.g. "1678123456789")
    op.execute(
        """
        ALTER TABLE hyperliquid_vaults_discovery.vaults 
        ALTER COLUMN vault_create_time TYPE TIMESTAMP WITH TIME ZONE 
        USING CASE 
            WHEN vault_create_time IS NULL OR vault_create_time = '' THEN NULL 
            ELSE to_timestamp(vault_create_time::BIGINT / 1000.0) 
        END
        """
    )


def downgrade() -> None:
    # Revert back to String
    op.execute(
        """
        ALTER TABLE hyperliquid_vaults_discovery.vaults 
        ALTER COLUMN vault_create_time TYPE VARCHAR(20) 
        USING CASE 
            WHEN vault_create_time IS NULL THEN NULL 
            ELSE (extract(epoch from vault_create_time) * 1000)::BIGINT::VARCHAR 
        END
        """
    )
