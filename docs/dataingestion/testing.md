# Testing

Tests live under `tests/` and are written with `pytest`.

## Running tests

From the repo root:

```bash
pytest -q
```

If you need more detail:

```bash
pytest -q -vv
```

## What is covered

The parsing/unit tests focus on the metrics extraction logic used by the ingestion flow.

See:

- `tests/test_upsert_vaults_parsing.py`

Covered behaviors include:

- Extracting PnL scalars from the `portfolio` structure.
- Extracting volume (`vlm`) values and parsing numeric strings.
- Calculating max drawdown from `accountValueHistory`.
- Timestamp extraction / fallback behavior.
- Address extraction/dedup/filtering from the stats JSON.
- Diagnostics summary counting and row-building behavior.

## Philosophy

- Keep parsing logic testable (pure functions over dict/list inputs).
- Prefer unit tests for payload-shape correctness (Hyperliquid responses can change).
- Use integration testing via running the flow against a real DB only when needed (not required for the core parsing tests).
