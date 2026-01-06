# DeFi Llama → Hyperliquid/HyperEVM Pools (Step-by-step)

This guide shows how to fetch Hyperliquid + HyperEVM pools from DeFi Llama using:

- `GET https://yields.llama.fi/pools`

## 1) Call the endpoint

The response is JSON with a top-level `data` array of pool objects.

Example (raw httpx):

```python
import httpx

url = "https://yields.llama.fi/pools"
resp = httpx.get(url, timeout=30)
resp.raise_for_status()
payload = resp.json()
pools = payload.get("data", [])
```

## 2) Filter to Hyperliquid / HyperEVM

Each pool includes a `chain` field. Filter case-insensitively:

```python
wanted = {"hyperliquid", "hyperevm"}
filtered = [
    p for p in pools
    if (p.get("chain") or "").lower() in wanted
]
```

## 3) Flag USDC-accepting pools

For the MVP heuristic, we mark pools that contain `"usdc"` in their symbol:

```python
for p in filtered:
    symbol = (p.get("symbol") or "")
    p["accepts_usdc"] = "usdc" in symbol.lower()
```

## 4) Persist pool metadata + metrics

We store two tables:

- `evm_pools`: one row per pool (`pool_id` is unique)
- `evm_pool_metrics`: time-series metrics (`time`, `pool_id` composite key)

Common fields from DeFi Llama that we store:

- Pool metadata: `pool` (id), `project` (protocol), `poolMeta` (name-ish), `symbol`, `address`
- Metrics: `tvlUsd`, `apyBase`, `apyReward`, `apy`, plus `timestamp`

## 5) Use the project client + flow

This repo includes a small client wrapper and an hourly Prefect flow:

- Client: `src/services/defillama_client.py`
- Flow: `src/pipelines/flows/evm_pools.py` (`sync_evm_pools_flow`)

The deployment is registered in `scripts/deploy_prefect_flows.py` as `hourly-evm-pools`.

## 6) Run tests

- Unit tests (fast, no network):

```bash
pytest -q
```

- Integration test (calls DeFi Llama; opt-in):

```bash
RUN_INTEGRATION=1 pytest -q -k defillama_integration
```
