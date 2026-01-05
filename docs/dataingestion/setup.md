# Setup

This project is a Python service + Prefect flows.

## Prerequisites

- Python 3.11+ (recommended)
- A PostgreSQL database reachable from where flows run

## Install

From the repo root:

- Create/activate your environment (venv/conda is fine)
- Install requirements:

```bash
pip install -r requirements.txt
```

## Local sanity checks

- Run unit tests:

```bash
pytest -q
```

- Run the main flow locally (small limit first):

```bash
python -m src.pipelines.flows.upsert_vaults --concurrency 10 --limit 20
```

## Running with Prefect

Typical workflow:

1. Configure `DATABASE_URL` (see [Configuration](configuration.md)).
2. Start a Prefect worker pointing at your work pool (Cloud-managed or self-hosted server).
3. Create/update deployments via `scripts/deploy_prefect_flows.py` (see [Deployments](deployments.md)).
