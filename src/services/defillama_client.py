"""DeFi Llama API client.

This module provides a small wrapper around the DeFi Llama yields endpoint.
We keep this client thin and focused so it is easy to test and reuse in Prefect
flows.

Endpoint:
  GET https://yields.llama.fi/pools

Docs:
  The endpoint returns a JSON payload with a top-level "data" list of pool
  objects. Each pool includes fields like chain, pool, tvlUsd, apyBase,
  apyReward, apy, timestamp, etc.
"""

from __future__ import annotations

from typing import Any

import httpx


class DefiLlamaClient:
    """Async client for the DeFi Llama yields endpoint."""

    YIELDS_URL = "https://yields.llama.fi/pools"

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a new client.

        Args:
            timeout_seconds: Request timeout.
            transport: Optional httpx transport override (used for unit tests).
        """
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport

    async def get_hyperliquid_pools(self) -> list[dict[str, Any]]:
        """Fetch and return Hyperliquid/HyperEVM pools.

        Returns:
            A list of pool dicts filtered to chains "hyperliquid" and "hyperevm".

        Raises:
            httpx.HTTPStatusError: If the endpoint returns a non-success status.
            httpx.RequestError: For network errors.
        """
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.get(self.YIELDS_URL)
            response.raise_for_status()
            payload = response.json() or {}

        data = payload.get("data") or []
        if not isinstance(data, list):
            return []

        # DeFi Llama uses a 'chain' field; we match case-insensitively.
        out: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            chain = (item.get("chain") or "").lower()
            if chain in {"hyperliquid", "hyperevm"}:
                out.append(item)
        return out
