import asyncio
import httpx
import requests
from typing import List, Dict, Any

# Canonical stats endpoint (keeps the same as ingest)
VAULTS_STATS_URL = "https://stats-data.hyperliquid.xyz/Mainnet/vaults"
API_BASE = "https://api.hyperliquid.xyz"


class HyperliquidClient:
    """Client for Hyperliquid: stats endpoint and /info API.

    Provides:
    - `fetch_all_stats()` synchronous: fetch the canonical vaults JSON.
    - `fetch_vault_details_batch()` async: concurrently POST to /info for details.
    """

    def __init__(self, timeout: int = 30, stats_url: str = VAULTS_STATS_URL, api_base: str = API_BASE):
        self.timeout = timeout
        self.stats_url = stats_url
        self.api_base = api_base.rstrip("/")

    def fetch_all_stats(self) -> List[Dict[str, Any]]:
        """Synchronous fetch of the full stats JSON (list of vault objects)."""
        r = requests.get(self.stats_url, headers={"Accept": "application/json"}, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise ValueError(f"expected a JSON list from {self.stats_url}")
        return data

    async def fetch_vault_details_batch(self, addresses: List[str], concurrency: int = 20, timeout: int = 30) -> Dict[str, Any]:
        """Async fetch of vault details for multiple addresses via POST /info.

        Returns a dict mapping address -> payload or {'error': msg}.
        """
        sem = asyncio.Semaphore(concurrency)  # type: ignore[name-defined]
        results: Dict[str, Any] = {}

        async with httpx.AsyncClient(timeout=timeout, base_url=self.api_base) as client:

            async def worker(addr: str):
                async with sem:
                    try:
                        r = await client.post("/info", json={"type": "vaultDetails", "vaultAddress": addr})
                        r.raise_for_status()
                        results[addr] = r.json()
                    except Exception as e:
                        results[addr] = {"error": str(e)}

            tasks = [asyncio.create_task(worker(a)) for a in addresses]
            await asyncio.gather(*tasks)

        return results