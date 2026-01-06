"""Prefect flow: Sync Hyperliquid/HyperEVM pools from DeFi Llama.

This module implements:
- Fetch Hyperliquid & HyperEVM pools from DeFi Llama
- Flag pools that accept USDC
- Persist pool metadata + time-series metrics into Postgres

The flow is designed to run hourly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import logging

from prefect import flow, get_run_logger, task
from prefect.exceptions import MissingContextError
from sqlalchemy.dialects.postgresql import insert

from src.core.database import AsyncSessionLocal
from src.models.evm_pool import EvmPool, EvmPoolMetric
from src.services.defillama_client import DefiLlamaClient


def _get_logger() -> logging.Logger:
    """Return a logger usable both inside and outside Prefect contexts."""
    try:
        return get_run_logger()  # type: ignore[return-value]
    except MissingContextError:
        return logging.getLogger(__name__)


def flag_usdc_pools(pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark pools that accept USDC deposits.

    The simplest heuristic (per acceptance criteria): if the pool symbol contains
    the substring "usdc" (case-insensitive), mark it as USDC-accepting.

    Args:
        pools: Pool dictionaries from the DeFi Llama endpoint.

    Returns:
        The same list with an added boolean key `accepts_usdc` on each item.
    """
    for pool in pools:
        symbol = (pool.get("symbol") or "")
        pool["accepts_usdc"] = "usdc" in str(symbol).lower()
    return pools


def _timestamp_to_datetime_utc(value: Any) -> datetime:
    """Convert a DeFi Llama timestamp to timezone-aware UTC datetime.

    DeFi Llama payloads often contain a numeric `timestamp` that may be either:
    - seconds since epoch
    - milliseconds since epoch

    Args:
        value: Timestamp-like value (int/float/str).

    Returns:
        A timezone-aware datetime in UTC.
    """
    now = datetime.now(timezone.utc)
    if value is None:
        return now
    try:
        ts = float(value)
        # Heuristic: treat very large values as milliseconds.
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return now


def build_evm_pool_rows(pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build DB rows for `evm_pools`.

    Notes:
        The DeFi Llama yields endpoint is not strictly versioned; this function
        uses best-effort extraction of commonly present fields.
    """
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []

    for p in pools:
        if not isinstance(p, dict):
            continue

        pool_id = p.get("pool")
        if not pool_id:
            continue

        # DeFi Llama sometimes omits an explicit contract address; use the first
        # underlying token address as a fallback when available.
        underlying = p.get("underlyingTokens")
        underlying0 = None
        if isinstance(underlying, list) and underlying:
            underlying0 = underlying[0]

        rows.append(
            {
                "pool_id": str(pool_id),
                # The yields endpoint typically uses `project` as the protocol.
                "protocol": p.get("project") or p.get("protocol"),
                # `poolMeta` is often the pool display name; fall back to symbol.
                "name": p.get("poolMeta") or p.get("name") or p.get("symbol"),
                "symbol": p.get("symbol"),
                "contract_address": p.get("address") or p.get("contractAddress") or underlying0,
                "accepts_usdc": bool(p.get("accepts_usdc", False)),
                # Keep timestamps explicit so we can set updated_at on upserts.
                "created_at": now,
                "updated_at": now,
            }
        )

    return rows


def build_evm_pool_metric_rows(pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build DB rows for `evm_pool_metrics` time-series metrics."""
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []

    for p in pools:
        if not isinstance(p, dict):
            continue

        pool_id = p.get("pool")
        if not pool_id:
            continue

        rows.append(
            {
                "timestampz": _timestamp_to_datetime_utc(p.get("timestamp")),
                "pool_id": str(pool_id),
                "tvl_usd": p.get("tvlUsd"),
                "apy_base": p.get("apyBase"),
                "apy_reward": p.get("apyReward"),
                "apy_total": p.get("apy"),
                "created_at": now,
                "updated_at": now,
            }
        )

    return rows


async def persist_evm_pools(pools: list[dict[str, Any]]) -> tuple[int, int]:
    """Persist pool metadata and metrics rows to the DB.

    Returns:
        (pool_count_upserted, metric_count_upserted)
    """
    logger = _get_logger()

    pool_rows = build_evm_pool_rows(pools)
    metric_rows = build_evm_pool_metric_rows(pools)

    if not pool_rows:
        logger.info("No EVM pools to persist")
        return (0, 0)

    # Insert in batches to avoid exceeding DB parameter limits.
    BATCH = 1000
    pools_written = 0
    metrics_written = 0

    async with AsyncSessionLocal() as session:
        async with session.begin():
            for i in range(0, len(pool_rows), BATCH):
                chunk = pool_rows[i : i + BATCH]
                stmt = insert(EvmPool).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[EvmPool.pool_id],
                    set_={
                        "protocol": stmt.excluded.protocol,
                        "name": stmt.excluded.name,
                        "symbol": stmt.excluded.symbol,
                        "contract_address": stmt.excluded.contract_address,
                        "accepts_usdc": stmt.excluded.accepts_usdc,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)
                pools_written += len(chunk)

            for i in range(0, len(metric_rows), BATCH):
                chunk = metric_rows[i : i + BATCH]
                if not chunk:
                    continue
                stmt = insert(EvmPoolMetric).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[EvmPoolMetric.timestampz, EvmPoolMetric.pool_id],
                    set_={
                        "tvl_usd": stmt.excluded.tvl_usd,
                        "apy_base": stmt.excluded.apy_base,
                        "apy_reward": stmt.excluded.apy_reward,
                        "apy_total": stmt.excluded.apy_total,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)
                metrics_written += len(chunk)

    logger.info(f"Persisted {pools_written} pools and {metrics_written} metric rows")
    return (pools_written, metrics_written)


@task(retries=3, retry_delay_seconds=[10, 30, 60])
async def fetch_defillama_pools() -> list[dict[str, Any]]:
    """Fetch Hyperliquid/HyperEVM pools from DeFi Llama."""
    client = DefiLlamaClient()
    return await client.get_hyperliquid_pools()


@task
async def persist_evm_pools_task(pools: list[dict[str, Any]]) -> tuple[int, int]:
    """Prefect task wrapper for DB persistence."""
    return await persist_evm_pools(pools)


@flow(name="evm-pools-sync", log_prints=True)
async def sync_evm_pools_flow() -> tuple[int, int]:
    """Hourly: Fetch DeFi Llama pools for Hyperliquid/HyperEVM and persist."""
    logger = get_run_logger()
    pools = await fetch_defillama_pools()
    pools = flag_usdc_pools(pools)
    logger.info(f"Fetched {len(pools)} EVM pools")
    return await persist_evm_pools_task(pools)
