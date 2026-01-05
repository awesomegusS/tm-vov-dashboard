# Data Ingestion Overview

This project ingests Hyperliquid vault metadata and performance metrics into Postgres on a schedule using Prefect.

## Data sources

- Vault list (canonical): `https://stats-data.hyperliquid.xyz/Mainnet/vaults`
- Per-vault details: `POST https://api.hyperliquid.xyz/info` with JSON `{ "type": "vaultDetails", "vaultAddress": "0x..." }`

## What gets stored

- `hyperliquid_vaults_discovery.vaults` — vault metadata (name, leader, tvl, relationship, etc.)
- `hyperliquid_vaults_discovery.vault_metrics` — time-series metrics per vault (pnl, volume, drawdown, max distributable tvl)
- `hyperliquid_vaults_discovery.top_500_vaults` — derived ranking table (latest metrics per vault, top 500 by `max_distributable_tvl`)

## Periodic runs

Two scheduled deployments are defined in `scripts/deploy_prefect_flows.py`:

- `hourly-vault-metrics` — runs `upsert_vault_metrics_flow` hourly (UTC)
- `4h-top-500` — runs `update_top_500_flow` every 4 hours (UTC)

## End-to-end flow (Mermaid)

```mermaid
flowchart TD
  %% External sources
  STATS[Hyperliquid Stats\n/Mainnet/vaults] -->|HTTP GET| FLOW1
  INFO[Hyperliquid API\nPOST /info type=vaultDetails] -->|HTTP POST (batched)| FLOW1

  %% Prefect control plane
  subgraph PREFECT[Prefect Orchestration]
    DEP1[Deployment\nhourly-vault-metrics\nCron: 0 * * * * UTC] --> RUN1[Flow Run]
    DEP2[Deployment\n4h-top-500\nCron: 0 */4 * * * UTC] --> RUN2[Flow Run]
  end

  %% Execution
  subgraph WORKER[Execution]
    WORK[Prefect Worker\n(work pool)] --> RUN1
    WORK --> RUN2
    FLOW1[upsert_vault_metrics_flow] --> VUP[Upsert vault rows]
    FLOW1 --> MUP[Upsert metric rows\n(batched upsert)]
    RUN2 --> TOP[update_top_500_flow]
  end

  %% Storage
  subgraph DB[(Postgres: hyperliquid_vaults_discovery)]
    VAULTS[(vaults)]
    METRICS[(vault_metrics)]
    TOP500[(top_500_vaults)]
  end

  %% Writes
  VUP --> VAULTS
  MUP --> METRICS
  TOP -->|SELECT latest metrics\nrank by max_distributable_tvl| METRICS
  TOP -->|WRITE| TOP500

  %% Orchestration wiring
  DEP1 --> WORK
  DEP2 --> WORK
```

## Important operational details

- **Rate limiting + retries:** detail fetches are throttled via a global async rate limiter (`requests_per_second`) with backoff/jitter for retryable errors.
- **Batching DB upserts:** writes are chunked to avoid the `asyncpg` bind-parameter limit (32,767 parameters).
- **Missing values:** if a vaultDetails payload omits fields (e.g., `maxDistributable`), ingestion stores NULL rather than inventing a value.

Next: see [Prefect Flows](prefect-flows.md) for parameters (`concurrency`, `requests_per_second`, etc.) and [Database](database.md) for schema/model details.
