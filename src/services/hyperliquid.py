from hyperliquid.info import Info
from hyperliquid.utils import constants

class HyperliquidClient:
    def __init__(self):
        # The SDK handles the base URL and headers automatically
        self.info = Info(constants.MAINNET_API_URL, skip_ws=True)

    def fetch_vault_summaries(self) -> list:
        """
        Fetch all ~3,000 vaults using the official SDK.
        """
        # The SDK's 'post' method automatically handles the /info endpoint logic
        # and headers that were causing the empty list issue.
        return self.info.post("/info", {"type": "vaultSummaries"})

    def fetch_vault_details(self, vault_address: str) -> dict:
        """
        Fetch granular data for a specific vault.
        """
        return self.info.vault_details(vault_address)