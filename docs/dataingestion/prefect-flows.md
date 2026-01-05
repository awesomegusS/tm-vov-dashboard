# Prefect Flows

Flow code is in `src/pipelines/flows/upsert_vaults.py`.

## `upsert_vault_metrics_flow`

Flow name: `Upsert Vault and Performance Metrics`

Purpose:

- Fetch canonical vault list from Hyperliquid stats endpoint.
- Upsert `vaults` metadata.
- Fetch per-vault `vaultDetails` from Hyperliquid `/info`.
- Parse time-series metrics from the `portfolio` payload.
- Upsert `vault_metrics` (batched).

Key parameters:

- `concurrency` (default 10): max in-flight detail requests.
- `requests_per_second` (default 3.0): global pacing across concurrent tasks.
- `active_only` (default True): only ingest non-closed vaults.
- `limit` (optional): cap number of addresses processed.
- `addresses` (optional): explicit address list to override stats-derived list.

Operational notes:

- The flow logs a diagnostics summary of the `vaultDetails` fetch results (errors, empty payloads, missing `portfolio`, HTTP status counts).
- Parsed metric rows are logged in small samples for observability.
- Batched upserts are used to avoid exceeding the `asyncpg` bind-parameter limit.

## `update_top_500_flow`

Flow name: `get top 500 vaults by TVL`

Purpose:

- Reads the latest `vault_metrics` row per vault (by `time`).
- Ranks vaults by `max_distributable_tvl`.
- Writes the top 500 to `top_500_vaults`.

Implementation detail:

- Uses a window function (`ROW_NUMBER() OVER (PARTITION BY vault_address ORDER BY time DESC)`) to select the latest metrics row.
