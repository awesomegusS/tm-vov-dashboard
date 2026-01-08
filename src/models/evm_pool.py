"""SQLAlchemy models for DeFi Llama EVM pools.

We persist two tables:
- evm_pools: pool metadata (unique per pool_id)
- evm_pool_metrics: time-series metrics (tvl, apy) keyed by (time, pool_id)

Both tables live in the existing `hyperliquid_vaults_discovery` schema to keep
all Hyperliquid-related ingestion data co-located.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Numeric, String, ForeignKey, text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from src.core.database import Base


# Define the schema name
SCHEMA_NAME = "hyperliquid_vaults_discovery"


class EvmPool(Base):
    """DeFi Llama pool metadata."""

    __tablename__ = "evm_pools"
    __table_args__ = {"schema": SCHEMA_NAME}

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    # DeFi Llama's unique pool identifier
    pool_id = Column(String(255), unique=True, nullable=False, index=True)

    protocol = Column(String(50))
    name = Column(String(255))
    symbol = Column(String(50))
    contract_address = Column(String(42))

    # Postgres boolean literal; avoid func.false() which would compile to false().
    accepts_usdc = Column(Boolean, nullable=False, server_default=text("false"))

    # Risk Parameters (Static info)
    ltv = Column(Numeric(10, 4))
    liquidation_threshold = Column(Numeric(10, 4))
    liquidation_bonus = Column(Numeric(10, 4))
    reserve_factor = Column(Numeric(10, 4))
    decimals = Column(Integer)
    
    # Source identifier (e.g., 'defillama', 'felix', 'hypurrfi', 'hyperlend', 'hyperbeat')
    source = Column(String(50))

    # Keep as the last columns (per acceptance criteria)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvmPoolMetric(Base):
    """DeFi Llama time-series metrics for a pool."""

    __tablename__ = "evm_pool_metrics"
    __table_args__ = {"schema": SCHEMA_NAME}

    timestampz = Column("time", DateTime(timezone=True), primary_key=True)
    pool_id = Column(
        String(255),
        ForeignKey(f"{SCHEMA_NAME}.evm_pools.pool_id"),
        primary_key=True,
    )

    tvl_usd = Column(Numeric(20, 2))
    # DeFi Llama APYs can exceed 10,000 (percent) for some pools.
    # Use a wider precision than NUMERIC(10, 6) to avoid overflows.
    apy_base = Column(Numeric(20, 6))
    apy_reward = Column(Numeric(20, 6))
    apy_total = Column(Numeric(20, 6))

    # Borrowing & Usage Metrics
    total_debt_usd = Column(Numeric(20, 2))
    utilization_rate = Column(Numeric(10, 6))
    apy_borrow_variable = Column(Numeric(10, 6))
    apy_borrow_stable = Column(Numeric(10, 6))

    # Keep as the last columns (per acceptance criteria)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
