# Hypercore Vaults Discovery Dashboard

This repo is the foundation for a **Hypercore vaults discovery dashboard**.

- **Dashboard UI (planned):** Streamlit
- **Hyper Core Data ingestion (Complete):** Prefect flows that ingest Hyperliquid vault + metrics data into Postgres
- **API (planned):** FastAPI endpoints once the data model stabilizes

## What’s in here today

### Data ingestion

The ingestion pipeline lives under `src/pipelines/flows/` and is orchestrated by Prefect.

- Prefect flow definitions: `src/pipelines/flows/`
- Deployment helper: `scripts/deploy_prefect_flows.py`
- Data ingestion docs: [docs/dataingestion/README.md](docs/dataingestion/README.md)
- Railway setup for Prefect Server + Worker: [docs/dataingestion/railway.md](docs/dataingestion/railway.md)

## Quickstart (local)

### 1) Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Point Prefect CLI at your server

```bash
export PREFECT_API_URL="https://<prefect-server-public-domain>/api"
```

### 3) (One-time) Create the work pool

```bash
prefect work-pool create hyperliquid-vault-ingestion --type process
```

### 4) Register deployments

Set the repo used as Prefect code storage:

```bash
export PREFECT_DEPLOY_SOURCE="https://github.com/awesomegusS/tm-vov-dashboard.git"

python scripts/deploy_prefect_flows.py --work-pool hyperliquid-vault-ingestion
```

### 5) Run a worker (optional local smoke test)

```bash
prefect worker start --pool hyperliquid-vault-ingestion
```

## Running on Railway

Railway is used for:
- Prefect Server (API + UI)
- A Prefect Worker service (process work pool)

See: [docs/dataingestion/railway.md](docs/dataingestion/railway.md)

## GitHub Actions (optional)

This repo includes a workflow that can automatically re-register deployments when flow code changes:
- Workflow: [.github/workflows/prefect_deploy.yml](.github/workflows/prefect_deploy.yml)
- Required repo secret: `PREFECT_API_URL`
- Optional repo secret: `PREFECT_DEPLOY_SOURCE`

## Roadmap

- Streamlit discovery dashboard (vault search/sort/detail views)
- FastAPI endpoints for programmatic access
- Expanded metrics + historical analysis
