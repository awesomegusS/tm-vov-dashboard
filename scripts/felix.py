import csv
import time
from web3 import Web3
from decimal import Decimal

# --- CONFIGURATION ---
RPC_URL = "https://rpc.hyperliquid.xyz/evm"
PROTOCOL_NAME = "Felix"

# Shared Oracle (Hyperlend) for pricing the Lending Vault assets
ORACLE_ADDRESS = Web3.to_checksum_address("0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e")

# --- MARKET 1: CDP MARKETS (Liquity V2) ---
CDP_MARKETS = {
    "WHYPE": {
        "collateral": "0x5555555555555555555555555555555555555555",
        "active_pool": "0x39ebba742b6917d49d4a9ac7cf5c70f84d34cc9e",
        "price_feed": "0x12a1868b89789900e413a6241ca9032dd1873a51"
    },
    "UBTC": {
        "collateral": "0x9fdbda0a5e284c32744d2f17ee5c74b284993463",
        "active_pool": "0x8d99575ebbbda038a626ca769561c16fdd7a5939",
        "price_feed": "0xf59f338424062dd1d44a9b4dd2721128a45358ab"
    },
    "kHYPE": {
        "collateral": "0xfd739d4e423301ce9385c1fb8850539d657c296d",
        "active_pool": "0xbfd0b103a49faf426f36864d19f5d871bf411a5a",
        "price_feed": "0x0a04e685f12e47b22b03c3763add63f1dd73265c"
    },
    "wstHYPE": {
        "collateral": "0x94e8396e0869c9f2200760af0621afd240e1cf38",
        "active_pool": "0x7abca40474d6b5f000f801d7fe7e0df4c89425ff",
        "price_feed": "0x067e69ad6bdb8ee95cac31b34626f48eb6f169a2"
    }
}

# --- MARKET 2: LENDING VAULTS (ERC4626 / MetaMorpho) ---
LENDING_VAULTS = {
    "USDe Vault":       "0x835febf893c6dddee5cf762b0f8e31c5b06938ab",
    "USDT0 Vault":      "0xfc5126377f0efc0041c0969ef9ba903ce67d151e",
    "USDT0 (Frontier)": "0x9896a8605763106e57a51aa0a97fe8099e806bb3",
    "USDhl Vault":      "0x9c59a9389d8f72DE2CdAf1126f36EA4790E2275e",
    "USDhl (Frontier)": "0x66c71204B70aE27BE6dC3eb41F9aF5868E68fDb6",
    "HYPE Vault":       "0x2900ABd73631b2f60747e687095537B673c06A76"
}

# --- ABIS ---
ABI_ERC20 = [
    {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
]

# Liquity V2 (CDP)
ABI_PRICE_FEED = [
    {"inputs":[],"name":"fetchPrice","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"lastGoodPrice","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
]
ABI_ACTIVE_POOL = [
    {"inputs":[],"name":"getFeUSDDebt","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getSystemDebt","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"} 
]

# Lending Vaults (ERC4626)
ABI_VAULT = [
    {"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"asset","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalAssets","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
]

# Shared Oracle
ABI_ORACLE = [
    {"inputs":[{"internalType":"address","name":"asset","type":"address"}],"name":"getAssetPrice","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}
]

def call_with_retry(contract_func, max_retries=5, initial_delay=2):
    for attempt in range(max_retries):
        try:
            return contract_func.call()
        except Exception as e:
            error_str = str(e).lower()
            if "rate limited" in error_str or "-32005" in error_str:
                delay = initial_delay * (attempt + 1)
                print(f"   >>> Rate limit hit. Sleeping {delay}s...")
                time.sleep(delay)
            else:
                raise e
    raise Exception("Failed after max retries")

def fetch_and_export():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("Error: Failed to connect to RPC")
        return

    print(f"Connected to HyperEVM ({PROTOCOL_NAME}). Block: {w3.eth.block_number}")
    oracle_contract = w3.eth.contract(address=ORACLE_ADDRESS, abi=ABI_ORACLE)

    results = []

    # ==================================================
    # 1. PROCESS CDP MARKETS (Liquity V2)
    # ==================================================
    print("\n--- Processing CDP Markets ---")
    for symbol_key, addresses in CDP_MARKETS.items():
        try:
            time.sleep(0.5)
            
            # Setup Contracts
            collateral_addr = Web3.to_checksum_address(addresses["collateral"])
            active_pool_addr = Web3.to_checksum_address(addresses["active_pool"])
            price_feed_addr = Web3.to_checksum_address(addresses["price_feed"])

            collateral_contract = w3.eth.contract(address=collateral_addr, abi=ABI_ERC20)
            price_feed_contract = w3.eth.contract(address=price_feed_addr, abi=ABI_PRICE_FEED)
            active_pool_contract = w3.eth.contract(address=active_pool_addr, abi=ABI_ACTIVE_POOL)

            # Basic Info
            symbol = call_with_retry(collateral_contract.functions.symbol())
            decimals = call_with_retry(collateral_contract.functions.decimals())

            # Metrics
            raw_collateral_balance = call_with_retry(collateral_contract.functions.balanceOf(active_pool_addr))
            
            # Price (Try fetchPrice, else lastGoodPrice)
            try:
                raw_price = call_with_retry(price_feed_contract.functions.fetchPrice())
            except:
                raw_price = call_with_retry(price_feed_contract.functions.lastGoodPrice())

            # Debt
            try:
                raw_debt = call_with_retry(active_pool_contract.functions.getFeUSDDebt())
            except:
                try:
                    raw_debt = call_with_retry(active_pool_contract.functions.getSystemDebt())
                except:
                    raw_debt = 0

            # Calc
            price_usd = Decimal(raw_price) / Decimal(10**18)
            collateral_amt = Decimal(raw_collateral_balance) / Decimal(10**decimals)
            tvl_usd = collateral_amt * price_usd
            debt_usd = Decimal(raw_debt) / Decimal(10**18)

            if tvl_usd > 0:
                utilization = (debt_usd / tvl_usd) * 100
            else:
                utilization = Decimal(0)
            
            accepts_usdc = True if "USDC" in symbol.upper() else False

            data_row = {
                "protocol": PROTOCOL_NAME,
                "pool_id": collateral_addr,
                "symbol": symbol,
                "name": f"Felix {symbol} CDP",
                "contract_address": active_pool_addr,
                "market_type": "CDP",
                "accepts_usdc": accepts_usdc,
                "tvl_usd": round(float(tvl_usd), 2),
                "total_debt_usd": round(float(debt_usd), 2),
                "utilization_rate": round(float(utilization), 4),
                "apy_base": 0.0,
                "apy_reward": 0.0,
                "apy_total": 0.0,
                "apy_borrow_variable": 0.0,
                "ltv": 90.90,
                "liquidation_threshold": 110.0,
                "liquidation_bonus": 0.0,
                "decimals": decimals
            }
            results.append(data_row)
            print(f"[{symbol}] CDP Processed.")

        except Exception as e:
            print(f"Error processing CDP {symbol_key}: {e}")

    # ==================================================
    # 2. PROCESS LENDING VAULTS (ERC4626)
    # ==================================================
    print("\n--- Processing Lending Vaults ---")
    for vault_name, vault_addr_raw in LENDING_VAULTS.items():
        try:
            time.sleep(0.5)

            vault_addr = Web3.to_checksum_address(vault_addr_raw)
            vault_contract = w3.eth.contract(address=vault_addr, abi=ABI_VAULT)

            # Info
            symbol = call_with_retry(vault_contract.functions.symbol())
            
            # Underlying Asset
            try:
                underlying_addr = call_with_retry(vault_contract.functions.asset())
                underlying_contract = w3.eth.contract(address=underlying_addr, abi=ABI_ERC20)
                underlying_decimals = call_with_retry(underlying_contract.functions.decimals())
                underlying_symbol = call_with_retry(underlying_contract.functions.symbol())
            except:
                # Fallback if not ERC4626 (unlikely given description)
                underlying_addr = vault_addr
                underlying_decimals = call_with_retry(vault_contract.functions.decimals())
                underlying_symbol = symbol

            # TVL
            try:
                raw_balance = call_with_retry(vault_contract.functions.totalAssets())
            except:
                raw_balance = call_with_retry(vault_contract.functions.totalSupply())

            # Price (Using Shared Hyperlend Oracle)
            try:
                raw_price = call_with_retry(oracle_contract.functions.getAssetPrice(underlying_addr))
                price_usd = Decimal(raw_price) / Decimal(10**8)
            except:
                price_usd = Decimal(0)

            # Calc
            tvl_tokens = Decimal(raw_balance) / Decimal(10**underlying_decimals)
            tvl_usd = tvl_tokens * price_usd
            accepts_usdc = True if "USDC" in underlying_symbol.upper() else False

            data_row = {
                "protocol": PROTOCOL_NAME,
                "pool_id": vault_addr,
                "symbol": symbol,
                "name": vault_name,
                "contract_address": vault_addr,
                "market_type": "Lending",
                "accepts_usdc": accepts_usdc,
                "tvl_usd": round(float(tvl_usd), 2),
                "total_debt_usd": 0.0, # Lending vaults usually don't track debt directly on the vault token
                "utilization_rate": 0.0,
                "apy_base": 0.0, 
                "apy_reward": 0.0,
                "apy_total": 0.0,
                "apy_borrow_variable": 0.0,
                "ltv": 0.0,
                "liquidation_threshold": 0.0,
                "liquidation_bonus": 0.0,
                "decimals": underlying_decimals
            }
            results.append(data_row)
            print(f"[{symbol}] Lending Vault Processed.")

        except Exception as e:
            print(f"Error processing Vault {vault_name}: {e}")

    # ==================================================
    # 3. EXPORT & DISPLAY
    # ==================================================
    if results:
        csv_filename = "felix_full_data.csv"
        keys = results[0].keys()
        with open(csv_filename, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
        
        print("\n" + "="*80)
        print(f"FINAL REPORT: {len(results)} Markets Fetched")
        print("="*80)
        
        for row in results:
            print(f"[{row['market_type']}] {row['name']}")
            print(f"  ├── Symbol:      {row['symbol']}")
            print(f"  ├── TVL:         ${row['tvl_usd']:,.2f}")
            if row['market_type'] == "CDP":
                print(f"  ├── Debt:        ${row['total_debt_usd']:,.2f}")
                print(f"  ├── Util Rate:   {row['utilization_rate']}%")
            print(f"  ├── Address:     {row['contract_address']}")
            print("-" * 60)
            
        print(f"\nSaved to '{csv_filename}'.")

if __name__ == "__main__":
    fetch_and_export()