import json

import pytest


@pytest.mark.asyncio
async def test_erc4626_fallback_merges_into_pool_list(monkeypatch):
    """Ensure on-chain target pools are merged and deduped by pool id."""

    from src.pipelines.flows import evm_pools as mod

    # Make sure the loader sees a configured target list.
    monkeypatch.setattr(
        mod.settings,
        "ERC4626_TARGET_VAULTS_JSON",
        json.dumps(
            [
                {"protocol": "Felix", "vault_address": "0x1111111111111111111111111111111111111111"},
                {"protocol": "Hyperlend", "vault_address": "0x2222222222222222222222222222222222222222"},
            ]
        ),
        raising=False,
    )
    monkeypatch.setattr(mod.settings, "HYPEREVM_RPC_URL", "http://example.invalid", raising=False)

    # Stub client to avoid real RPC.
    class _Snap:
        def __init__(self, vault_address: str):
            self.vault_address = vault_address
            self.vault_name = None
            self.vault_symbol = "vUSDC"
            self.vault_decimals = 6
            self.asset_address = "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # mainnet USDC shape
            self.asset_symbol = "USDC"
            self.asset_decimals = 6
            self.total_assets_raw = 123_000_000
            self.total_supply_raw = 0

        def total_assets_normalized(self):
            return 123.0

    class _Client:
        def __init__(self, rpc_url: str):
            self.rpc_url = rpc_url

        async def get_vault_snapshot(self, vault_address: str):
            return _Snap(vault_address)

    monkeypatch.setattr(mod, "Erc4626Client", _Client)

    # Existing DeFi Llama pools (none are target protocols).
    defillama = [
        {
            "pool": "defillama-1",
            "project": "some-protocol",
            "symbol": "ETH",
            "tvlUsd": 1.0,
            "timestamp": 1700000000,
        }
    ]

    onchain = await mod.fetch_erc4626_target_pools()
    assert len(onchain) == 2

    merged = mod.flag_usdc_pools(defillama) + mod.flag_usdc_pools(onchain)

    # Reuse the merge/dedupe logic from the flow.
    by_id = {str(p.get("pool")): p for p in merged if p.get("pool")}
    assert "defillama-1" in by_id
    assert "0x1111111111111111111111111111111111111111" in by_id
    assert "0x2222222222222222222222222222222222222222" in by_id

    assert by_id["0x1111111111111111111111111111111111111111"]["project"] == "Felix"
    assert by_id["0x1111111111111111111111111111111111111111"]["tvlUsd"] == 123.0
