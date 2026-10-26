"""Descriptive market context from completed OHLC bars; not a trading signal."""
import numpy as np
import pandas as pd


def prepare_price_action(candles, lookback=20):
    """Return completed candles with causal trend, range and volatility context."""
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(candles.columns)
    if missing:
        raise ValueError(f"Missing market columns: {sorted(missing)}")
    if lookback < 2:
        raise ValueError("lookback must be at least 2")

    data = candles.copy()
    if "bar_complete_at_fetch" in data:
        data = data.loc[data.bar_complete_at_fetch.fillna(False)].copy()
    data = data.sort_values("timestamp", kind="stable").reset_index(drop=True)
    valid = (np.isfinite(data[["open", "high", "low", "close"]]).all(axis=1)
             & (data.low <= data[["open", "close"]].min(axis=1))
             & (data.high >= data[["open", "close"]].max(axis=1))
             & (data.high >= data.low))
    data = data.loc[valid].copy().reset_index(drop=True)
    if data.empty:
        raise ValueError("No completed, valid OHLC candles are available.")

    previous_close = data.close.shift(1)
    true_range = pd.concat([
        data.high - data.low,
        (data.high - previous_close).abs(),
        (data.low - previous_close).abs(),
    ], axis=1).max(axis=1)
    data["atr14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    data["ema20"] = data.close.ewm(span=20, adjust=False).mean()
    data["ema50"] = data.close.ewm(span=50, adjust=False).mean()
    change = data.close.diff()
    average_gain = change.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    average_loss = -change.clip(upper=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    data["rsi14"] = 100 - (100 / (1 + relative_strength))
    data.loc[average_loss.eq(0) & average_gain.gt(0), "rsi14"] = 100.0
    data.loc[average_loss.eq(0) & average_gain.eq(0), "rsi14"] = 50.0
    data["prior_range_high"] = data.high.rolling(lookback, min_periods=lookback).max().shift(1)
    data["prior_range_low"] = data.low.rolling(lookback, min_periods=lookback).min().shift(1)
    data["change_1bar"] = data.close.diff()
    data["change_4bar"] = data.close.diff(4)
    data["range_position"] = (
        (data.close - data.prior_range_low)
        / (data.prior_range_high - data.prior_range_low).replace(0, np.nan)
    )
    data["range_break"] = np.select(
        [data.close > data.prior_range_high, data.close < data.prior_range_low],
        ["Above prior range", "Below prior range"],
        default="Inside prior range",
    )
    return data


def summarize_price_action(data):
    """Summarize the last completed bar without converting context to a forecast."""
    if data.empty:
        raise ValueError("No candles available to summarize.")
    latest = data.iloc[-1]
    close = float(latest.close)
    if close > latest.ema20 and latest.ema20 > latest.ema50:
        trend = "Bullish alignment"
    elif close < latest.ema20 and latest.ema20 < latest.ema50:
        trend = "Bearish alignment"
    else:
        trend = "Mixed / transitioning"
    return {
        "timestamp": latest.timestamp,
        "close": close,
        "change_1bar": latest.change_1bar,
        "change_4bar": latest.change_4bar,
        "atr14": latest.atr14,
        "trend": trend,
        "range_break": latest.range_break,
        "range_position": latest.range_position,
        "ema20": latest.ema20,
        "ema50": latest.ema50,
        "rsi14": latest.rsi14,
        "bar_range": float(latest.high - latest.low),
    }


def detect_supply_demand_zones(data, *, left=3, right=3, search_bars=10,
                               displacement_atr=1.0, zone_life=96, max_zones=8):
    """Find price-action candidate zones without inferring resting institutional orders."""
    if data.empty:
        return []
    if min(left, right, search_bars, zone_life, max_zones) < 1:
        raise ValueError("Pivot, search, lifetime, and zone limits must be positive.")

    highs = data.high.to_numpy(dtype=float)
    lows = data.low.to_numpy(dtype=float)
    opens = data.open.to_numpy(dtype=float)
    closes = data.close.to_numpy(dtype=float)
    atr = data.atr14.to_numpy(dtype=float)
    zones = []
    swing_high = swing_low = np.nan
    swing_high_used = swing_low_used = False
    last_direction = 0

    for index in range(len(data)):
        close = closes[index]
        up_break = np.isfinite(swing_high) and not swing_high_used and close > swing_high
        down_break = np.isfinite(swing_low) and not swing_low_used and close < swing_low
        direction = 1 if up_break and not down_break else -1 if down_break and not up_break else 0
        if direction == 1:
            swing_high_used = True
            last_direction = 1
        elif direction == -1:
            swing_low_used = True
            last_direction = -1

        for zone in zones:
            if not zone["active"]:
                continue
            broken = close < zone["bottom"] if zone["direction"] == 1 else close > zone["top"]
            expired = index - zone["born_index"] > zone_life
            if broken or expired:
                zone["active"] = False
                zone["status"] = "Invalidated" if broken else "Expired"
                continue
            overlap = index > zone["born_index"] and highs[index] >= zone["bottom"] and lows[index] <= zone["top"]
            if overlap and not zone["inside"]:
                zone["touches"] += 1
                zone["last_touch"] = data.timestamp.iloc[index]
                zone["status"] = f"Retested {zone['touches']}"
            zone["inside"] = overlap

        prior_atr = atr[index - 1] if index > 0 else np.nan
        directional_body = direction == 1 and closes[index] > opens[index] or direction == -1 and closes[index] < opens[index]
        if (direction and directional_body and np.isfinite(prior_atr)
                and abs(closes[index] - opens[index]) >= displacement_atr * prior_atr):
            opposing_index = None
            for offset in range(1, min(search_bars, index) + 1):
                candidate = index - offset
                opposing = closes[candidate] < opens[candidate] if direction == 1 else closes[candidate] > opens[candidate]
                if opposing:
                    opposing_index = candidate
                    break
            if opposing_index is not None:
                top = highs[opposing_index]
                bottom = lows[opposing_index]
                departed = closes[index] > top if direction == 1 else closes[index] < bottom
                if top > bottom and departed:
                    zones.append({
                        "top": float(top),
                        "bottom": float(bottom),
                        "direction": direction,
                        "type": "Demand candidate" if direction == 1 else "Supply candidate",
                        "origin_time": data.timestamp.iloc[opposing_index],
                        "created_at": data.timestamp.iloc[index],
                        "born_index": index,
                        "age_bars": 0,
                        "touches": 0,
                        "last_touch": None,
                        "inside": False,
                        "active": True,
                        "status": "Fresh",
                    })
                    zones = zones[-max_zones:]

        pivot_index = index - right
        if pivot_index >= left:
            high_window = highs[pivot_index - left:index + 1]
            low_window = lows[pivot_index - left:index + 1]
            if highs[pivot_index] == high_window.max() and np.count_nonzero(high_window == highs[pivot_index]) == 1:
                swing_high = highs[pivot_index]
                swing_high_used = False
            if lows[pivot_index] == low_window.min() and np.count_nonzero(low_window == lows[pivot_index]) == 1:
                swing_low = lows[pivot_index]
                swing_low_used = False

    latest_index = len(data) - 1
    latest_close = closes[latest_index]
    latest_atr = atr[latest_index]
    for zone in zones:
        zone["age_bars"] = latest_index - zone["born_index"]
        zone["distance"] = max(zone["bottom"] - latest_close, latest_close - zone["top"], 0.0)
        zone["distance_atr"] = zone["distance"] / latest_atr if np.isfinite(latest_atr) and latest_atr > 0 else np.nan
        zone.pop("born_index")
        zone.pop("inside")
    return list(reversed(zones))