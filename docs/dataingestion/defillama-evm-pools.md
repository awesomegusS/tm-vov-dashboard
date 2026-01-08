# Hybrid Ingestion: DeFi Llama + Direct RPC (EVM Pools)

This guide shows how we fetch Hyperliquid + HyperEVM pools using a hybrid approach:
1.  **DeFi Llama**: Broad coverage of pools via `GET https://yields.llama.fi/pools`.
2.  **Direct RPC**: Richer, real-time data for specific protocols (Felix, Hyperlend, HypurrFi, Hyperbeat) via direct chain calls.

## 1) Data Sources

### A. DeFi Llama (General Discovery)
We fetch the global pool list and filter for `chain="HyperEVM"` or `chain="Hyperliquid"`. This provides basic TVL and APY data for most pools.

### B. Direct RPC Clients (Protocol-Specific)
For key ecosystem partners, we use custom Python clients (`src/services/*_client.py`) that query on-chain contracts via the HyperEVM RPC `https://rpc.hyperliquid.xyz/evm`. This allows us to fetch deeper metrics not available on DeFi Llama:
- **Risk Params**: LTV, Liquidation Thresholds, Reserve Factors.
- **Borrow Metrics**: Total Debt, Utilization Rates, Borrow APYs (Variable/Stable).
- **Metadata**: Exact token decimals, underlying asset addresses.

## 2) Flag USDC-accepting pools

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

- Pool metadata: `pool` (id), `project` (protocol), `poolMeta` (name-ish), `symbol`, `contract_address`, `ltv`, `liquidation_threshold`, `decimals`
- Metrics: `tvlUsd`, `apyBase`, `apyReward`, `apy`, `total_debt_usd`, `utilization_rate`, `apy_borrow_variable`, `apy_borrow_stable`, plus `timestamp`

## 5) Use the project client + flow

This repo includes client wrappers and an hourly Prefect flow:

- Clients:
    * `src/services/defillama_client.py`
    * `src/services/felix_client.py`
    * `src/services/hyperlend_client.py`
    * `src/services/hypurrfi_client.py`
    * `src/services/hyperbeat_client.py`
- Flow: `src/pipelines/flows/evm_pools.py` (`sync_evm_pools_flow`)

The deployment is registered in `scripts/deploy_prefect_flows.py` as `hourly-evm-pools`.

## 6) Run tests

- Unit tests (fast, no network):

```bash
pytest -q
```

- Integration test (opt-in):

```bash
RUN_INTEGRATION=1 pytest -q -k defillama_integration
```

## 7) Run the flow locally

Use the local runner script (if available) or run module:

- Dry-run (no DB writes):

```bash
python scripts/run_evm_pools_flow_local.py --no-persist
```

- Persist to Postgres (requires `DATABASE_URL` to be set in `.env` or environment):

```bash
python scripts/run_evm_pools_flow_local.py
```

By default this runs without Prefect Cloud/Server (ephemeral/local execution). To use your configured Prefect API, pass `--use-prefect-api`.
