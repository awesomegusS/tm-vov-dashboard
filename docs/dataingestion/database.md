# Database and Models

The database schema is `hyperliquid_vaults_discovery`.

Models are defined in `src/models/vault.py`.

## Tables

### `hyperliquid_vaults_discovery.vaults`

Stores relatively static vault metadata.

Common columns (non-exhaustive):

- `vault_address` (primary key)
- `name`
- `leader_address`
- `description`
- `tvl_usd`
- `is_closed`
- `relationship_type`
- `vault_create_time`
- `created_at`, `updated_at`

The hourly flow upserts these rows first.

### `hyperliquid_vaults_discovery.vault_metrics`

Stores time-series metrics per vault.

Important constraints:

- Composite primary key: `(time, vault_address)`
- `time` is NOT NULL

Selected metric columns (non-exhaustive; see `VaultMetric` for authoritative list):

- `max_distributable_tvl`
- `pnl_day`, `pnl_week`, `pnl_month`, `pnl_year`, `pnl_all_time`
- `vlm_day`, `vlm_week`, `vlm_month`, `vlm_year`, `vlm_all_time`
- `max_drawdown_day`, `max_drawdown_week`, `max_drawdown_month`, `max_drawdown_year`, `max_drawdown_all_time`

Notes:

- The ingestion logic treats missing `maxDistributable` as NULL (rather than inventing 0).
- The `tvl_usd` column was explicitly dropped from `vault_metrics` via migration (see [Migrations](migrations.md)).

### `hyperliquid_vaults_discovery.top_500_vaults`

A small table storing a point-in-time ranking of the 500 vaults with highest `max_distributable_tvl` from the latest available metric row per vault.

Populated by `update_top_500_flow`.

## Access layer

- DB sessions are created via `src/core/database.py` (`AsyncSessionLocal`).
- Writes use SQLAlchemy `insert(...).on_conflict_do_update(...)` for upserts.
- Upserts are batched to avoid the `asyncpg` bind-parameter limit (32,767 parameters).
