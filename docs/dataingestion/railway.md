# Railway (Prefect Server + Worker)

This repo includes a `Procfile` for hosting Prefect Server and a Prefect Worker on Railway.

## What the Railway “web” service is

The Railway `web` process runs **Prefect Server**.

- It exposes the **Prefect API** at `/api`.
- It also serves the **Prefect UI** in the browser.

Yes: this is where you’ll see your Prefect resources (work pools, deployments, runs, logs).

Important distinction:

- This is **not** your application’s custom dashboard UI.
- This is Prefect’s UI for orchestration/observability.

Your flows will show up there once you create deployments against that server.

## Files

- `Procfile`
  - `web`: starts Prefect Server
  - `worker`: starts Prefect Worker

## Core idea

- Prefect Server runs in the Railway `web` process.
- Prefect Worker runs in the Railway `worker` process.
- Deployments are created against that server and executed by the worker (no Prefect Cloud managed compute quota).

## Quick setup (Railway)

1) Create a Railway project from this repo.

2) Add a Postgres service for **Prefect Server metadata**.

3) Create a Railway service for the server:

- Procfile process: `web`
- Env vars:
  - `PREFECT_API_DATABASE_CONNECTION_URL` = Postgres URL for Prefect metadata
    - If you run into driver issues, try `postgresql+asyncpg://...`.

After deploy, note the public URL for this service.

4) Create a Railway service for the worker:

- Procfile process: `worker`
- Env vars:
  - `PREFECT_API_URL` = `https://<prefect-server-public-domain>/api`
  - `DATABASE_URL` = Postgres URL for your app DB (where `vaults`/`vault_metrics` live)

5) One-time initialization (run from your laptop):

```bash
export PREFECT_API_URL="https://<prefect-server-public-domain>/api"
prefect work-pool create hyperliquid-vault-ingestion --type process

python scripts/deploy_prefect_flows.py \
  --work-pool hyperliquid-vault-ingestion
```

Once deployments exist, Railway’s worker will pick up scheduled runs.

## Minimum required configuration

At minimum:

- `PREFECT_API_URL` on the worker: `https://<prefect-server-public-domain>/api`
- `DATABASE_URL` on the worker: the app Postgres URL (vaults/metrics tables)

Prefect Server also needs its own metadata DB URL (Prefect’s internal DB), typically configured as `PREFECT_API_DATABASE_CONNECTION_URL`.
