import argparse
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from prefect import flow, task, get_run_logger
from sqlalchemy.dialects.postgresql import insert

from src.services.hyperliquid import HyperliquidClient
from src.core.database import AsyncSessionLocal
from src.models.vault import VaultMetric


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


@flow(name="Upsert Vault Metrics (info to vault_metrics)")
async def upsert_vault_metrics_flow(vaults_json: str = "data/vaults-latest.json", concurrency: int = 10, limit: Optional[int] = None):
    logger = get_run_logger()
    p = Path(vaults_json)
    if not p.exists():
        raise SystemExit(f"Vaults file not found: {p}")

    addrs = extract_addresses_from_json(p)
    if limit:
        addrs = addrs[:limit]

    client = HyperliquidClient()
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
