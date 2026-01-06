"""ERC-4626 client utilities.

This module provides a minimal Web3 client for reading ERC-4626 vault state
(totalAssets, totalSupply, underlying asset) and ERC-20 token metadata.

We use this as a fallback when DeFi Llama yields does not list a target protocol.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from web3 import Web3


# Minimal ABI fragments for ERC-4626 and ERC-20 reads.
_ERC4626_ABI: list[dict[str, Any]] = [
    {
        "name": "totalAssets",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "totalSupply",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "asset",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "name": "name",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
    {
        "name": "symbol",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]

_ERC20_ABI: list[dict[str, Any]] = [
    {
        "name": "decimals",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "name": "symbol",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
    {
        "name": "name",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
]


@dataclass(frozen=True)
class Erc4626VaultSnapshot:
    vault_address: str
    vault_name: str | None
    vault_symbol: str | None
    vault_decimals: int | None
    asset_address: str | None
    asset_symbol: str | None
    asset_decimals: int | None
    total_assets_raw: int | None
    total_supply_raw: int | None

    def total_assets_normalized(self) -> Decimal | None:
        if self.total_assets_raw is None or self.asset_decimals is None:
            return None
        return Decimal(self.total_assets_raw) / (Decimal(10) ** Decimal(self.asset_decimals))


class Erc4626Client:
    def __init__(self, rpc_url: str, request_timeout_seconds: int = 20) -> None:
        self._w3 = Web3(
            Web3.HTTPProvider(
                rpc_url,
                request_kwargs={"timeout": request_timeout_seconds},
            )
        )

    @staticmethod
    def _checksum(address: str) -> str:
        return Web3.to_checksum_address(address)

    def _erc20_contract(self, token_address: str):
        return self._w3.eth.contract(address=self._checksum(token_address), abi=_ERC20_ABI)

    def _erc4626_contract(self, vault_address: str):
        return self._w3.eth.contract(address=self._checksum(vault_address), abi=_ERC4626_ABI)

    def get_vault_snapshot_sync(self, vault_address: str) -> Erc4626VaultSnapshot:
        contract = self._erc4626_contract(vault_address)

        def _safe_call(fn):
            try:
                return fn.call()
            except Exception:
                return None

        vault_name = _safe_call(contract.functions.name())
        vault_symbol = _safe_call(contract.functions.symbol())
        vault_decimals = _safe_call(contract.functions.decimals())

        asset_address = _safe_call(contract.functions.asset())
        total_assets = _safe_call(contract.functions.totalAssets())
        total_supply = _safe_call(contract.functions.totalSupply())

        asset_symbol = None
        asset_decimals = None
        if asset_address:
            token = self._erc20_contract(asset_address)
            asset_symbol = _safe_call(token.functions.symbol())
            asset_decimals = _safe_call(token.functions.decimals())

        return Erc4626VaultSnapshot(
            vault_address=str(vault_address),
            vault_name=vault_name if isinstance(vault_name, str) else None,
            vault_symbol=vault_symbol if isinstance(vault_symbol, str) else None,
            vault_decimals=int(vault_decimals) if isinstance(vault_decimals, int) else None,
            asset_address=str(asset_address) if isinstance(asset_address, str) else None,
            asset_symbol=asset_symbol if isinstance(asset_symbol, str) else None,
            asset_decimals=int(asset_decimals) if isinstance(asset_decimals, int) else None,
            total_assets_raw=int(total_assets) if isinstance(total_assets, int) else None,
            total_supply_raw=int(total_supply) if isinstance(total_supply, int) else None,
        )

    async def get_vault_snapshot(self, vault_address: str) -> Erc4626VaultSnapshot:
        return await asyncio.to_thread(self.get_vault_snapshot_sync, vault_address)
