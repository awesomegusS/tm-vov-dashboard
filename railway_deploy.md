# Railway deploy (Prefect Server + Worker)

This repo can run **Prefect Server** and a **Prefect Worker** on Railway to avoid Prefect Cloud “managed compute” limits.

## What you’ll create in Railway
- **Postgres (Prefect metadata DB)**: used by Prefect Server
- **Service: `prefect-server`**: runs the API/UI (`Procfile` process `web`)
- **Service: `prefect-worker`**: runs flow executions (`Procfile` process `worker`)
- **(Optional) Postgres (app DB)**: where your flows write vault/vault_metrics tables (this is `DATABASE_URL`)

## Procfile processes
- `web`: `prefect server start --host 0.0.0.0 --port $PORT`
- `worker`: `prefect worker start --pool hyperliquid-vault-ingestion`

## Railway UI steps

### 1) Create a new Railway project
- Railway → **New Project** → **Deploy from GitHub repo** → select `tm-vov-dashboard` repo.

### 2) Add Postgres for Prefect Server metadata
- In the project: **Add** → **Database** → **PostgreSQL**.
- Note the connection URL (Railway provides `DATABASE_URL` on the DB service).

### 3) Create the `prefect-server` service
- Add a **new service from the same GitHub repo** (or duplicate the existing repo service).
- In the service settings:
  - **Start Command / Procfile process**: `web`
  - **Environment variables** (set on the `prefect-server` service):
    - `PREFECT_API_DATABASE_CONNECTION_URL` = Postgres URL for Prefect metadata.
      - If Railway gives `postgresql://...`, Prefect generally works with it; if you hit driver errors, use `postgresql+asyncpg://...`.

After deploy, Railway will provide a public URL for this service.

### 4) Create the `prefect-worker` service
- Add another **service from the same GitHub repo**.
- In the service settings:
  - **Start Command / Procfile process**: `worker`
  - **Environment variables** (set on the `prefect-worker` service):
    - `PREFECT_API_URL` = `https://<prefect-server-public-domain>/api`
    - `DATABASE_URL` = Postgres URL for your *application* database (the DB your flows upsert into).
      - This can be an existing external Postgres, or add another Railway Postgres plugin dedicated to the app DB.

## Initialize Prefect (one-time)
Do this from your laptop (or any machine with Prefect installed) after the `prefect-server` is up.

1) Point your CLI at Railway Prefect Server:
- `export PREFECT_API_URL="https://<prefect-server-public-domain>/api"`

2) Create the work pool (self-hosted):
- `prefect work-pool create hyperliquid-vault-ingestion --type process`

3) Create deployments (remote git source) for the flows:
- `conda run -n tm-vov-dashboard python - <<'PY'
from prefect import flow
from prefect.schedules import Cron

try:
    from prefect.runner.storage import GitRepository
    src = GitRepository(url="https://github.com/awesomegusS/tm-vov-dashboard.git", reference="master")
except Exception:
    # Fallback: Prefect also accepts a plain URL
    src = "https://github.com/awesomegusS/tm-vov-dashboard.git"

# Hourly vault metrics
flow.from_source(source=src, entrypoint="src/pipelines/flows/upsert_vaults.py:upsert_vault_metrics_flow").deploy(
    name="hourly-vault-metrics",
    work_pool_name="hyperliquid-vault-ingestion",
    schedules=[Cron("0 * * * *", timezone="UTC")],
)

# Top 500 refresh (every 4 hours)
flow.from_source(source=src, entrypoint="src/pipelines/flows/upsert_vaults.py:update_top_500_flow").deploy(
    name="top-500-vaults",
    work_pool_name="hyperliquid-vault-ingestion",
    schedules=[Cron("0 */4 * * *", timezone="UTC")],
)
PY`

Once those exist, the `prefect-worker` service on Railway will pick up scheduled runs and execute them.

## Troubleshooting
- Worker can’t connect:
  - Confirm `PREFECT_API_URL` on the worker ends with `/api`.
- DB errors in flow runs:
  - Confirm `DATABASE_URL` is set on the worker service (this is the DB your app writes to).
- Prefect Server won’t start:
  - Confirm `PREFECT_API_DATABASE_CONNECTION_URL` points at the Prefect metadata Postgres.
