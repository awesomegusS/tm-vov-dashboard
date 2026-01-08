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
from src.services.felix_client import FelixClient
from src.services.hyperbeat_client import HyperbeatClient
from src.services.hyperlend_client import HyperlendClient
from src.services.hypurrfi_client import HypurrFiClient


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

        pool_id = p.get("pool") or p.get("pool_id")
        if not pool_id:
            continue

        # DeFi Llama sometimes omits an explicit contract address; use the first
        # underlying token address as a fallback when available.
        contract_address = p.get("contract_address")
        if not contract_address:
            contract_address = p.get("address") or p.get("contractAddress")
            underlying = p.get("underlyingTokens")
            if not contract_address and isinstance(underlying, list) and underlying:
                contract_address = underlying[0]

        # Determine source
        source = p.get("source")
        if not source:
            source = "defillama"

        rows.append(
            {
                "pool_id": str(pool_id),
                "protocol": p.get("protocol") or p.get("project"),
                "name": p.get("name") or p.get("poolMeta") or p.get("symbol"),
                "symbol": p.get("symbol"),
                "contract_address": contract_address,
                "accepts_usdc": bool(p.get("accepts_usdc", False)),
                "ltv": p.get("ltv"),
                "liquidation_threshold": p.get("liquidation_threshold"),
                "liquidation_bonus": p.get("liquidation_bonus"),
                "reserve_factor": p.get("reserve_factor"),
                "decimals": p.get("decimals"),
                "source": source,
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

        pool_id = p.get("pool") or p.get("pool_id")
        if not pool_id:
            continue
        
        # Timestamps: DeFi Llama uses "timestamp", our clients use current time (so None in p) or implicit
        ts_val = p.get("timestamp")
        timestampz = _timestamp_to_datetime_utc(ts_val) if ts_val else now

        rows.append(
            {
                "timestampz": timestampz,
                "pool_id": str(pool_id),
                "tvl_usd": p.get("tvl_usd") if p.get("tvl_usd") is not None else p.get("tvlUsd"),
                "apy_base": p.get("apy_base") if p.get("apy_base") is not None else p.get("apyBase"),
                "apy_reward": p.get("apy_reward") if p.get("apy_reward") is not None else p.get("apyReward"),
                "apy_total": p.get("apy_total") if p.get("apy_total") is not None else p.get("apy"),
                "total_debt_usd": p.get("total_debt_usd"),
                "utilization_rate": p.get("utilization_rate"),
                "apy_borrow_variable": p.get("apy_borrow_variable"),
                "apy_borrow_stable": p.get("apy_borrow_stable"),
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
                        "ltv": stmt.excluded.ltv,
                        "liquidation_threshold": stmt.excluded.liquidation_threshold,
                        "liquidation_bonus": stmt.excluded.liquidation_bonus,
                        "reserve_factor": stmt.excluded.reserve_factor,
                        "decimals": stmt.excluded.decimals,
                        "source": stmt.excluded.source,
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
                        "total_debt_usd": stmt.excluded.total_debt_usd,
                        "utilization_rate": stmt.excluded.utilization_rate,
                        "apy_borrow_variable": stmt.excluded.apy_borrow_variable,
                        "apy_borrow_stable": stmt.excluded.apy_borrow_stable,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)
                metrics_written += len(chunk)

    logger.info(f"Persisted {pools_written} pools and {metrics_written} metric rows")
    return (pools_written, metrics_written)


@task(retries=5, retry_delay_seconds=[10, 20, 30, 60, 120])
async def fetch_defillama_pools() -> list[dict[str, Any]]:
    """Fetch Hyperliquid/HyperEVM pools from DeFi Llama."""
    client = DefiLlamaClient()
    return await client.get_hyperliquid_pools()


@task(retries=5, retry_delay_seconds=[10, 20, 30, 60, 120])
def fetch_felix_pools() -> list[dict[str, Any]]:
    """Fetch pools from Felix Protocol."""
    client = FelixClient()
    return client.fetch_pools()


@task(retries=5, retry_delay_seconds=[10, 20, 30, 60, 120])
def fetch_hyperlend_pools() -> list[dict[str, Any]]:
    """Fetch pools from Hyperlend."""
    client = HyperlendClient()
    return client.fetch_pools()


@task(retries=5, retry_delay_seconds=[10, 20, 30, 60, 120])
def fetch_hypurrfi_pools() -> list[dict[str, Any]]:
    """Fetch pools from HypurrFi."""
    client = HypurrFiClient()
    return client.fetch_pools()


@task(retries=5, retry_delay_seconds=[10, 20, 30, 60, 120])
def fetch_hyperbeat_pools() -> list[dict[str, Any]]:
    """Fetch pools from Hyperbeat."""
    client = HyperbeatClient()
    return client.fetch_pools()


@task
async def persist_evm_pools_task(pools: list[dict[str, Any]]) -> tuple[int, int]:
    """Prefect task wrapper for DB persistence."""
    return await persist_evm_pools(pools)



@flow(name="evm-pools-sync", log_prints=True)
async def sync_evm_pools_flow(*, persist: bool = True) -> tuple[int, int]:
    """Hourly: Fetch pools for Hyperliquid/HyperEVM."""
    logger = get_run_logger()
    
    # --- CRITICAL FIX: Run Sequentially to avoid RPC Rate Limits ---
    # Do NOT use .submit() here. Running these in parallel triggers the 
    # global 100 req/min limit immediately.
    
    logger.info("Starting sequential fetch...")
    
    # 1. DeFi Llama (Async)
    pools_dl = await fetch_defillama_pools()
    logger.info(f"DeFi Llama fetched {len(pools_dl)} pools")

    # 2. Felix
    # Run in thread explicitly if needed, or just direct call if task allows
    pools_felix = fetch_felix_pools() 
    logger.info(f"Felix fetched {len(pools_felix)} pools")

    # 3. Hyperlend
    pools_hl = fetch_hyperlend_pools()
    logger.info(f"Hyperlend fetched {len(pools_hl)} pools")

    # 4. HypurrFi
    pools_hf = fetch_hypurrfi_pools()
    logger.info(f"HypurrFi fetched {len(pools_hf)} pools")

    # 5. Hyperbeat
    pools_hb = fetch_hyperbeat_pools()
    logger.info(f"Hyperbeat fetched {len(pools_hb)} pools")
    
    # ... (Keep existing deduplication and persistence logic) ...
    all_pools_list = pools_dl + pools_felix + pools_hl + pools_hf + pools_hb
    
    # Deduplicate by pool_id.
    # Using a dict to keep the *last* seen version.
    # Order matters: If we want Client data to override DefiLlama, put Clients last.
    # Currently order is DL -> Felix -> HL -> HF -> HB.
    # This assumes Client data is better.
    
    by_id: dict[str, dict[str, Any]] = {}

    # Initialize clients to get expected counts
    client_felix = FelixClient()
    client_hb = HyperbeatClient()
    # Hyperlend/HypurrFi are dynamic, so expected is unknown/dynamic
    
    # First pass: Populate with all.
    # Since pool_id is what matters.
    # Note: DefiLlama might use a different pool_id format than our clients?
    # Clients use contract_address/asset_address as pool_id.
    # DefiLlama usually uses "0x..." address or "project-slug".
    # Assuming DefiLlama uses address for EVM pools.
    
    for p in all_pools_list:
        pid = p.get("pool") or p.get("pool_id")
        if pid:
            # Normalize to lower case string for comparison?
            # DB is case sensitive? But addresses usually checksummed.
            # Best to trust the source's formatting but convert to string.
            pid_str = str(pid)
            
            # Use 'pool_id' key if 'pool' is missing (Client data uses 'pool_id')
            if "pool" not in p:
                p["pool"] = pid_str
                
            by_id[pid_str] = p

    pools = list(by_id.values())

    logger.info(
        f"Fetched {len(pools)} EVM pools total ("
        f"DL: {len(pools_dl)}, "
        f"Felix: {len(pools_felix)}/{client_felix.expected_count}, "
        f"HL: {len(pools_hl)}, "
        f"HF: {len(pools_hf)}, "
        f"HB: {len(pools_hb)}/{client_hb.expected_count})"
    )

    if not persist:
        # Dry run stats
        return (len(build_evm_pool_rows(pools)), len(build_evm_pool_metric_rows(pools)))

    return await persist_evm_pools_task(pools)

