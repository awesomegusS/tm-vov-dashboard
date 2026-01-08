import csv
import time
from web3 import Web3
from decimal import Decimal

# --- CONFIGURATION ---
RPC_URL = "https://rpc.hyperliquid.xyz/evm"
PROTOCOL_NAME = "Hyperbeat"

# Reusing Hyperlend Oracle for pricing (Shared Infrastructure)
ORACLE_ADDRESS = Web3.to_checksum_address("0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e")

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

# --- HELPER: RETRY LOGIC ---
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
        print("Error: Failed to connect to HyperEVM RPC")
        return

    print(f"Connected to HyperEVM ({PROTOCOL_NAME}). Block: {w3.eth.block_number}")
    
    oracle_contract = w3.eth.contract(address=ORACLE_ADDRESS, abi=ABI_ORACLE)
    results = []

    for vault_name, vault_addr_raw in VAULTS.items():
        try:
            # Polite delay
            time.sleep(0.5)

            vault_addr = Web3.to_checksum_address(vault_addr_raw)
            vault_contract = w3.eth.contract(address=vault_addr, abi=ABI_VAULT)

            # 1. Get Vault Info
            symbol = call_with_retry(vault_contract.functions.symbol())
            
            # 2. Identify Underlying
            try:
                underlying_addr = call_with_retry(vault_contract.functions.asset())
                is_erc4626 = True
            except:
                underlying_addr = vault_addr 
                is_erc4626 = False

            # 3. Get Decimals
            if is_erc4626:
                underlying_contract = w3.eth.contract(address=underlying_addr, abi=ABI_ERC20)
                underlying_decimals = call_with_retry(underlying_contract.functions.decimals())
                underlying_symbol = call_with_retry(underlying_contract.functions.symbol())
            else:
                underlying_decimals = call_with_retry(vault_contract.functions.decimals())
                underlying_symbol = symbol

            # 4. Get Balance (TVL)
            try:
                raw_balance = call_with_retry(vault_contract.functions.totalAssets())
            except:
                raw_balance = call_with_retry(vault_contract.functions.totalSupply())

            # 5. Get Price
            try:
                raw_price = call_with_retry(oracle_contract.functions.getAssetPrice(underlying_addr))
                price_usd = Decimal(raw_price) / Decimal(10**8)
            except:
                price_usd = Decimal(0)

            # --- CALCULATIONS ---
            tvl_tokens = Decimal(raw_balance) / Decimal(10**underlying_decimals)
            tvl_usd = tvl_tokens * price_usd
            accepts_usdc = True if "USDC" in underlying_symbol.upper() else False

            # --- DATA ROW ---
            data_row = {
                "protocol": PROTOCOL_NAME,
                "pool_id": vault_addr,
                "symbol": symbol,
                "name": vault_name,
                "contract_address": vault_addr,
                "accepts_usdc": accepts_usdc,
                "tvl_usd": round(float(tvl_usd), 2),
                # Zero placeholders for columns not applicable to simple vaults
                "total_debt_usd": 0.0,
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

            # --- FULL VERBOSE TERMINAL OUTPUT ---
            print(f"[{symbol}] {vault_name}")
            print(f"  ├── Protocol:        {data_row['protocol']}")
            print(f"  ├── Addresses:")
            print(f"  │    ├── Vault:      {data_row['pool_id']}")
            print(f"  │    └── Underlying: {underlying_addr}")
            print(f"  ├── Financials:")
            print(f"  │    ├── TVL:        ${data_row['tvl_usd']:,.2f}")
            print(f"  │    ├── Price:      ${price_usd:,.2f}")
            print(f"  │    ├── Debt:       ${data_row['total_debt_usd']:,.2f}")
            print(f"  │    └── Util Rate:  {data_row['utilization_rate']}%")
            print(f"  ├── Rates (APY):")
            print(f"  │    ├── Base:       {data_row['apy_base']}%")
            print(f"  │    ├── Reward:     {data_row['apy_reward']}%")
            print(f"  │    ├── Total:      {data_row['apy_total']}%")
            print(f"  │    └── Borrow:     {data_row['apy_borrow_variable']}%")
            print(f"  └── Risk Params:")
            print(f"       ├── LTV:        {data_row['ltv']}%")
            print(f"       ├── Liq Thresh: {data_row['liquidation_threshold']}%")
            print(f"       ├── Liq Bonus:  {data_row['liquidation_bonus']}%")
            print(f"       └── Decimals:   {data_row['decimals']}")
            print("-" * 60)

        except Exception as e:
            print(f"Error processing {vault_name}: {e}")

    # --- SAVE TO CSV ---
    if results:
        csv_filename = "hyperbeat_full_data.csv"
        keys = results[0].keys()
        with open(csv_filename, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
        print(f"\nSaved Hyperbeat data to '{csv_filename}'.")

if __name__ == "__main__":
    fetch_and_export()