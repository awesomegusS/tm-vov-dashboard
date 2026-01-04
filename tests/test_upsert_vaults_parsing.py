import math


from src.pipelines.flows.upsert_vaults import (
    _calculate_max_drawdown,
    _extract_addresses_from_vaults_json,
    _extract_pnl,
    _extract_volume,
    _summarize_details_results,
    build_metric_rows_from_details,
)


def _portfolio(*, day=None, week=None, month=None, all_time=None):
    """Build a portfolio payload matching Hyperliquid vaultDetails shape.

    Each period is encoded as [period_key, {pnlHistory, accountValueHistory, vlm}].
    """

    def mk(period_key, body):
        if body is None:
            return None
        return [period_key, body]

    out = []
    for key, body in (
        ("day", day),
        ("week", week),
        ("month", month),
        ("allTime", all_time),
    ):
        pair = mk(key, body)
        if pair is not None:
            out.append(pair)
    return out


def test_extract_pnl_returns_last_value_for_period():
    portfolio = _portfolio(
        day={
            "pnlHistory": [
                [1000, "1.25"],
                [2000, "-0.50"],
            ]
        }
    )

    assert _extract_pnl(portfolio, "day") == -0.5


def test_extract_pnl_missing_period_returns_none():
    portfolio = _portfolio(day={"pnlHistory": [[1000, "1.0"]]})
    assert _extract_pnl(portfolio, "month") is None


def test_extract_volume_parses_numeric_string():
    portfolio = _portfolio(month={"vlm": "440.82"})
    assert _extract_volume(portfolio, "month") == 440.82


def test_extract_volume_missing_returns_none():
    portfolio = _portfolio(day={})
    assert _extract_volume(portfolio, "day") is None


def test_calculate_max_drawdown_percent_basic():
    # Values: 100 -> 120 (peak) -> 90 (trough) => drawdown = (90-120)/120 = -0.25 => 25%
    portfolio = _portfolio(
        day={
            "accountValueHistory": [
                [1000, "100"],
                [2000, "120"],
                [3000, "90"],
                [4000, "110"],
            ]
        }
    )
    dd = _calculate_max_drawdown(portfolio, "day")
    assert dd is not None
    assert math.isclose(dd, 25.0, rel_tol=1e-12, abs_tol=1e-12)


def test_calculate_max_drawdown_handles_zero_then_positive_peak():
    # Start at 0 (no dd computed), then peak 10, then drop to 5 => 50%
    portfolio = _portfolio(
        day={
            "accountValueHistory": [
                [1000, "0"],
                [2000, "10"],
                [3000, "5"],
            ]
        }
    )
    dd = _calculate_max_drawdown(portfolio, "day")
    assert dd is not None
    assert math.isclose(dd, 50.0, rel_tol=1e-12, abs_tol=1e-12)


def test_calculate_max_drawdown_no_values_returns_none():
    portfolio = _portfolio(day={"accountValueHistory": []})
    assert _calculate_max_drawdown(portfolio, "day") is None


def test_extract_addresses_from_vaults_json_dedupes_and_orders():
    vaults = [
        {"summary": {"vaultAddress": "0xaaa"}},
        {"summary": {"vaultAddress": "0xbbb"}},
        {"summary": {"vaultAddress": "0xaaa"}},
        {"vaultAddress": "0xccc"},
        {"summary": {}},
        {},
    ]

    assert _extract_addresses_from_vaults_json(vaults) == ["0xaaa", "0xbbb", "0xccc"]


def test_build_metric_rows_handles_missing_portfolio_and_skips_errors():
    details = {
        "0xgood": {
            "maxDistributable": "123.45",
            "apr": 0.12,
            # No portfolio key
        },
        "0xerr": {"error": "rate limited", "status_code": 429},
        "0xempty": {},
    }
    rows = build_metric_rows_from_details(details)
    assert len(rows) == 1
    assert rows[0]["vault_address"] == "0xgood"
    assert rows[0]["vlm_day"] is None
    assert rows[0]["max_drawdown_day"] is None


def test_build_metric_rows_missing_fields_still_emits_row_with_nulls():
    details = {
        "0xabc": {
            # missing maxDistributable, pnlHistory, accountValueHistory, vlm
            "portfolio": [],
        }
    }

    rows = build_metric_rows_from_details(details)
    assert len(rows) == 1
    row = rows[0]
    assert row["vault_address"] == "0xabc"
    assert row["timestampz"] is not None
    assert getattr(row["timestampz"], "tzinfo", None) is not None
    assert row["max_distributable_tvl"] is None
    assert row["vlm_day"] is None
    assert row["max_drawdown_day"] is None


def test_build_metric_rows_skips_non_dict_payloads():
    details = {
        "0x2": ["unexpected"],
        "0x4": {"portfolio": [], "maxDistributable": "1.23"},
    }

    rows = build_metric_rows_from_details(details)
    assert len(rows) == 1
    assert rows[0]["vault_address"] == "0x4"
    assert rows[0]["max_distributable_tvl"] == 1.23


def test_summarize_details_results_counts_errors_empty_non_dict_and_missing_fields():
    addresses = ["0x1", "0x2", "0x3", "0x4"]
    details = {
        "0x1": {"error": "rate limited", "status_code": 429},
        "0x2": None,
        "0x3": ["unexpected"],
        "0x4": {"portfolio": [], "maxDistributable": None},
    }

    diag = _summarize_details_results(addresses, details)
    assert diag["addresses_total"] == 4
    assert diag["details_returned"] == 4
    assert diag["error_count"] == 1
    assert diag["empty_count"] == 1
    assert diag["non_dict_count"] == 1
    assert diag["missing_portfolio_count"] == 0
    assert diag["empty_portfolio_count"] == 1
    assert diag["missing_max_distributable_count"] == 1
    assert diag["status_code_counts"] == {429: 1}
