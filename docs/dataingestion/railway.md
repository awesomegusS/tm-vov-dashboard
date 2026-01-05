# Railway (Prefect Server + Worker)

This setup runs a Prefect Server service on Railway, plus a separate Prefect Worker service.

In our working configuration, deployments use GitHub as code storage (Prefect `git_clone` pull step). The worker image is built from [Dockerfile.worker](Dockerfile.worker), which installs `git` so those pull steps succeed.

## Core idea

- Prefect Server runs as a Railway service.
- Prefect Worker runs as a separate Railway service.
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

4) Create the work pool (one-time, after the server is reachable)

You must create the process work pool on the server before the worker can pick up runs.

```bash
export PREFECT_API_URL="https://<prefect-server-public-domain>/api"
prefect work-pool create hyperliquid-vault-ingestion --type process
```

5) Create a Railway service for the worker:

Recommended: build the worker using [Dockerfile.worker](Dockerfile.worker). Railway will build and run this container for the worker service.

- Env vars:
  - `PREFECT_API_URL` = `https://<prefect-server-public-domain>/api`
  - `DATABASE_URL` = Postgres URL for your app DB (where `vaults`/`vault_metrics` live)
  - Optional: `PREFECT_WORK_POOL` (default is set in [Dockerfile.worker](Dockerfile.worker))

6) Create/update deployments (run from your laptop):

```bash
export PREFECT_API_URL="https://<prefect-server-public-domain>/api"

# Set the repo used as Prefect code storage
# e.g.
export PREFECT_DEPLOY_SOURCE="https://github.com/awesomegusS/tm-vov-dashboard.git"

# If your script is written to use remote source (GitHub storage), this registers
# deployments that will `git_clone` at runtime.
python scripts/deploy_prefect_flows.py --work-pool hyperliquid-vault-ingestion
```

Once deployments exist, Railway’s worker will pick up scheduled runs.

7) (Optional) Local smoke test: start a worker locally

If you want to quickly verify the server + pool wiring (and see runs picked up), you can start a process worker locally.

Important: set your local `PREFECT_API_URL` to the same public API URL used by the Prefect UI setting:

```bash
export PREFECT_API_URL="https://<prefect-server-public-domain>/api"
prefect worker start --pool hyperliquid-vault-ingestion
```

## Minimum required configuration

At minimum:

- `PREFECT_API_URL` on the worker: `https://<prefect-server-public-domain>/api`
- `DATABASE_URL` on the worker: the app Postgres URL (vaults/metrics tables)

Prefect Server also needs its own metadata DB URL (Prefect’s internal DB), typically configured as `PREFECT_API_DATABASE_CONNECTION_URL`.

For the Prefect UI to work in the browser on Railway, also set:

- `PREFECT_UI_API_URL` on the server: `https://<prefect-server-public-domain>/api`

Note: `PREFECT_UI_API_URL` is the same setting as `PREFECT_SERVER_UI_API_URL`.

## GitHub Actions (optional)

You can automate “create work pool (idempotent) + redeploy deployments” on each change to flow code or the deployment script.

- Workflow file: `.github/workflows/prefect_deploy.yml`
- Required GitHub repo secret: `PREFECT_API_URL` (set to `https://<prefect-server-public-domain>/api`)
- Required GitHub repo secret: `PREFECT_DEPLOY_SOURCE` (git URL used for deployments)

## Worker build notes

- Worker service deploy method: Dockerfile
- Dockerfile path: [Dockerfile.worker](Dockerfile.worker)
- Runtime env vars:
  - `PREFECT_API_URL` = `https://<prefect-server-public-domain>/api`
  - `DATABASE_URL` = your app DB URL
  - Optional: `PREFECT_WORK_POOL` (default: `hyperliquid-vault-ingestion`)

This is what ensures `git` is present for git-based code storage pull steps.
