"""Unit tests for EVM pools flow processing helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from src.pipelines.flows.evm_pools import (
    _timestamp_to_datetime_utc,
    build_evm_pool_metric_rows,
    build_evm_pool_rows,
    flag_usdc_pools,
)


def test_flag_usdc_pools_sets_accepts_usdc_true_when_symbol_contains_usdc() -> None:
    """Pools that contain 'usdc' in symbol are flagged as accepting USDC."""
    pools = [
        {"symbol": "USDC", "pool": "p1"},
        {"symbol": "eth", "pool": "p2"},
        {"symbol": "kUSDC-ETH", "pool": "p3"},
        {"symbol": None, "pool": "p4"},
    ]

    out = flag_usdc_pools(pools)

    assert out[0]["accepts_usdc"] is True
    assert out[1]["accepts_usdc"] is False
    assert out[2]["accepts_usdc"] is True
    assert out[3]["accepts_usdc"] is False


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
    pools = [{"chain": "Hyperliquid"}, {"pool": "p1", "symbol": "ETH"}]

    pool_rows = build_evm_pool_rows(pools)
    metric_rows = build_evm_pool_metric_rows(pools)

    assert len(pool_rows) == 1
    assert len(metric_rows) == 1
    assert pool_rows[0]["pool_id"] == "p1"
    assert metric_rows[0]["pool_id"] == "p1"
