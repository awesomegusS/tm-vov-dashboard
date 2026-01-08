import csv
import time
from web3 import Web3
from decimal import Decimal

# --- CONFIGURATION ---
RPC_URL = "https://rpc.hyperliquid.xyz/evm"
POOL_ADDRESSES_PROVIDER = Web3.to_checksum_address("0xA73ff12D177D8F1Ec938c3ba0e87D33524dD5594")
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

def parse_configuration(conf_data):
    ltv = (conf_data & 0xFFFF) / 100.0 
    liq_threshold = ((conf_data >> 16) & 0xFFFF) / 100.0
    liq_bonus = ((conf_data >> 32) & 0xFFFF) / 100.0
    decimals = (conf_data >> 48) & 0xFF
    return ltv, liq_threshold, liq_bonus, decimals

def fetch_and_export():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("Error: Failed to connect to HyperEVM RPC")
        return

    print(f"Connected to HyperEVM ({PROTOCOL_NAME}). Block: {w3.eth.block_number}")

    provider = w3.eth.contract(address=POOL_ADDRESSES_PROVIDER, abi=ABI_PROVIDER)
    pool_address = provider.functions.getPool().call()
    oracle_address = provider.functions.getPriceOracle().call()
    
    pool = w3.eth.contract(address=pool_address, abi=ABI_POOL)
    oracle = w3.eth.contract(address=oracle_address, abi=ABI_ORACLE)

    reserves_list = pool.functions.getReservesList().call()
    print(f"Found {len(reserves_list)} assets.\n")

    results = []

    for asset_address in reserves_list:
        try:
            # --- RATE LIMIT PROTECTION ---
            # Sleep for 200ms between assets to prevent spamming the RPC
            time.sleep(0.2) 
            
            # --- FETCH DATA ---
            reserve_data = pool.functions.getReserveData(asset_address).call()
            
            conf_data = reserve_data[0][0]
            liquidity_rate_ray = reserve_data[2]        
            variable_borrow_rate_ray = reserve_data[4]  
            
            h_token_address = reserve_data[8]           
            var_debt_token_address = reserve_data[10]   

            ltv, liq_threshold, liq_bonus, decimals_conf = parse_configuration(conf_data)

            asset_contract = w3.eth.contract(address=asset_address, abi=ABI_ERC20)
            symbol = asset_contract.functions.symbol().call()
            name = asset_contract.functions.name().call()
            decimals = decimals_conf 

            h_token_contract = w3.eth.contract(address=h_token_address, abi=ABI_ERC20)
            total_supply_raw = h_token_contract.functions.totalSupply().call()

            debt_contract = w3.eth.contract(address=var_debt_token_address, abi=ABI_ERC20)
            total_debt_raw = debt_contract.functions.totalSupply().call()

            price_raw = oracle.functions.getAssetPrice(asset_address).call()
            price_usd = Decimal(price_raw) / Decimal(10**8)

            # --- CALCULATIONS ---
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

            apy_reward_pct = 0.0 
            apy_total_pct = apy_base_pct + apy_reward_pct

            accepts_usdc = True if "USDC" in symbol.upper() else False

            data_row = {
                "protocol": PROTOCOL_NAME,
                "pool_id": asset_address,
                "symbol": symbol,
                "name": name,
                "contract_address": h_token_address,
                "accepts_usdc": accepts_usdc,
                "tvl_usd": round(float(tvl_usd), 2),
                "total_debt_usd": round(float(total_debt_usd), 2),
                "utilization_rate": round(float(utilization), 4),
                "apy_base": round(apy_base_pct, 4),
                "apy_reward": round(apy_reward_pct, 4),
                "apy_total": round(apy_total_pct, 4),
                "apy_borrow_variable": round(apy_borrow_pct, 4),
                "ltv": ltv,
                "liquidation_threshold": liq_threshold,
                "liquidation_bonus": liq_bonus,
                "decimals": decimals
            }
            results.append(data_row)

            # --- VERBOSE TERMINAL OUTPUT ---
            print(f"[{symbol}] {name}")
            print(f"  ├── Protocol:        {data_row['protocol']}")
            print(f"  ├── Addresses:")
            print(f"  │    ├── Asset:      {data_row['pool_id']}")
            print(f"  │    └── Vault:      {data_row['contract_address']}")
            print(f"  ├── Financials:")
            print(f"  │    ├── TVL:        ${data_row['tvl_usd']:,.2f}")
            print(f"  │    ├── Debt:       ${data_row['total_debt_usd']:,.2f}")
            print(f"  │    ├── Util Rate:  {data_row['utilization_rate']}%")
            print(f"  │    └── AcceptUsdc: {data_row['accepts_usdc']}")
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
            print(f"Error processing {asset_address}: {e}")
            # If we still hit a rate limit, pause longer before the next one
            time.sleep(1)

    # --- SAVE TO CSV ---
    if results:
        csv_filename = "hypurrfi_full_data.csv"
        keys = results[0].keys()
        with open(csv_filename, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(results)
        print(f"\nSaved comprehensive data to '{csv_filename}'.")

if __name__ == "__main__":
    fetch_and_export()