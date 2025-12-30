import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from prefect import flow, task, get_run_logger
from sqlalchemy.dialects.postgresql import insert

from src.core.database import AsyncSessionLocal
from src.models.vault import Vault
from src.services.hyperliquid import HyperliquidClient


def build_summary_rows(vaults: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for v in vaults:
        summary = (v or {}).get("summary") or {}
        rows.append(
            {
                "name": summary.get("name"),
                "vaultAddress": summary.get("vaultAddress"),
                "leader": summary.get("leader"),
                "tvl": summary.get("tvl"),
                "isClosed": summary.get("isClosed"),
                "createTimeMillis": summary.get("createTimeMillis"),
                "apr": v.get("apr"),
            }
        )
    return rows


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


@task
def write_out_files(vaults: List[Dict[str, Any]], out_dir: str = "data") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    write_json(out / f"vaults-{ts}.json", vaults)
    write_json(out / "vaults-latest.json", vaults)
    summary_rows = build_summary_rows(vaults)
    write_json(out / "vaults-summary-latest.json", summary_rows)
    get_run_logger().info(f"Wrote {len(vaults)} vaults to {out}")


def _extract_created_at(v: Dict[str, Any]):
    ts = (v or {}).get("summary", {}).get("createTimeMillis") or v.get("createTimeMillis")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts) / 1000.0, tz=timezone.utc)
        except Exception:
            return None
    return None


@task
async def upsert_vault_records(vaults: List[Dict[str, Any]]):
    logger = get_run_logger()
    rows = []
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
                "description": v.get("description") or summary.get("description"),
                "is_closed": summary.get("isClosed") or v.get("isClosed") or False,
                "relationship_type": (v.get("relationship") or {}).get("type") or summary.get("relationshipType"),
                "created_at": _extract_created_at(v),
                "updated_at": datetime.now(timezone.utc),
            }
        )
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
                        "relationship_type": stmt.excluded.relationship_type,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)

    logger.info(f"Upserted {len(rows)} vaults")
    return len(rows)


@flow(name="Upsert Vaults (stats to vaults table)")
def upsert_vaults_flow(out_dir: str = "data") -> int:
    logger = get_run_logger()
    client = HyperliquidClient()
    vaults = client.fetch_all_stats()
    write_out_files(vaults, out_dir=out_dir)
    # upsert summaries into vaults table
    import asyncio as _asyncio

    _asyncio.run(upsert_vault_records(vaults))
    logger.info("Upsert vaults flow complete")
    return len(vaults)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data")
    args = p.parse_args()
    upsert_vaults_flow(out_dir=args.out_dir)


if __name__ == "__main__":
    main()
