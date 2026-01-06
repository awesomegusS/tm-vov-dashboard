"""Integration test for EVM pools DB upserts.

This validates that our upsert logic writes correct values to Postgres.

Requirements:
- A reachable Postgres DB via `DATABASE_URL` (sync-style URL is fine; code will
  convert to asyncpg internally).
- The DB user must have permission to run migrations.

This test will run `alembic upgrade head` to ensure the schema exists.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from src.core.database import AsyncSessionLocal
from src.pipelines.flows.evm_pools import flag_usdc_pools, persist_evm_pools


@pytest.mark.asyncio
@pytest.mark.integration
async def test_evm_pools_upsert_writes_and_updates_rows() -> None:
    """Persisting the same pool twice should update existing rows."""

    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is required for DB integration tests")

    # Ensure latest schema is applied.
    # NOTE: Alembic env.py uses asyncio.run(); run migrations in a separate
    # thread/process to avoid "asyncio.run() cannot be called" inside pytest-asyncio.
    repo_root = Path(__file__).resolve().parents[1]
    await asyncio.to_thread(
        lambda: subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            cwd=str(repo_root),
            env=os.environ.copy(),
        )
    )

    pool_id = f"test-{uuid.uuid4()}"
    ts = int(datetime.now(timezone.utc).timestamp())

    payload_1 = [
        {
            "pool": pool_id,
            "chain": "HyperEVM",
            "project": "test-protocol",
            "symbol": "USDC",
            "tvlUsd": 123.45,
            "apyBase": 0.01,
            "apyReward": None,
            "apy": 0.01,
            "timestamp": ts,
        }
    ]

    # First write (match flow behavior: flag then persist)
    pools_written, metrics_written = await persist_evm_pools(flag_usdc_pools(payload_1))
    assert pools_written == 1
    assert metrics_written == 1

    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                text(
                    """
SELECT pool_id, protocol, name, symbol, contract_address, accepts_usdc
FROM hyperliquid_vaults_discovery.evm_pools
WHERE pool_id = :pool_id
"""
                ),
                {"pool_id": pool_id},
            )
        ).mappings().first()

        assert row is not None
        assert row["pool_id"] == pool_id
        assert row["protocol"] == "test-protocol"
        assert row["symbol"] == "USDC"
        assert row["accepts_usdc"] is True

        metric = (
            await session.execute(
                text(
                    """
SELECT pool_id, time, tvl_usd, apy_base, apy_reward, apy_total
FROM hyperliquid_vaults_discovery.evm_pool_metrics
WHERE pool_id = :pool_id
ORDER BY time DESC
LIMIT 1
"""
                ),
                {"pool_id": pool_id},
            )
        ).mappings().first()

        assert metric is not None
        assert metric["pool_id"] == pool_id
        assert float(metric["tvl_usd"]) == pytest.approx(123.45)
        assert float(metric["apy_base"]) == pytest.approx(0.01)
        assert metric["apy_reward"] is None
        assert float(metric["apy_total"]) == pytest.approx(0.01)

    # Second write with changed values (same pool_id and same timestamp to force metric upsert).
    payload_2 = [
        {
            "pool": pool_id,
            "chain": "Hyperliquid",
            "project": "test-protocol-2",
            "symbol": "ETH",
            "tvlUsd": 999.0,
            "apyBase": 0.02,
            "apyReward": 0.03,
            "apy": 0.05,
            "timestamp": ts,
        }
    ]

    pools_written, metrics_written = await persist_evm_pools(flag_usdc_pools(payload_2))
    assert pools_written == 1
    assert metrics_written == 1

    async with AsyncSessionLocal() as session:
        row2 = (
            await session.execute(
                text(
                    """
SELECT pool_id, protocol, symbol, accepts_usdc
FROM hyperliquid_vaults_discovery.evm_pools
WHERE pool_id = :pool_id
"""
                ),
                {"pool_id": pool_id},
            )
        ).mappings().first()

        assert row2 is not None
        assert row2["protocol"] == "test-protocol-2"
        assert row2["symbol"] == "ETH"
        assert row2["accepts_usdc"] is False

        metric2 = (
            await session.execute(
                text(
                    """
SELECT pool_id, tvl_usd, apy_base, apy_reward, apy_total
FROM hyperliquid_vaults_discovery.evm_pool_metrics
WHERE pool_id = :pool_id AND time = to_timestamp(:ts)
"""
                ),
                {"pool_id": pool_id, "ts": ts},
            )
        ).mappings().first()

        assert metric2 is not None
        assert float(metric2["tvl_usd"]) == pytest.approx(999.0)
        assert float(metric2["apy_base"]) == pytest.approx(0.02)
        assert float(metric2["apy_reward"]) == pytest.approx(0.03)
        assert float(metric2["apy_total"]) == pytest.approx(0.05)

        # Cleanup to keep the DB tidy.
        await session.execute(
            text("DELETE FROM hyperliquid_vaults_discovery.evm_pool_metrics WHERE pool_id = :pool_id"),
            {"pool_id": pool_id},
        )
        await session.execute(
            text("DELETE FROM hyperliquid_vaults_discovery.evm_pools WHERE pool_id = :pool_id"),
            {"pool_id": pool_id},
        )
        await session.commit()
