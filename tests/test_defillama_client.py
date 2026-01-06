"""Unit tests for the DeFi Llama client and helpers.

These tests are network-isolated and use httpx MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from src.services.defillama_client import DefiLlamaClient


@pytest.mark.asyncio
async def test_get_hyperliquid_pools_filters_chain_hyperliquid_and_hyperevm() -> None:
    """Client filters pools to Hyperliquid/HyperEVM chains only."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://yields.llama.fi/pools"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"chain": "Hyperliquid", "pool": "p1"},
                    {"chain": "HyperEVM", "pool": "p2"},
                    {"chain": "Ethereum", "pool": "p3"},
                    {"chain": None, "pool": "p4"},
                ]
            },
        )

    client = DefiLlamaClient(transport=httpx.MockTransport(handler))
    pools = await client.get_hyperliquid_pools()

    assert [p.get("pool") for p in pools] == ["p1", "p2"]


@pytest.mark.asyncio
async def test_get_hyperliquid_pools_missing_data_key_returns_empty_list() -> None:
    """Client tolerates payloads without a 'data' key."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []})

    client = DefiLlamaClient(transport=httpx.MockTransport(handler))
    pools = await client.get_hyperliquid_pools()

    assert pools == []


@pytest.mark.asyncio
async def test_get_hyperliquid_pools_non_200_raises() -> None:
    """Client raises for non-success responses."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = DefiLlamaClient(transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.HTTPStatusError):
        await client.get_hyperliquid_pools()
