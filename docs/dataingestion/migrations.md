# Alembic Migrations

Alembic is configured for async SQLAlchemy and includes schema-aware migrations.

Key files:

- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/*`

## Running migrations

From the repo root, with your environment activated and `DATABASE_URL` set:

```bash
alembic upgrade head
```

To check current revision:

```bash
alembic current
```

To see history:

```bash
alembic history
```

## Creating a new migration

Autogenerate (if models reflect desired schema changes):

```bash
alembic revision --autogenerate -m "your message"
```

Then review the generated migration carefully before applying.

## Included migrations (current)

These live in `alembic/versions/`:

- `a5aaa2b59ad0_init_schema_hyperliquid_vaults_discovery.py` — initial schema for `hyperliquid_vaults_discovery`
- `b1_add_vault_and_metrics_columns.py` — adds additional columns for vaults/metrics
- `c2_create_top_500_vaults.py` — adds the `top_500_vaults` table
- `c3_expand_vault_metrics_columns.py` — expands metrics column set
- `d4_drop_tvl_usd_from_vault_metrics.py` — drops `tvl_usd` from `vault_metrics`

## Notes on async + schemas

- `alembic/env.py` runs migrations with async engine semantics.
- Migrations target the `hyperliquid_vaults_discovery` schema, so ensure your Postgres role has privileges to create/alter objects in that schema.
