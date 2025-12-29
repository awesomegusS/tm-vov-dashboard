import requests
import json

def debug_connection():
    print("--- 🕵️ NETWORK DIAGNOSTICS ---")
    
    # 1. Check IP visibility
    try:
        ip_info = requests.get("https://ipinfo.io/json", timeout=5).json()
        print(f"🌍 Your Python IP: {ip_info.get('ip')} ({ip_info.get('country')})")
        print(f"   Org: {ip_info.get('org')}")
        
        if ip_info.get('country') == 'US':
            print("❌ CRITICAL: Python is still routing through the US!")
    except Exception as e:
        print(f"⚠️ Could not check IP: {e}")

    print("\n--- 🏦 HYPERLIQUID RAW API CHECK ---")
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "vaultSummaries"}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"📡 Status Code: {response.status_code}")
        print(f"📦 Response Size: {len(response.content)} bytes")
        
        data = response.json()
        if isinstance(data, list):
            print(f"📊 Items Returned: {len(data)}")
            if len(data) == 0:
                print("❌ RESULT: API returned an empty list (Geo-blocking or Shadow-ban active).")
        else:
            print(f"⚠️ Unexpected format: {type(data)}")
            print(str(data)[:200]) # Print first 200 chars

    except Exception as e:
        print(f"❌ Connection Failed: {e}")

if __name__ == "__main__":
    debug_connection()