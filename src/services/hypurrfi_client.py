from decimal import Decimal
import time
import logging
from typing import Any, List, Dict
from web3 import Web3

logger = logging.getLogger(__name__)

class HypurrFiClient:
    # --- CONFIGURATION ---
    RPC_URL = "https://rpc.hyperliquid.xyz/evm"
    POOL_ADDRESSES_PROVIDER = "0xA73ff12D177D8F1Ec938c3ba0e87D33524dD5594"
    PROTOCOL_NAME = "HypurrFi"

    # --- ABIS ---
    ABI_PROVIDER = [
        {"inputs":[],"name":"getPool","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"getPriceOracle","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"}
    ]

    ABI_POOL = [
        {"inputs":[],"name":"getReservesList","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},
        {
            "inputs":[{"internalType":"address","name":"asset","type":"address"}],
            "name":"getReserveData",
            "outputs":[{
                "components":[
                    {"components":[{"internalType":"uint256","name":"data","type":"uint256"}],"internalType":"struct DataTypes.ReserveConfigurationMap","name":"configuration","type":"tuple"},
                    {"internalType":"uint128","name":"liquidityIndex","type":"uint128"},
                    {"internalType":"uint128","name":"currentLiquidityRate","type":"uint128"},
                    {"internalType":"uint128","name":"variableBorrowIndex","type":"uint128"},
                    {"internalType":"uint128","name":"currentVariableBorrowRate","type":"uint128"},
                    {"internalType":"uint128","name":"currentStableBorrowRate","type":"uint128"},
                    {"internalType":"uint40","name":"lastUpdateTimestamp","type":"uint40"},
                    {"internalType":"uint16","name":"id","type":"uint16"},
                    {"internalType":"address","name":"aTokenAddress","type":"address"},
                    {"internalType":"address","name":"stableDebtTokenAddress","type":"address"},
                    {"internalType":"address","name":"variableDebtTokenAddress","type":"address"},
                    {"internalType":"address","name":"interestRateStrategyAddress","type":"address"},
                    {"internalType":"uint128","name":"accruedToTreasury","type":"uint128"},
                    {"internalType":"uint128","name":"unbacked","type":"uint128"},
                    {"internalType":"uint128","name":"isolationModeTotalDebt","type":"uint128"}
                ],
                "internalType":"struct DataTypes.ReserveData",
                "name":"","type":"tuple"
            }],
            "stateMutability":"view","type":"function"
        }
    ]

    ABI_ERC20 = [
        {"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
        {"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
    ]

    ABI_ORACLE = [
        {"inputs":[{"internalType":"address","name":"asset","type":"address"}],"name":"getAssetPrice","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
    ]

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(self.RPC_URL))
        self.pool_addresses_provider = Web3.to_checksum_address(self.POOL_ADDRESSES_PROVIDER)

    # def _call_with_retry(self, contract_func, max_retries=5, initial_delay=2):
    #     for attempt in range(max_retries):
    #         try:
    #             return contract_func.call()
    #         except Exception as e:
    #             error_str = str(e).lower()
    #             if "rate limited" in error_str or "-32005" in error_str:
    #                 delay = initial_delay * (attempt + 1)
    #                 logger.warning(f"Rate limit hit in HypurrFiClient. Sleeping {delay}s before retry {attempt+1}/{max_retries}...")
    #                 time.sleep(delay)
    #             else:
    #                 raise e
    #     raise Exception(f"Failed after {max_retries} retries due to rate limits.")
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

    def _parse_configuration(self, conf_data):
        ltv = (conf_data & 0xFFFF) / 100.0  
        liq_threshold = ((conf_data >> 16) & 0xFFFF) / 100.0
        liq_bonus = ((conf_data >> 32) & 0xFFFF) / 100.0
        decimals = (conf_data >> 48) & 0xFF
        return ltv, liq_threshold, liq_bonus, decimals

    def fetch_pools(self) -> List[Dict[str, Any]]:
        if not self.w3.is_connected():
            logger.error("Failed to connect to HyperEVM RPC")
            return []

        logger.info(f"Connected to HyperEVM ({self.PROTOCOL_NAME}). Block: {self.w3.eth.block_number}")

        provider_contract = self.w3.eth.contract(address=self.pool_addresses_provider, abi=self.ABI_PROVIDER)
        pool_address = self._call_with_retry(provider_contract.functions.getPool())
        oracle_address = self._call_with_retry(provider_contract.functions.getPriceOracle())
        
        pool_contract = self.w3.eth.contract(address=pool_address, abi=self.ABI_POOL)
        oracle_contract = self.w3.eth.contract(address=oracle_address, abi=self.ABI_ORACLE)

        reserves_list = self._call_with_retry(pool_contract.functions.getReservesList())
        logger.info(f"Found {len(reserves_list)} assets for {self.PROTOCOL_NAME}.")

        results = []

        for asset_address in reserves_list:
            try:
                time.sleep(0.5) 

                reserve_data = self._call_with_retry(pool_contract.functions.getReserveData(asset_address))
                
                conf_data = reserve_data[0][0]
                liquidity_rate_ray = reserve_data[2]        
                variable_borrow_rate_ray = reserve_data[4]
                stable_borrow_rate_ray = reserve_data[5] 
                
                h_token_address = reserve_data[8]           
                var_debt_token_address = reserve_data[10]   

                ltv, liq_threshold, liq_bonus, decimals_conf = self._parse_configuration(conf_data)

                # Asset Details
                asset_contract = self.w3.eth.contract(address=asset_address, abi=self.ABI_ERC20)
                symbol = self._call_with_retry(asset_contract.functions.symbol())
                name = self._call_with_retry(asset_contract.functions.name())
                decimals = decimals_conf 

                # Supply & Debt
                h_token_contract = self.w3.eth.contract(address=h_token_address, abi=self.ABI_ERC20)
                total_supply_raw = self._call_with_retry(h_token_contract.functions.totalSupply())

                debt_contract = self.w3.eth.contract(address=var_debt_token_address, abi=self.ABI_ERC20)
                total_debt_raw = self._call_with_retry(debt_contract.functions.totalSupply())

                # Price (8 decimals)
                price_raw = self._call_with_retry(oracle_contract.functions.getAssetPrice(asset_address))
                price_usd = Decimal(price_raw) / Decimal(10**8)

                # Calculations
                tvl_usd = (Decimal(total_supply_raw) / Decimal(10**decimals)) * price_usd
                total_debt_usd = (Decimal(total_debt_raw) / Decimal(10**decimals)) * price_usd

                if total_supply_raw > 0:
                    utilization = (Decimal(total_debt_raw) / Decimal(total_supply_raw)) * 100
                else:
                    utilization = Decimal(0)

                SECONDS_PER_YEAR = 31536000
                
                supply_rate_sec = Decimal(liquidity_rate_ray) / Decimal(10**27) / Decimal(SECONDS_PER_YEAR)
                apy_base = ((1 + supply_rate_sec) ** Decimal(SECONDS_PER_YEAR)) - 1
                apy_base_pct = float(apy_base) * 100
                
                borrow_rate_sec = Decimal(variable_borrow_rate_ray) / Decimal(10**27) / Decimal(SECONDS_PER_YEAR)
                apy_borrow_pct = (float(((1 + borrow_rate_sec) ** Decimal(SECONDS_PER_YEAR)) - 1)) * 100

                stable_borrow_rate_sec = Decimal(stable_borrow_rate_ray) / Decimal(10**27) / Decimal(SECONDS_PER_YEAR)
                apy_borrow_stable_pct = (float(((1 + stable_borrow_rate_sec) ** Decimal(SECONDS_PER_YEAR)) - 1)) * 100

                apy_reward_pct = 0.0 
                apy_total_pct = apy_base_pct + apy_reward_pct

                accepts_usdc = True if "USDC" in symbol.upper() else False

                data_row = {
                    "source": "hypurrfi",
                    "protocol": self.PROTOCOL_NAME,
                    "pool_id": asset_address, 
                    "symbol": symbol,
                    "name": name,
                    "contract_address": h_token_address,
                    "accepts_usdc": accepts_usdc,
                    "tvl_usd": float(tvl_usd),
                    "total_debt_usd": float(total_debt_usd),
                    "utilization_rate": float(utilization),
                    "apy_base": apy_base_pct,
                    "apy_reward": apy_reward_pct,
                    "apy_total": apy_total_pct,
                    "apy_borrow_variable": apy_borrow_pct,
                    "apy_borrow_stable": apy_borrow_stable_pct,
                    "ltv": ltv,
                    "liquidation_threshold": liq_threshold,
                    "liquidation_bonus": liq_bonus,
                    "decimals": decimals,
                    "reserve_factor": 0.0
                }
                results.append(data_row)

            except Exception as e:
                logger.error(f"Error processing {asset_address} in HypurrFi: {e}")
                time.sleep(1)

        return results
