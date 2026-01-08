# Hyperliquid & HyperEVM Vaults Dashboard

**Current Status:**
- ✅ **Data Ingestion:** Complete (Hybrid architecture: DeFi Llama + Direct RPC).
- 🚧 **Dashboard UI (Streamlit):** In Progress / Coming Soon.
- 🚧 **API (FastAPI):** In Progress / Coming Soon.

## Purpose
This repository houses the backend infrastructure for observing and analyzing vaults and pools across the **Hyperliquid L1** and **HyperEVM** ecosystem (Felix, Hyperlend, HypurrFi, Hyperbeat). It orchestrates reliable data ingestion pipelines to feed a downstream analytics dashboard.

## Key Features
- **Hybrid Data Collection:** Combines broad discovery from **DeFi Llama** with deep, real-time metrics (LTV, Borrow APY, Risk Params) via **Direct RPC** calls.
- **Protocol Support:** 
  - **Native:** Hyperliquid Vaults (HLP, User Vaults).
  - **EVM:** Felix Protocol, Hyperlend, HypurrFi, Hyperbeat.
- **Robust Storage:** Data is normalized and persisted in PostgreSQL using SQLAlchemy models.
- **Orchestration:** Prefect flows manage hourly syncs, retries, and error handling.

## Project Structure

| Directory | Description |
|-----------|-------------|
| `src/pipelines/flows/` | Prefect workflows (e.g., `evm_pools.py`, `upsert_vaults.py`) that orchestrate data fetching. |
| `src/services/` | Protocol-specific RPC clients (`felix_client.py`, `hyperliquid.py`, etc.) and adaptors. |
| `src/models/` | SQLAlchemy database definitions (`evm_pool.py`, `vault.py`) defining the schema. |
| `src/core/` | Core configuration, database sessions, and secrets management. |
| `alembic/` | Database schema migrations and version control. |
| `scripts/` | Deployment utilities (`deploy_prefect_flows.py`) and ad-hoc scripts. |
| `docs/` | Detailed architectural documentation and setup guides. |
| `data/` | Local data snapshots and temporary files (ignored by git). |

## Quick Start (Local Ingestion)

### 1. Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
Ensure you have a PostgreSQL database running and a `.env` file or environment variables set for `DATABASE_URL` and `PREFECT_API_URL`.

### 3. Deploy/Run Flows
To register the flows with your Prefect server:
```bash
python scripts/deploy_prefect_flows.py --work-pool hyperliquid-vault-ingestion
```

To run a worker locally:
```bash
prefect worker start --pool hyperliquid-vault-ingestion
```

## Documentation
See the `docs/` folder for in-depth guides:
- [**System Overview**](docs/dataingestion/overview.md)
- [**Database Architecture**](docs/dataingestion/database.md)
- [**Hybrid Ingestion Details**](docs/dataingestion/defillama-evm-pools.md)
- [**Railway Deployment**](docs/dataingestion/railway.md)

---
*Built with Python 3.13, Prefect, SQLAlchemy, and Web3.py*
