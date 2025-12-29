import asyncio
from hyperliquid.info import Info
from hyperliquid.utils import constants

async def test_api():
    print(f"📍 Connecting to: {constants.MAINNET_API_URL}")
    info = Info(constants.MAINNET_API_URL, skip_ws=True)
    
    try:
        # 1. Try fetching simple metadata (often works even if restricted)
        print("1️⃣  Fetching Exchange Metadata...")
        meta = info.post("/info", {"type": "meta"})
        print(f"✅ Metadata Success! Found {len(meta['universe'])} assets.")
        
        # 2. Try fetching Vaults (likely blocked in US)
        print("\n2️⃣  Fetching Vault Summaries...")
        vaults = info.post("/info", {"type": "vaultSummaries"})
        
        if vaults:
            print(f"✅ Vaults Success! Found {len(vaults)} vaults.")
        else:
            print("❌ Vaults returned EMPTY list. (Likely Geo-blocked)")

    except Exception as e:
        print(f"❌ API Connection Failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_api())