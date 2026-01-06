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
import json
import asyncio

import logging

from prefect import flow, get_run_logger, task
from prefect.exceptions import MissingContextError
from sqlalchemy.dialects.postgresql import insert

from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.models.evm_pool import EvmPool, EvmPoolMetric
from src.services.defillama_client import DefiLlamaClient
from src.services.erc4626_client import Erc4626Client


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


def _load_erc4626_targets() -> list[dict[str, Any]]:
    """Load configured ERC-4626 target vaults.

    Expected JSON format (list of objects):
      [{"protocol": "Felix", "vault_address": "0x...", "name": "..."}, ...]
    """
    raw = settings.ERC4626_TARGET_VAULTS_JSON
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [p for p in parsed if isinstance(p, dict)]
        return []
    except Exception:
        return []


def _normalize_address(value: Any) -> str | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s


async def fetch_erc4626_target_pools() -> list[dict[str, Any]]:
    """Fetch target ERC-4626 vaults on-chain as a DeFi Llama-like pool list.

    This is a best-effort fallback when DeFi Llama yields does not include a
    target protocol.
    """
    logger = _get_logger()

    targets = _load_erc4626_targets()
    if not targets:
        return []

    rpc_url = settings.HYPEREVM_RPC_URL
    if not rpc_url:
        logger.warning("ERC-4626 targets configured but HYPEREVM_RPC_URL is not set; skipping")
        return []

    client = Erc4626Client(rpc_url)
    now = datetime.now(timezone.utc)
    ts = int(now.timestamp())

    hyperevm_usdc = (settings.HYPEREVM_USDC_ADDRESS or "").lower()

    async def _one(target: dict[str, Any]) -> dict[str, Any] | None:
        protocol = target.get("protocol")
        vault_address = _normalize_address(target.get("vault_address") or target.get("address"))
        if not protocol or not vault_address:
            return None

        snap = await client.get_vault_snapshot(vault_address)

        # Compute tvlUsd only when the underlying asset is USDC (1 USDC == 1 USD).
        tvl_usd = None
        asset_addr = (snap.asset_address or "").lower()
        if hyperevm_usdc and asset_addr == hyperevm_usdc:
            tvl_norm = snap.total_assets_normalized()
            if tvl_norm is not None:
                tvl_usd = float(tvl_norm)
        elif (snap.asset_symbol or "").upper() == "USDC":
            tvl_norm = snap.total_assets_normalized()
            if tvl_norm is not None:
                tvl_usd = float(tvl_norm)

        vault_name = target.get("name") or snap.vault_name or snap.vault_symbol
        vault_symbol = target.get("symbol") or snap.vault_symbol or snap.asset_symbol

        return {
            # Mimic DeFi Llama yields keys where possible.
            "pool": str(vault_address),
            "project": str(protocol),
            "poolMeta": vault_name,
            "name": vault_name,
            "symbol": vault_symbol,
            "address": str(vault_address),
            "chain": "HyperEVM",
            "timestamp": ts,
            "tvlUsd": tvl_usd,
            # No APY data available from on-chain read alone.
            "apyBase": None,
            "apyReward": None,
            "apy": None,
        }

    rows = await asyncio.gather(*[_one(t) for t in targets])
    return [r for r in rows if isinstance(r, dict)]


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


@task(retries=3, retry_delay_seconds=[10, 30, 60])
async def fetch_erc4626_target_pools_task() -> list[dict[str, Any]]:
    """Fetch configured target ERC-4626 pools on-chain."""
    return await fetch_erc4626_target_pools()


@task
async def persist_evm_pools_task(pools: list[dict[str, Any]]) -> tuple[int, int]:
    """Prefect task wrapper for DB persistence."""
    return await persist_evm_pools(pools)


@flow(name="evm-pools-sync", log_prints=True)
async def sync_evm_pools_flow(*, persist: bool = True) -> tuple[int, int]:
    """Hourly: Fetch DeFi Llama pools for Hyperliquid/HyperEVM.

    Args:
        persist: When True (default), upsert pools + metrics into Postgres.
            When False, run a local dry-run (fetch + transform) and return
            row counts without touching the DB.
    """
    logger = get_run_logger()
    pools = await fetch_defillama_pools()
    pools = flag_usdc_pools(pools)

    # On-chain fallback for target protocols (ERC-4626).
    # This is driven by config, so it is safe to call every run.
    onchain = await fetch_erc4626_target_pools_task()
    if onchain:
        onchain = flag_usdc_pools(onchain)
        # De-dupe by pool id (DeFi Llama's `pool` key).
        by_id: dict[str, dict[str, Any]] = {str(p.get("pool")): p for p in pools if p.get("pool")}
        for p in onchain:
            pid = p.get("pool")
            if pid:
                by_id[str(pid)] = p
        pools = list(by_id.values())

    logger.info(f"Fetched {len(pools)} EVM pools")
    if not persist:
        return (len(build_evm_pool_rows(pools)), len(build_evm_pool_metric_rows(pools)))

    return await persist_evm_pools_task(pools)
