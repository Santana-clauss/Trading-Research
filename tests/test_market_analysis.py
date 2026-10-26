import pandas as pd
import pytest

from src.market_analysis import detect_supply_demand_zones, prepare_price_action, summarize_price_action


def candles(count=60):
    close = [2000 + index for index in range(count)]
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=count, freq="15min", tz="UTC"),
        "open": [value - 0.5 for value in close],
        "high": [value + 1 for value in close],
        "low": [value - 1 for value in close],
        "close": close,
        "bar_complete_at_fetch": [True] * (count - 1) + [False],
    })


def test_price_action_uses_only_completed_bars_and_prior_range():
    result = prepare_price_action(candles())
    summary = summarize_price_action(result)

    assert len(result) == 59
    assert summary["close"] == 2058
    assert summary["rsi14"] == 100
    assert result.prior_range_high.iloc[-1] == 2058
    assert summary["timestamp"] == pd.Timestamp("2026-01-01 14:30:00+00:00")


def test_invalid_ohlc_rows_are_excluded():
    frame = candles(3)
    frame.loc[1, "high"] = frame.loc[1, "low"] - 1

    assert len(prepare_price_action(frame)) == 1


def test_flat_prices_have_neutral_rsi():
    frame = candles(20)
    frame[["open", "high", "low", "close"]] = 2000

    assert summarize_price_action(prepare_price_action(frame))["rsi14"] == 50


def test_demand_zone_is_created_after_break_then_retested_and_invalidated():
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=24, freq="15min", tz="UTC"),
        "open": [100.0] * 24,
        "high": [102.0] * 24,
        "low": [98.0] * 24,
        "close": [100.0] * 24,
        "atr14": [4.0] * 24,
    })
    frame.loc[10, "high"] = 110.0
    frame.loc[13, ["open", "high", "low", "close"]] = [106.0, 108.0, 102.0, 103.0]
    frame.loc[14, ["open", "high", "low", "close"]] = [105.0, 113.0, 104.0, 112.0]
    frame.loc[15:23, ["open", "high", "low", "close"]] = [111.0, 114.0, 109.0, 112.0]
    frame.loc[18, ["open", "high", "low", "close"]] = [109.0, 109.0, 105.0, 106.0]
    frame.loc[20, ["open", "high", "low", "close"]] = [104.0, 105.0, 100.0, 101.0]

    retested_zones = detect_supply_demand_zones(frame.iloc[:20], left=3, right=3, displacement_atr=1.0)
    zones = detect_supply_demand_zones(frame, left=3, right=3, displacement_atr=1.0)

    assert retested_zones[0]["touches"] == 1
    assert retested_zones[0]["status"] == "Retested 1"
    assert len(zones) == 1
    assert zones[0]["type"] == "Demand candidate"
    assert zones[0]["origin_time"] == frame.timestamp.iloc[13]
    assert zones[0]["created_at"] == frame.timestamp.iloc[14]
    assert zones[0]["touches"] == 1
    assert zones[0]["status"] == "Invalidated"
    assert zones[0]["status"] == "Invalidated"
    assert not zones[0]["active"]


def test_missing_columns_and_no_valid_bars_fail_clearly():
    with pytest.raises(ValueError, match="Missing market columns"):
        prepare_price_action(pd.DataFrame({"close": [1]}))

    frame = candles(1)
    frame["bar_complete_at_fetch"] = False
    with pytest.raises(ValueError, match="No completed"):
        prepare_price_action(frame)