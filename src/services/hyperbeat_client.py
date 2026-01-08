from decimal import Decimal
import time
import logging
from typing import Any, List, Dict
from web3 import Web3

logger = logging.getLogger(__name__)

class HyperbeatClient:
    # --- CONFIGURATION ---
    RPC_URL = "https://rpc.hyperliquid.xyz/evm"
    PROTOCOL_NAME = "Hyperbeat"

    # Shared Oracle (Hyperlend) for pricing (Shared Infrastructure)
    ORACLE_ADDRESS = "0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e"

    # --- VAULT LIST ---
    VAULTS = {
        "HYPE Vault": "0x96c6cbb6251ee1c257b2162ca0f39aa5fa44b1fb",
        "UBTC Vault": "0xc061d38903b99ac12713b550c2cb44b221674f94",
        "USDT Vault": "0x5e105266db42f78fa814322bce7f388b4c2e61eb",
        "XAUt Vault": "0x6EB6724D8D3D4FF9E24d872E8c38403169dC05f8",
        "LST Vault":  "0x81e064d0eB539de7c3170EDF38C1A42CBd752A76",
        "liquidHYPE": "0x441794d6a8f9a3739f5d4e98a728937b33489d29",
        "Ventuals VLP": "0xD66d69c288d9a6FD735d7bE8b2e389970fC4fD42",
        "dnHYPE":     "0x949a7250Bb55Eb79BC6bCC97fcD1C473DB3e6F29",
        "dnPUMP":     "0x8858A307a85982c2B3CB2AcE1720237f2f09c39B",
        "USDC Vault": "0x057ced81348D57Aad579A672d521d7b4396E8a61",
        "wNLP":       "0x4Cc221cf1444333510a634CE0D8209D2D11B9bbA"
    }

    # --- ABIS ---
    ABI_VAULT = [
        {"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"asset","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"totalAssets","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
    ]

    ABI_ERC20 = [
        {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"}
    ]

    ABI_ORACLE = [
        {"inputs":[{"internalType":"address","name":"asset","type":"address"}],"name":"getAssetPrice","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
    ]

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(self.RPC_URL))
        self.oracle_address = Web3.to_checksum_address(self.ORACLE_ADDRESS)

    def _call_with_retry(self, contract_func, max_retries=5, initial_delay=2):
        for attempt in range(max_retries):
            try:
                return contract_func.call()
            except Exception as e:
                error_str = str(e).lower()
                if "rate limited" in error_str or "-32005" in error_str:
                    delay = initial_delay * (attempt + 1)
                    logger.warning(f"Rate limit hit in HyperbeatClient. Sleeping {delay}s before retry {attempt+1}/{max_retries}...")
                    time.sleep(delay)
                else:
                    raise e
        raise Exception(f"Failed after {max_retries} retries due to rate limits.")

    def fetch_pools(self) -> List[Dict[str, Any]]:
        if not self.w3.is_connected():
            logger.error("Failed to connect to Hyperbeat.")
            return []

        logger.info(f"Connected to HyperEVM ({self.PROTOCOL_NAME}). Block: {self.w3.eth.block_number}")
        
        oracle_contract = self.w3.eth.contract(address=self.oracle_address, abi=self.ABI_ORACLE)
        results = []

        for vault_label, vault_addr_raw in self.VAULTS.items():
            try:
                vault_addr = Web3.to_checksum_address(vault_addr_raw)
                vault_contract = self.w3.eth.contract(address=vault_addr, abi=self.ABI_VAULT)

                # Fetch basic info
                name = self._call_with_retry(vault_contract.functions.name())
                symbol = self._call_with_retry(vault_contract.functions.symbol())
                decimals = self._call_with_retry(vault_contract.functions.decimals())
                asset_addr = self._call_with_retry(vault_contract.functions.asset())
                
                total_assets = self._call_with_retry(vault_contract.functions.totalAssets())
                # totalSupply = self._call_with_retry(vault_contract.functions.totalSupply()) # Not used for TVL calc in script

                # Get Price from Oracle
                price_raw = self._call_with_retry(oracle_contract.functions.getAssetPrice(asset_addr))
                price_usd = Decimal(price_raw) / Decimal(10**8)

                # Calculations
                tvl_usd = (Decimal(total_assets) / Decimal(10**decimals)) * price_usd

                accepts_usdc = True if "USDC" in symbol.upper() else False

                data_row = {
                    "source": "hyperbeat",
                    "protocol": self.PROTOCOL_NAME,
                    "pool_id": vault_addr,  # Using vault address as ID since it's unique
                    "symbol": symbol,
                    "name": name,  # Or vault_label if preferred, but contract name is better
                    "contract_address": vault_addr,
                    "accepts_usdc": accepts_usdc,
                    "tvl_usd": float(tvl_usd),
                    "total_debt_usd": 0.0, # Not applicable/available
                    "utilization_rate": 0.0,
                    "apy_base": 0.0, # Not available
                    "apy_reward": 0.0,
                    "apy_total": 0.0,
                    "apy_borrow_variable": 0.0,
                    "apy_borrow_stable": 0.0,
                    "ltv": 0.0,
                    "liquidation_threshold": 0.0,
                    "liquidation_bonus": 0.0,
                    "decimals": decimals,
                    "reserve_factor": 0.0
                }
                results.append(data_row)

            except Exception as e:
                logger.error(f"Error processing {vault_label} ({vault_addr_raw}): {e}")
                # Continue
        
        return results
