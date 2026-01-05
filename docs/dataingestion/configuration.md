# Configuration

## Environment variables

### `DATABASE_URL`

Required for DB writes.

- The code expects a Postgres URL.
- Async SQLAlchemy is used.
- `src/core/database.py` rewrites URLs that start with `postgresql://` into `postgresql+asyncpg://` so `asyncpg` is used.

Example:

```bash
export DATABASE_URL='postgresql://user:pass@host:5432/dbname'
```

### Prefect secrets fallback (optional)

If `DATABASE_URL` is not set, `src/core/database.py` attempts to load a Prefect secret block named `database-url`.

This allows deployments/agents to run without injecting `DATABASE_URL` directly, as long as the Prefect environment has that secret configured.

## Operational notes

- Prefect-managed workers that pull code from git cannot rely on local generated files under `data/`. The main flow fetches the canonical vault list from the Hyperliquid stats endpoint at runtime.
