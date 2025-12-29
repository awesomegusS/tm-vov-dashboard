import httpx
from hyperliquid.utils import constants


class HyperliquidClient:
    """A small wrapper that calls the public /info HTTP endpoint.

    We prefer this over the SDK here because some SDK versions
    do not expose the vault helper methods. The endpoint accepts
    JSON payloads like {"type": "vaultSummaries"} and
    {"type": "vaultDetails", "vaultAddress": "0x..."}.
    """

    def __init__(self, timeout: int = 30):
        # The SDK's MAINNET_API_URL may be the root host; the API expects POSTs to /info
        base = str(constants.MAINNET_API_URL)
        self.base_url = base.rstrip('/') + '/info'
        self.timeout = timeout

    def fetch_vault_summaries(self) -> list:
        """Synchronous fetch of all vault summaries.

        This method is intentionally synchronous so callers can
        run it via `asyncio.to_thread` (as used in the Prefect task).
        """
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.base_url, json={"type": "vaultSummaries"})
            resp.raise_for_status()
            return resp.json()

    def fetch_vault_details(self, vault_address: str) -> dict:
        """Synchronous fetch of a single vault's details."""
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                self.base_url,
                json={"type": "vaultDetails", "vaultAddress": vault_address},
            )
            resp.raise_for_status()
            return resp.json()