"""Unit tests for EVM pools flow processing helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from src.pipelines.flows.evm_pools import (
    _timestamp_to_datetime_utc,
    build_evm_pool_metric_rows,
    build_evm_pool_rows,
)


def test_timestamp_to_datetime_utc_handles_seconds_and_millis() -> None:
    """Timestamp conversion supports both seconds and milliseconds."""
    dt_seconds = _timestamp_to_datetime_utc(1_700_000_000)
    dt_millis = _timestamp_to_datetime_utc(1_700_000_000_000)

    assert isinstance(dt_seconds, datetime)
    assert isinstance(dt_millis, datetime)
    assert dt_seconds.tzinfo == timezone.utc
    assert dt_millis.tzinfo == timezone.utc


def test_build_rows_skips_missing_pool_id() -> None:
    """Rows are only built when 'pool' (pool_id) is present."""
    pools = [{"chain": "Hyperliquid"}, {"pool": "p1", "symbol": "ETH", "source": "defillama"}]

    pool_rows = build_evm_pool_rows(pools)
    metric_rows = build_evm_pool_metric_rows(pools)

    assert len(pool_rows) == 1
    assert len(metric_rows) == 1
    assert pool_rows[0]["pool_id"] == "p1"
    assert pool_rows[0]["source"] == "defillama"
    assert metric_rows[0]["pool_id"] == "p1"

def test_build_rows_handles_new_metrics() -> None:
    """Ensure new metrics in EvmPoolMetric are captured."""
    pools = [{
        "pool": "p1",
        "symbol": "ETH",
        "tvl_usd": 1000.0,
        "total_debt_usd": 500.0,
        "utilization_rate": 50.0,
        "apy_borrow_variable": 5.0,
        "apy_borrow_stable": 2.0,
        "source": "felix"
    }]

    pool_rows = build_evm_pool_rows(pools)
    metric_rows = build_evm_pool_metric_rows(pools)

    assert len(pool_rows) == 1
    assert pool_rows[0]["source"] == "felix"
    
    m = metric_rows[0]
    assert m["tvl_usd"] == 1000.0
    assert m["total_debt_usd"] == 500.0
    assert m["utilization_rate"] == 50.0
    assert m["apy_borrow_variable"] == 5.0
    assert m["apy_borrow_stable"] == 2.0
