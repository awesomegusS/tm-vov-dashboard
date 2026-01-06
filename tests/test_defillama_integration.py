"""Integration tests for the DeFi Llama pools endpoint.

These tests call a public endpoint and validate only stable invariants.
"""

from __future__ import annotations

import httpx
import pytest

from src.services.defillama_client import DefiLlamaClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_defillama_pools_endpoint_returns_expected_shape() -> None:
  """Sanity-check the public DeFi Llama endpoint response."""

  async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as http:
    response = await http.get("https://yields.llama.fi/pools")
    response.raise_for_status()
    payload = response.json() or {}

  assert "data" in payload
  assert isinstance(payload["data"], list)
  assert len(payload["data"]) > 0

  sample = payload["data"][0]
  assert isinstance(sample, dict)
  assert "chain" in sample
  assert "project" in sample
  assert "pool" in sample
  assert "tvlUsd" in sample
  assert "apy" in sample


@pytest.mark.asyncio
@pytest.mark.integration
async def test_defillama_client_filters_hyperliquid_and_hyperevm_only() -> None:
  """Client filter should only return Hyperliquid/HyperEVM pools."""
  client = DefiLlamaClient()
  pools = await client.get_hyperliquid_pools()
  assert isinstance(pools, list)
  assert len(pools) > 0
  for p in pools:
    chain = (p.get("chain") or "").lower()
    assert chain in {"hyperliquid", "hyperevm"}
