import argparse
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from prefect import flow, task, get_run_logger
from sqlalchemy.dialects.postgresql import insert

from src.services.hyperliquid import HyperliquidClient
from src.core.database import AsyncSessionLocal
from src.models.vault import Vault, VaultMetric


def extract_addresses_from_json(path: Path) -> List[str]:
    data = __import__("json").loads(path.read_text())
    addrs = []
    for v in data:
        summary = (v or {}).get("summary") or {}
        addr = summary.get("vaultAddress")
        if addr:
            addrs.append(addr)
    seen = set()
    out = []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def extract_addresses_from_stats(vaults: List[Dict[str, Any]]) -> List[str]:
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


def build_metric_rows_from_details(details_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    out: List[Dict[str, Any]] = []
    for addr, data in details_map.items():
        if not data or (isinstance(data, dict) and data.get("error")):
            continue
        v = data
        follower_list = v.get("followers") or []
        follower_count = len(follower_list) if isinstance(follower_list, list) else None

        def extract_pnl(portfolio, period_key: str):
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

        portfolio = v.get("portfolio") or []
        out.append(
            {
                "time": now,
                "vault_address": addr,
                "tvl_usd": float(v.get("tvl", 0) or 0),
                "apr": float(v.get("apr")) if v.get("apr") is not None else None,
                "leader_commission": float(v.get("leaderCommission")) if v.get("leaderCommission") is not None else None,
                "follower_count": follower_count,
                "pnl_day": extract_pnl(portfolio, "day"),
                "pnl_week": extract_pnl(portfolio, "week"),
                "pnl_month": extract_pnl(portfolio, "month"),
                "pnl_all_time": extract_pnl(portfolio, "allTime"),
                "updated_at": now,
            }
        )
    return out


@task
async def insert_metric_rows(rows: List[Dict[str, Any]]):
    logger = get_run_logger()
    if not rows:
        logger.info("No metric rows to insert")
        return 0
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(insert(VaultMetric), rows)
    logger.info(f"Inserted {len(rows)} metric rows")
    return len(rows)


@task
async def upsert_vault_rows_from_stats(vaults: List[Dict[str, Any]]):
    """Ensure vaults exist before inserting metrics (avoids FK violations)."""
    logger = get_run_logger()
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    rows: List[Dict[str, Any]] = []
    for v in vaults:
        summary = (v or {}).get("summary") or {}
        addr = summary.get("vaultAddress") or v.get("vaultAddress")
        if not addr:
            continue
        rows.append(
            {
                "vault_address": addr,
                "name": summary.get("name") or v.get("name"),
                "leader_address": summary.get("leader") or v.get("leader"),
                "is_closed": summary.get("isClosed") or v.get("isClosed") or False,
                "updated_at": now,
            }
        )

    if not rows:
        logger.warning("No vault rows to upsert")
        return 0

    BATCH = 1000
    async with AsyncSessionLocal() as session:
        async with session.begin():
            for i in range(0, len(rows), BATCH):
                chunk = rows[i : i + BATCH]
                stmt = insert(Vault).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[Vault.vault_address],
                    set_={
                        "name": stmt.excluded.name,
                        "leader_address": stmt.excluded.leader_address,
                        "is_closed": stmt.excluded.is_closed,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)

    logger.info(f"Upserted {len(rows)} vaults (pre-metrics)")
    return len(rows)


@flow(name="Upsert Vault Metrics (info to vault_metrics)")
async def upsert_vault_metrics_flow(vaults_json: str = "data/vaults-latest.json", concurrency: int = 10, limit: Optional[int] = None):
    logger = get_run_logger()
    p = Path(vaults_json)

    client = HyperliquidClient()

    # Always fetch the canonical vault list from stats for reliability in
    # Prefect-managed workers (repo clones won't contain generated data/ files).
    vaults_stats = await asyncio.to_thread(client.fetch_all_stats)
    await upsert_vault_rows_from_stats(vaults_stats)

    if p.exists():
        addrs = extract_addresses_from_json(p)
    else:
        logger.warning(f"Vaults file not found: {p}; falling back to stats endpoint")
        addrs = extract_addresses_from_stats(vaults_stats)

    if limit:
        addrs = addrs[:limit]
    logger.info(f"Fetching details for {len(addrs)} addresses (concurrency={concurrency})")
    details = await client.fetch_vault_details_batch(addrs, concurrency=concurrency)
    rows = build_metric_rows_from_details(details)
    await insert_metric_rows(rows)
    logger.info("Upsert vault metrics complete")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vaults", default="data/vaults-latest.json")
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    asyncio.run(upsert_vault_metrics_flow(vaults_json=args.vaults, concurrency=args.concurrency, limit=args.limit))


if __name__ == "__main__":
    main()
