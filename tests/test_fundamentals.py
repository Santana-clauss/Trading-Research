import pandas as pd
import pytest

from src.fundamentals import combine_macro_context, summarize_fred_series


def observations(values, start="2026-01-01"):
    return pd.DataFrame({
        "date": pd.date_range(start, periods=len(values), freq="B"),
        "value": values,
    })


def test_real_yield_falling_is_macro_tailwind_for_gold():
    values = [4.0] * 20 + [3.8]
    result = summarize_fred_series(
        "DFII10", observations(values), today="2026-02-01", lookback=20
    )

    assert result["change"] == pytest.approx(-0.2)
    assert result["view"] == "gold tailwind"
    assert result["gold_score"] == 1


def test_rising_dollar_is_macro_headwind_and_stale_data_is_neutral():
    values = [100.0] * 20 + [100.5]
    fresh = summarize_fred_series(
        "DTWEXBGS", observations(values), today="2026-02-01", lookback=20
    )
    stale = summarize_fred_series(
        "DFII10", observations(values), today="2026-04-01", lookback=20
    )

    assert fresh["view"] == "gold headwind"
    assert fresh["gold_score"] == -1
    assert stale["stale"]
    assert stale["gold_score"] == 0


def test_macro_summary_does_not_call_mixed_inputs_a_forecast():
    summaries = [
        {"stale": False, "gold_score": 1},
        {"stale": False, "gold_score": -1},
        {"stale": True, "gold_score": 1},
    ]

    assert combine_macro_context(summaries) == {
        "score": 0, "view": "Macro signals are mixed", "usable_series": 2
    }