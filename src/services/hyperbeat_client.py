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
    ORACLE_ADDRESS = "0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e"

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

    # Standard ERC20/4626 interfaces
    ABI_VAULT = [
        {"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"asset","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"totalAssets","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
    ]
    ABI_ORACLE = [
        {"inputs":[{"internalType":"address","name":"asset","type":"address"}],"name":"getAssetPrice","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
    ]

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(self.RPC_URL))
        self.oracle_address = Web3.to_checksum_address(self.ORACLE_ADDRESS)

    @property
    def expected_count(self) -> int:
        return len(self.VAULTS)

    # def _call_with_retry(self, contract_func, max_retries=5):
    #     # Exponential Backoff: 2s, 4s, 8s, 16s, 32s
    #     for attempt in range(max_retries):
    #         try:
    #             return contract_func.call()
    #         except Exception as e:
    #             error_str = str(e).lower()
    #             if "rate limited" in error_str or "-32005" in error_str:
    #                 delay = 2 ** (attempt + 1)
    #                 logger.warning(f"Rate limit in Hyperbeat. Sleeping {delay}s...")
    #                 time.sleep(delay)
    #             else:
    #                 raise e
    #     raise Exception(f"Failed after {max_retries} retries")
    
    def _call_with_retry(self, contract_func, max_retries=5):
        for attempt in range(max_retries):
            try:
                return contract_func.call()
            except Exception as e:
                error_str = str(e).lower()
                # Check for rate limit specific codes/messages
                if "rate limited" in error_str or "-32005" in error_str:
                    # Exponential Backoff: 2, 4, 8, 16, 32 seconds
                    delay = 2 ** (attempt + 1)
                    logger.warning(f"Rate limit hit. Sleeping {delay}s...")
                    time.sleep(delay)
                else:
                    raise e
        raise Exception("Failed after max retries")

    def fetch_pools(self) -> List[Dict[str, Any]]:
        if not self.w3.is_connected():
            return []

        logger.info(f"Connected to Hyperbeat RPC")
        oracle_contract = self.w3.eth.contract(address=self.oracle_address, abi=self.ABI_ORACLE)
        results = []

        for vault_label, vault_addr_raw in self.VAULTS.items():
            try:
                # Polite Delay between vaults
                time.sleep(0.5)

                vault_addr = Web3.to_checksum_address(vault_addr_raw)
                vault_contract = self.w3.eth.contract(address=vault_addr, abi=self.ABI_VAULT)

                # 1. Basic Info (Safe Fetch)
                try:
                    symbol = self._call_with_retry(vault_contract.functions.symbol())
                except:
                    symbol = "UNKNOWN"
                
                try:
                    name = self._call_with_retry(vault_contract.functions.name())
                except:
                    name = vault_label

                # 2. Identify Underlying Asset (Robust Fallback)
                is_erc4626 = False
                try:
                    # Try getting underlying asset
                    asset_addr = self._call_with_retry(vault_contract.functions.asset())
                    is_erc4626 = True
                except:
                    # Fallback: The vault IS the asset (e.g. dnTokens)
                    asset_addr = vault_addr
                    is_erc4626 = False

                # 3. Get Decimals
                try:
                    if is_erc4626:
                        # Create temp contract for underlying to get its decimals
                        # Simplified: assume same ABI works
                        asset_c = self.w3.eth.contract(address=asset_addr, abi=self.ABI_VAULT)
                        decimals = self._call_with_retry(asset_c.functions.decimals())
                    else:
                        decimals = self._call_with_retry(vault_contract.functions.decimals())
                except:
                    decimals = 18 # Default

                # 4. Get Balance (TVL)
                # Try totalAssets (ERC4626), failover to totalSupply (Standard)
                try:
                    raw_balance = self._call_with_retry(vault_contract.functions.totalAssets())
                except:
                    try:
                        raw_balance = self._call_with_retry(vault_contract.functions.totalSupply())
                    except:
                        raw_balance = 0

                # 5. Get Price
                try:
                    price_raw = self._call_with_retry(oracle_contract.functions.getAssetPrice(asset_addr))
                    price_usd = Decimal(price_raw) / Decimal(10**8)
                except:
                    price_usd = Decimal(0)

                # 6. Calculate
                tvl_usd = (Decimal(raw_balance) / Decimal(10**decimals)) * price_usd
                accepts_usdc = True if "USDC" in symbol.upper() else False

                results.append({
                    "source": "hyperbeat",
                    "protocol": self.PROTOCOL_NAME,
                    "pool_id": vault_addr,
                    "symbol": symbol,
                    "name": name,
                    "contract_address": vault_addr,
                    "accepts_usdc": accepts_usdc,
                    "tvl_usd": float(tvl_usd),
                    "total_debt_usd": 0.0,
                    "utilization_rate": 0.0,
                    "apy_base": 0.0,
                    "apy_reward": 0.0,
                    "apy_total": 0.0,
                    "apy_borrow_variable": 0.0,
                    "apy_borrow_stable": 0.0,
                    "ltv": 0.0,
                    "liquidation_threshold": 0.0,
                    "liquidation_bonus": 0.0,
                    "decimals": decimals,
                    "reserve_factor": 0.0
                })

            except Exception as e:
                # Log but do not crash the flow
                logger.error(f"Error processing {vault_label}: {e}")
                continue
        
        return results