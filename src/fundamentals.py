"""Released macro context for gold; observations are drivers, not price forecasts."""
from io import BytesIO
from urllib.request import Request, urlopen

import pandas as pd


SERIES = {
    "real_yield": {
        "id": "DFII10",
        "name": "10-year Treasury inflation-adjusted yield",
        "unit": "percentage points",
        "favorable_direction": -1,
        "threshold": 0.10,
        "source_url": "https://fred.stlouisfed.org/series/DFII10",
    },
    "broad_dollar": {
        "id": "DTWEXBGS",
        "name": "Broad trade-weighted U.S. dollar index",
        "unit": "index points",
        "favorable_direction": -1,
        "threshold": 0.25,
        "source_url": "https://fred.stlouisfed.org/series/DTWEXBGS",
    },
}


def fetch_fred_series(series_id, *, timeout=20):
    """Fetch public FRED graph CSV; no API key or synthetic fallback is used."""
    if series_id not in {series["id"] for series in SERIES.values()}:
        raise ValueError(f"Unsupported FRED series: {series_id}")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    request = Request(url, headers={"User-Agent": "GoldMarketMonitor/1.0 (research dashboard)"})
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(5_000_001)
    if len(payload) > 5_000_000:
        raise ValueError("FRED response exceeded the 5MB limit.")
    frame = pd.read_csv(BytesIO(payload))
    if not {"observation_date", series_id} <= set(frame.columns):
        raise ValueError(f"Unexpected FRED response columns for {series_id}.")
    frame["date"] = pd.to_datetime(frame.observation_date, errors="coerce")
    frame["value"] = pd.to_numeric(frame[series_id].replace(".", pd.NA), errors="coerce")
    frame = frame.dropna(subset=["date", "value"]).sort_values("date", kind="stable")
    if frame.empty:
        raise ValueError(f"FRED returned no usable observations for {series_id}.")
    return frame[["date", "value"]].reset_index(drop=True)


def summarize_fred_series(series_id, observations, *, today=None, lookback=20):
    """Summarize a released series against its value 20 observations earlier."""
    spec = next((item for item in SERIES.values() if item["id"] == series_id), None)
    if spec is None:
        raise ValueError(f"Unsupported FRED series: {series_id}")
    if lookback < 1:
        raise ValueError("lookback must be positive")
    data = observations.dropna(subset=["date", "value"]).sort_values("date", kind="stable")
    if data.empty:
        raise ValueError(f"No observations available for {series_id}.")
    latest = data.iloc[-1]
    today = pd.Timestamp.now().normalize() if today is None else pd.Timestamp(today).normalize()
    age_days = max(0, (today - pd.Timestamp(latest.date).normalize()).days)
    enough_history = len(data) > lookback
    previous = float(data.value.iloc[-lookback - 1]) if enough_history else None
    latest_value = float(latest.value)
    change = latest_value - previous if previous is not None else None
    stale = age_days > 7
    if stale or change is None or abs(change) < spec["threshold"]:
        view = "stale" if stale else "mixed / little change"
        gold_score = 0
    else:
        macro_direction = 1 if change > 0 else -1
        gold_score = macro_direction * spec["favorable_direction"]
        view = "gold headwind" if gold_score < 0 else "gold tailwind"
    return {
        "id": series_id,
        "name": spec["name"],
        "unit": spec["unit"],
        "source_url": spec["source_url"],
        "latest": latest_value,
        "date": pd.Timestamp(latest.date),
        "age_days": age_days,
        "change": change,
        "lookback_observations": lookback,
        "gold_score": gold_score,
        "view": view,
        "stale": stale,
    }


def combine_macro_context(summaries):
    """Return a small directional context score without probability language."""
    usable = [summary for summary in summaries if not summary["stale"]]
    score = sum(summary["gold_score"] for summary in usable)
    if not usable:
        view = "Macro data are stale or unavailable"
    elif score >= 1:
        view = "Macro conditions lean supportive for gold"
    elif score <= -1:
        view = "Macro conditions lean against gold"
    else:
        view = "Macro signals are mixed"
    return {"score": score, "view": view, "usable_series": len(usable)}