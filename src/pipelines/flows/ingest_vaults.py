import asyncio
from datetime import datetime, timezone
from prefect import flow, task, get_run_logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

# Internal modules
from src.core.database import AsyncSessionLocal
from src.services.hyperliquid import HyperliquidClient
from src.models.vault import Vault, VaultMetric

@task(retries=3, retry_delay_seconds=10)
async def fetch_hypercore_vaults():
    """
    Fetches the raw list of ~3,000 vaults from Hyperliquid.
    Retries automatically if the API blips.
    """
    logger = get_run_logger()
    client = HyperliquidClient()
    
    logger.info("Requesting vault summaries via SDK...")
    
    try:
        # Run blocking SDK call in thread
        data = await asyncio.to_thread(client.fetch_vault_summaries)
    except Exception as e:
        # Catch connection errors (like 403 Forbidden)
        logger.error(f"API Connection Error: {e}")
        raise

    if not data:
        # Ensure we log clearly that this is likely a geo-block issue
        logger.error("⚠️ API returned 0 vaults. If you are in the US, you are likely GEO-BLOCKED.")
        raise ValueError("SDK returned empty list. Check VPN or Region.")

    logger.info(f"Successfully fetched {len(data)} vaults.")
    return data

@task
async def upsert_vault_data(raw_data: list):
    """
    Updates the 'vaults' table (metadata) and inserts new rows into 
    'vault_metrics' (time-series).
    """
    logger = get_run_logger()
    if not raw_data:
        logger.warning("⚠️ No vault data fetched! Skipping upsert to avoid DB crash.")
        return
    
    # 1. Prepare Data Containers
    vault_records = []
    metric_records = []
    current_time = datetime.now(timezone.utc)

    for item in raw_data:
        # Skip if necessary, though ingestion usually grabs everything 
        # for historical tracking.
        
        # Prepare Metadata (Vaults Table)
        # Note: API field names map to our DB columns here
        vault_records.append({
            "vault_address": item["vaultAddress"],
            "name": item.get("name"),
            "leader_address": item.get("leader"),
            "is_closed": item.get("isClosed", False),
            # 'createTimeMillis' comes as int, convert if needed or store as is
            # For this MVP we focus on the core fields
        })

        # Prepare Metrics (VaultMetrics Table)
        # We assume 'tvl' comes as a string/float from API
        metric_records.append({
            "time": current_time,
            "vault_address": item["vaultAddress"],
            "tvl_usd": float(item.get("tvl", 0) or 0),
            # We will fetch detailed APR in a separate sub-flow later 
            # if it's not in the summary endpoint
            "apr": None 
        })

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # --- A. UPSERT Metadata (Vaults) ---
            # If vault exists, update mutable fields (name, leader, closed status)
            stmt_vaults = insert(Vault).values(vault_records)
            stmt_vaults = stmt_vaults.on_conflict_do_update(
                index_elements=[Vault.vault_address],
                set_={
                    "name": stmt_vaults.excluded.name,
                    "leader_address": stmt_vaults.excluded.leader_address,
                    "is_closed": stmt_vaults.excluded.is_closed,
                }
            )
            await session.execute(stmt_vaults)
            
            # --- B. INSERT Metrics (Time-series) ---
            # TimescaleDB is append-only for metrics; we just insert.
            if metric_records:
                await session.execute(insert(VaultMetric), metric_records)

    logger.info(f"Upserted {len(vault_records)} vaults and recorded {len(metric_records)} metric points.")

@flow(name="HyperCore Ingestion", log_prints=True)
async def ingest_hypercore_vaults():
    """
    Main orchestration flow for Phase 1.
    """
    logger = get_run_logger()
    logger.info("Starting HyperCore Vault Ingestion Phase 1...")
    
    # 1. Fetch
    raw_vaults = await fetch_hypercore_vaults()
    
    # 2. Process & Store
    await upsert_vault_data(raw_vaults)
    
    logger.info("Ingestion complete.")

if __name__ == "__main__":
    # Local development run
    asyncio.run(ingest_hypercore_vaults())