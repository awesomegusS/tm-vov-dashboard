# Deployments (Prefect)

Deployments are created programmatically by `scripts/deploy_prefect_flows.py`.

This script uses Prefect’s `flow.from_source(...).deploy(...)` pattern (git-backed source).

## Deployments defined

- `hourly-vault-metrics`
  - Entry point: `src/pipelines/flows/upsert_vaults.py:upsert_vault_metrics_flow`
  - Schedule: cron hourly

- `4h-top-500`
  - Entry point: `src/pipelines/flows/upsert_vaults.py:update_top_500_flow`
  - Schedule: cron every 4 hours

## How to create/update deployments

From the repo root:

```bash
python scripts/deploy_prefect_flows.py --help
```

Typical usage (example):

```bash
python scripts/deploy_prefect_flows.py \
  --work-pool hyperliquid-vault-ingestion
```

Notes:

- If your workers pull from git, you must push code changes to the repo (and recreate/update deployments) for those changes to take effect in runs.
- If you’re running Prefect Server (self-hosted), create the work pool in that server UI/CLI and run a worker against it.
