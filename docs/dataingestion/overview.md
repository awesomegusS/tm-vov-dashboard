# Data Ingestion Overview

This project ingests Hyperliquid and HyperEVM vault metadata and performance metrics into Postgres on a schedule using Prefect.

## Data sources

The ingestion system uses a hybrid approach to gather data:

1.  **Hyperliquid Stats & API**:
    *   Vault list (canonical): `https://stats-data.hyperliquid.xyz/Mainnet/vaults`
    *   Per-vault details: `POST https://api.hyperliquid.xyz/info`

2.  **DeFi Llama**:
    *   Broad EVM pool discovery via `https://yields.llama.fi/pools`.

3.  **Direct RPC (HyperEVM)**:
    *   Protocol-specific clients (Felix, Hyperlend, HypurrFi, Hyperbeat) connect directly to the HyperEVM JSON-RPC (`https://rpc.hyperliquid.xyz/evm`) to fetch granular risk parameters and borrow metrics.

## What gets stored

it stores data in the `hyperliquid_vaults_discovery` schema:

- `vaults` / `vault_metrics`: Native Hyperliquid vaults (HLP, etc.).
- `top_500_vaults`: Derived ranking of native vaults.
- `evm_pools` / `evm_pool_metrics`: HyperEVM ecosystem pools (Lending, CDPs, Vaults).

## Periodic runs

Two scheduled deployments are defined in `scripts/deploy_prefect_flows.py`:

- `hourly-vault-metrics` — runs `upsert_vault_metrics_flow` hourly (UTC)
- `4h-top-500` — runs `update_top_500_flow` every 4 hours (UTC)
- `hourly-evm-pools` — runs `sync_evm_pools_flow` hourly (UTC) to sync external EVM pools.

## End-to-end flow (Mermaid)

```mermaid
flowchart TD
  %% External sources (Hyperliquid)
  STATS["Hyperliquid Stats<br/>/Mainnet/vaults"] --> FLOW1
  FLOW1 --> INFO["Hyperliquid API<br/>/info (vaultDetails)"]

  %% External sources (HyperEVM)
  DL["DeFi Llama<br/>/yields"] --> EVM_FLOW
  FELIX["Felix Protocol<br/>(RPC)"] --> EVM_FLOW
  HL["Hyperlend<br/>(RPC)"] --> EVM_FLOW
  HF["HypurrFi<br/>(RPC)"] --> EVM_FLOW
  HB["Hyperbeat<br/>(RPC)"] --> EVM_FLOW

  %% Prefect control plane
  subgraph PREFECT[Prefect Orchestration]
    DEP1["Deployment<br/>hourly-vault-metrics<br/>Hourly (UTC)"] --> RUN1["Flow Run<br/>upsert_vault_metrics_flow"]
    DEP2["Deployment<br/>4h-top-500<br/>Every 4 hours (UTC)"] --> RUN2["Flow Run<br/>update_top_500_flow"]
    DEP3["Deployment<br/>hourly-evm-pools<br/>Hourly (UTC)"] --> RUN3["Flow Run<br/>evm_pools_sync_flow"]
  end

  %% Execution
  subgraph WORKER[Execution]
    WORK["Prefect Worker<br/>(work pool)"] --> RUN1
    WORK --> RUN2
    WORK --> RUN3
    FLOW1[upsert_vault_metrics_flow] --> VUP[Upsert vault rows]
    FLOW1 --> MUP["Upsert metric rows<br/>(batched upsert)"]
    RUN2 --> TOP[update_top_500_flow]
    RUN3 --> EVM_FLOW[evm_pools_sync_flow]
  end

  %% Storage
  subgraph DB["Postgres: hyperliquid_vaults_discovery"]
    VAULTS["vaults"]
    METRICS["vault_metrics"]
    TOP500["top_500_vaults"]
    EVM_POOLS["evm_pools"]
    EVM_METRICS["evm_pool_metrics"]
  end

  %% Writes
  VUP --> VAULTS
  MUP --> METRICS
  TOP --> METRICS
  TOP --> TOP500
  EVM_FLOW --> EVM_POOLS
  EVM_FLOW --> EVM_METRICS

  %% Orchestration wiring
  DEP1 --> WORK
  DEP2 --> WORK
  DEP3 --> WORK
```

## Important operational details

- **Rate limiting + retries:** detail fetches are throttled via a global async rate limiter (`requests_per_second`) with backoff/jitter for retryable errors.
- **Batching DB upserts:** writes are chunked to avoid the `asyncpg` bind-parameter limit (32,767 parameters).
- **Missing values:** if a vaultDetails payload omits fields (e.g., `maxDistributable`), ingestion stores NULL rather than inventing a value.

Next: see [Prefect Flows](prefect-flows.md) for parameters (`concurrency`, `requests_per_second`, etc.) and [Database](database.md) for schema/model details.
