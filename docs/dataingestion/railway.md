# Railway (Prefect Server + Worker)

This repo includes a `Procfile` for hosting Prefect Server and a Prefect Worker on Railway.

## Files

- `Procfile`
  - `web`: starts Prefect Server
  - `worker`: starts Prefect Worker

This repo also includes `start_worker.sh`, which the Procfile uses to ensure `git` is available at runtime (required for deployments that use Prefect’s `git_clone` pull step).

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
  - `PREFECT_SERVER_API_HOST` = `0.0.0.0`
  - `PREFECT_UI_API_URL` = `https://<prefect-server-public-domain>/api`
    - This is critical on Railway. If this is missing or wrong, the Prefect UI can try to call
      `http://127.0.0.1:4200/api` (or another non-public address) and you’ll see “Can’t connect to Server API”.
    - Include the full scheme (`https://...`). If the UI receives an `api_url` without a scheme
      from `/ui-settings`, the UI may render as a blank page.

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

For the Prefect UI to work in the browser on Railway, also set:

- `PREFECT_UI_API_URL` on the server: `https://<prefect-server-public-domain>/api`

Note: `PREFECT_UI_API_URL` is the same setting as `PREFECT_SERVER_UI_API_URL`.

## Troubleshooting: Deployment shows “Not Ready”

In Prefect, a deployment/work pool is “Not Ready” when **no worker is connected and polling that work pool**.

Quick confirm (from your laptop):

```bash
export PREFECT_API_URL="https://<prefect-server-public-domain>/api"
prefect work-pool inspect hyperliquid-vault-ingestion
```

If it shows `status=WorkPoolStatus.NOT_READY`, fix it by ensuring your Railway **worker** service is actually running:

- You need a second Railway service (separate from the server `web` service).
- Start command must run the worker process, e.g. `prefect worker start --pool hyperliquid-vault-ingestion`.
- Worker env vars must include:
  - `PREFECT_API_URL` = `https://<prefect-server-public-domain>/api`
  - `DATABASE_URL` = your app DB URL

Once the worker connects, Prefect will mark the work pool/deployments as ready and scheduled runs will start executing.

Tip: verify you’re running the right process

- If your Railway logs say “Found web command in Procfile” and show `prefect server start ...`, that service is running the **server**, not the **worker**.
- The worker service logs should show `prefect worker start --pool hyperliquid-vault-ingestion`.

## Troubleshooting: Flow run crashes during `git_clone` ("No such file or directory: 'git'")

If your deployment uses remote code storage (like this repo’s `scripts/deploy_prefect_flows.py`), Prefect will run a `git_clone` pull step at flow-run start.

Symptom:

- Flow run enters `Crashed` quickly
- Logs include: `FileNotFoundError: [Errno 2] No such file or directory: 'git'`

Fix on Railway:

- Ensure the worker runtime includes `git`.
- This repo includes a [nixpacks.toml](nixpacks.toml) that installs `git` via `nixPkgs` (and keeps `aptPkgs` as a fallback).
- Redeploy the Railway worker service so the new runtime image is built.

## Alternative strategy: Run the worker as a Docker container

If you want to bypass Nixpacks entirely for the worker, this repo includes a dedicated worker Dockerfile:

- [Dockerfile.worker](Dockerfile.worker)

Railway setup (worker service):

- Deploy method: Dockerfile
- Dockerfile path: `Dockerfile.worker`
- Runtime env vars:
  - `PREFECT_API_URL` = `https://<prefect-server-public-domain>/api`
  - `DATABASE_URL` = your app DB URL
  - Optional: `PREFECT_WORK_POOL` (default: `hyperliquid-vault-ingestion`)

This guarantees `git` is installed in the worker image so Prefect deployments that use `git_clone` can start.
