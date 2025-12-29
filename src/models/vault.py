from sqlalchemy import Column, String, DateTime, Boolean, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from src.core.database import Base

# Define the schema name
SCHEMA_NAME = "hyperliquid_vaults_discovery"

class Vault(Base):
    __tablename__ = "vaults"
    __table_args__ = {"schema": SCHEMA_NAME}
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    vault_address = Column(String(42), unique=True, nullable=False, index=True)
    name = Column(String(255))
    leader_address = Column(String(42))
    is_closed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class VaultMetric(Base):
    __tablename__ = "vault_metrics"
    __table_args__ = {"schema": SCHEMA_NAME}
    
    time = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
    vault_address = Column(String(42), ForeignKey(f"{SCHEMA_NAME}.vaults.vault_address"), primary_key=True)
    tvl_usd = Column(Numeric(20, 2))
    apr = Column(Numeric(10, 6))