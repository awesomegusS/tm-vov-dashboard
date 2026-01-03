"""
Script is a prefect workflow that fetches all vaults (new and old) on hyperliquid,
vault details and UPSERTS the database with the latest basic info and vault details for each vault
Returns: None

Usage: 
"""
import argparse
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from prefect import flow, task, get_run_logger
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from src.services.hyperliquid import HyperliquidClient
from src.core.database import AsyncSessionLocal
from src.models.vault import Vault, VaultMetric, Top500Vault




def _convert_millis_to_datetime(v: Dict[str, Any]):
    ts = v.get("createTimeMillis")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts) / 1000.0, tz=timezone.utc)
        except Exception:
            return None
    return None

def build_vault_rows(vaults_json: List[Dict[str, Any]]):
    logger = get_run_logger()
    rows = []

    # build summary records
    for v in vaults_json:
        summary = (v or {}).get("summary") or {}
        addr = summary.get("vaultAddress") or v.get("vaultAddress")
        if not addr:
            continue
        rows.append(
            {
                "vault_address": addr,
                "name": summary.get("name") or v.get("name"),
                "leader_address": summary.get("leader") or v.get("leader"),
                "description": v.get("description") or summary.get("description"),
                "tvl_usd": summary.get("tvl"),
                "is_closed": summary.get("isClosed") or v.get("isClosed") or False,
                "relationship_type": (v.get("relationship") or {}).get("type") or summary.get("relationshipType"),
                "vault_create_time": _convert_millis_to_datetime(v),
                "created_at":  datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        ) 
    logger.info(f"Built {len(rows)} vaults")
    return rows


async def upsert_vault_rows(rows: List[Dict[str, Any]]):
    logger = get_run_logger()
    # Insert in batches to avoid exceeding DB parameter limits
    BATCH = 1000
    async with AsyncSessionLocal() as session:
        async with session.begin():
            for i in range(0, len(rows), BATCH):
                chunk = rows[i : i + BATCH]
                if not chunk:
                    continue
                stmt = insert(Vault).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[Vault.vault_address],
                    set_={
                        "name": stmt.excluded.name,
                        "leader_address": stmt.excluded.leader_address,
                        "is_closed": stmt.excluded.is_closed,
                        "description": stmt.excluded.description,
                        "tvl_usd": stmt.excluded.tvl_usd,
                        "relationship_type": stmt.excluded.relationship_type,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)

    logger.info(f"Upserted {len(rows)} vaults")
    return len(rows)


def _extract_pnl(portfolio: Dict , period_key: str):
    try:
        for pair in (portfolio or []):
            if not pair:
                continue
            key = pair[0]
            if key == period_key:
                body = pair[1] if len(pair) > 1 else {}
                pnl_history = body.get("pnlHistory") or []
                if pnl_history:
                    last = pnl_history[-1]
                    return float(last[1])
        return None
    except Exception:
        return None
            

def _calculate_max_drawdown(portfolio: Dict, period_key: str):
    try:
        for pair in (portfolio or []):
            if not pair:
                continue
            key = pair[0]
            if key == period_key:
                body = pair[1] if len(pair) > 1 else {}
                accValHist = body.get("accountValueHistory") or []
                peak = float("-inf")
                mdd = 0.0  # as a negative number (or keep as positive)
                for accVal in accValHist:
                    _, value = accVal.items()
                    peak = max(peak, accVal)
                    dd = (accVal - peak) / peak  # negative or 0
                    mdd = min(mdd, dd)
        return -mdd  # positive fraction, e.g. 0.256 = 25.6%
    except Exception:
        return None
            

def _extract_volume(portfolio: Dict, period_key: str):
    try:
        for pair in (portfolio or []):
            if not pair:
                continue
            key = pair[0]

            # select period
            if key == period_key:
                body = pair[1] if len(pair) > 1 else {}
                vlm = body.get("vlm") or []
        return vlm
    except Exception:
        return None

def _extract_timestamp(portfolio: Dict):
    try:
        if not portfolio:
            raise Exception  
        
        pnlHist = portfolio[1].get('pnlHistory')
        timestamp = pnlHist[-1][0] # fetch the last timestamp as of, it's global accross all history last object, also datetime.now() | when a request was sent to the endpoint
        return timestamp
    except Exception as e: # should refactor
        return None

def build_metric_rows_from_details(details_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    out: List[Dict[str, Any]] = []
    for addr, data in details_map.items():
        if not data or (isinstance(data, dict) and data.get("error")):
            continue
        v = data
        follower_list = v.get("followers") or []
        follower_count = len(follower_list) if isinstance(follower_list, list) else None

        portfolio = v.get("portfolio") or []
        out.append(
            {
                "timestampz": _extract_timestamp(portfolio), # use any of the last portfolio historical timestamp values 
                "vault_address": addr,

                "max_distributable_tvl": float(v.get("maxDistributable", 0) or 0),
                "apr": float(v.get("apr")) if v.get("apr") is not None else None,
                "leader_commission": float(v.get("leaderCommission")) if v.get("leaderCommission") is not None else None,
                "follower_count": follower_count,
                
                "pnl_day": _extract_pnl(portfolio, "day"),
                "pnl_week": _extract_pnl(portfolio, "week"),
                "pnl_month": _extract_pnl(portfolio, "month"),
                "pnl_all_time": _extract_pnl(portfolio, "allTime"),

                "vlm_day":_extract_volume(portfolio, "day"),
                "vlm_week":  _extract_volume(portfolio, "week"),
                "vlm_month":  _extract_volume(portfolio, "month"),
                "vlm_all_time": _extract_volume(portfolio, "allTime"),
                
                "max_drawdown_day": _calculate_max_drawdown(portfolio, "day"),
                "max_drawdown_week": _calculate_max_drawdown(portfolio, "week"),
                "max_drawdown_month": _calculate_max_drawdown(portfolio, "month"),
                "max_drawdown_all_time": _calculate_max_drawdown(portfolio, "allTime"),
                
                "created_at": now,
                "updated_at": now,
            }
        )
    return out


@task
async def upsert_metric_rows(rows: List[Dict[str, Any]]):
    logger = get_run_logger()
    if not rows:
        logger.info("No metric rows to insert")
        return 0
    
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # await session.execute(insert(VaultMetric), rows)
            # do upsert here
            stmt = insert(VaultMetric).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=[VaultMetric.timestampz, VaultMetric.vault_address],
                set_={
                    "apr": stmt.excluded.apr,
                    "max_distributable_tvl": stmt.excluded.max_distributable_tvl,
                    "leader_commission": stmt.excluded.leader_commission,
                    "follower_count": stmt.excluded.follower_count,

                    "pnl_day": stmt.excluded.pnl_day,
                    "pnl_week": stmt.excluded.pnl_week,
                    "pnl_month": stmt.excluded.pnl_month,
                    "pnl_all_time": stmt.excluded.pnl_all_time,

                    "vlm_day": stmt.excluded.vlm_day,
                    "vlm_week": stmt.excluded.vlm_week,
                    "vlm_month": stmt.excluded.vlm_month,
                    "vlm_all_time": stmt.excluded.vlm_all_time,

                    "max_drawdown_day": stmt.excluded.max_drawdown_day,
                    "max_drawdown_week": stmt.excluded.max_drawdown_week,
                    "max_drawdown_month": stmt.excluded.max_drawdown_month,
                    "max_drawdown_all_time": stmt.excluded.max_drawdown_all_time,
                    
                    "updated_at": stmt.excluded.updated_at
                },
            )
            await session.execute(stmt)

    logger.info(f"Inserted {len(rows)} metric rows")
    return len(rows)



def _extract_addresses_from_vaults_json(vaults: List[Dict[str, Any]]) -> List[str]:
    addrs: List[str] = []
    for v in vaults:
        summary = (v or {}).get("summary") or {}
        addr = summary.get("vaultAddress") or v.get("vaultAddress")
        if addr:
            addrs.append(addr)
    seen = set()
    out: List[str] = []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out

@flow(name="Upsert Vault and Performance Metrics")
async def upsert_vault_metrics_flow(concurrency: int = 10, limit: Optional[int] = None):
    """Every 1 hour: Get latest vault info and perf metrics for all vaults"""
    logger = get_run_logger()
    client = HyperliquidClient()

    # Always fetch the canonical vault list from stats for reliability in
    # Prefect-managed workers (repo clones won't contain generated data/ files).

    # upsert basic vaults info
    vaults_json = await asyncio.to_thread(client.fetch_all_stats)
    vault_rows = build_vault_rows(vaults_json)
    await upsert_vault_rows(vault_rows)

    # upsert vault performance
    addrs = _extract_addresses_from_vaults_json(vaults_json)
    if limit:
        addrs = addrs[:limit]
    logger.info(f"Fetching details for {len(addrs)} addresses (concurrency={concurrency})")
    details = await client.fetch_vault_details_batch(addrs, concurrency=concurrency)

    rows = build_metric_rows_from_details(details)
    await upsert_metric_rows(rows)
    logger.info("Upsert vault and metrics complete")


@task
async def update_top_500():
    logger = get_run_logger()
    now = datetime.now(timezone.utc)

    sql = text(
        """
                WITH latest AS (
                    SELECT
                        vault_address,
                        max_distributable_tvl,
                        time,
                        ROW_NUMBER() OVER (PARTITION BY vault_address ORDER BY time DESC) AS rn
                    FROM hyperliquid_vaults_discovery.vault_metrics
                )
                SELECT vault_address, max_distributable_tvl, time
        FROM latest
        WHERE rn = 1
                ORDER BY max_distributable_tvl DESC NULLS LAST
        LIMIT 500
        """
    )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            res = await session.execute(sql)
            rows = list(res.fetchall())

            await session.execute(text("DELETE FROM hyperliquid_vaults_discovery.top_500_vaults"))

            payload = []
            for i, (vault_address, tvl_usd, metrics_time) in enumerate(rows, start=1):
                payload.append(
                    {
                        "vault_address": vault_address,
                        "rank": i,
                        "tvl_usd": tvl_usd,
                        "metrics_time": metrics_time,
                        "updated_at": now,
                    }
                )

            if payload:
                await session.execute(insert(Top500Vault).values(payload))

    logger.info(f"Wrote {len(rows)} rows to top_500_vaults")
    return len(rows)

@flow(name="get top 500 vaults by TVL ", log_prints=True)
async def update_top_500_flow():
    logger = get_run_logger()
    """Every 4 hours: Fetch details for top 500 vaults by TVL."""
    n = await update_top_500()
    logger.info(f"Updated top 500 vaults by TVL ({n})")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    asyncio.run(upsert_vault_metrics_flow(concurrency=args.concurrency, limit=args.limit))


if __name__ == "__main__":
    main()
