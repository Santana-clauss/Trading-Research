"""Non-destructive candle checks and reusable JSON-friendly reports."""
from dataclasses import dataclass, asdict
import json
import numpy as np
import pandas as pd

REQUIRED = ("timestamp", "open", "high", "low", "close")


@dataclass
class QualityReport:
    summary: dict
    issues: list

    @property
    def status(self):
        levels = {issue["severity"] for issue in self.issues}
        return "FAIL" if "ERROR" in levels else "WARNING" if "WARNING" in levels else "PASS"

    def to_dict(self):
        return {"status": self.status, **asdict(self)}

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, allow_nan=False)

    def __str__(self):
        s = self.summary
        lines = [f"Data quality: {self.status}", f"Input: {s['input_filename']}",
                 f"Rows loaded: {s['rows_loaded']}",
                 f"UTC range: {s['earliest_timestamp']} -> {s['latest_timestamp']}",
                 f"Timeframe: {s['detected_timeframe']} (assumed: {s['assumed_timeframe']})",
                 f"Duplicate timestamps (extra rows): {s['duplicate_timestamp_count']}",
                 f"Invalid OHLC candles: {s['invalid_ohlc_count']}",
                 f"Unobserved interval slots: {s['missing_interval_count']} (closures not excluded)",
                 f"Timezone-aware: {s['timezone_aware']}",
                 f"Missing values: {s['missing_value_counts']}"]
        for item in self.issues:
            lines.append(f"{item['severity']} {item['code']}: {item['message']} | rows={item['rows']}")
        return "\n".join(lines)


def validate_candles(frame, *, filename="<memory>", expected_timeframe=None,
                     metadata=None, initial_issues=None):
    """Rows reference logical CSV records (header is row 1), not sorted indices."""
    metadata = metadata or {}
    issues = list(initial_issues or [])

    def add(level, code, message, mask=None):
        rows = [] if mask is None else frame.loc[mask, "source_row"].astype(int).tolist()
        issues.append(dict(severity=level, code=code, message=message, rows=rows))

    missing = [c for c in REQUIRED if c not in frame]
    if missing:
        add("ERROR", "missing_columns", f"Required columns absent: {missing}")
    if frame.empty:
        add("ERROR", "no_rows", "No candle records.")
    counts = {c: int(frame[c].isna().sum()) for c in REQUIRED if c in frame}
    invalid = pd.Series(False, index=frame.index)
    for c in ("open", "high", "low", "close"):
        if c not in frame:
            continue
        numeric = pd.to_numeric(frame[c], errors="coerce")
        bad = numeric.isna() | ~np.isfinite(numeric) | (numeric <= 0)
        invalid |= bad
        if bad.any():
            add("ERROR", "invalid_price", f"{c}: missing, non-numeric, non-finite or non-positive.", bad)
    if all(c in frame for c in ("open", "high", "low", "close")):
        o, h, l, c = (pd.to_numeric(frame[k], errors="coerce") for k in ("open", "high", "low", "close"))
        bad = (h < l) | (h < o) | (h < c) | (l > o) | (l > c)
        invalid |= bad
        if bad.any():
            add("ERROR", "ohlc_relationship", "High/low do not contain open and close.", bad)
    for c in ("tick_volume", "real_volume", "spread"):
        if c not in frame:
            add("WARNING", "optional_missing", f"{c} is unavailable.")
        else:
            values = frame[c]
            bad = values.isna() | ~np.isfinite(values) | (values < 0)
            counts[c] = int(values.isna().sum())
            if bad.any():
                add("WARNING", "optional_invalid", f"{c}: missing, non-finite or negative.", bad)

    ts = frame["timestamp"] if "timestamp" in frame else pd.Series([], dtype="datetime64[ns, UTC]")
    aware = isinstance(ts.dtype, pd.DatetimeTZDtype)
    valid = ts.dropna()
    dup = ts.notna() & ts.duplicated(keep=False)
    extra = int(valid.duplicated().sum())
    if dup.any():
        add("ERROR", "duplicates", "Duplicate timestamps; records preserved.", dup)
    if ts.isna().any():
        add("ERROR", "invalid_timestamp", "Unusable timestamps; inspect raw_timestamp and timezone issues.", ts.isna())
    if not aware:
        add("ERROR", "timezone_unresolved", "Internal timestamps are not timezone-aware.")
    if metadata.get("input_ordered") is False:
        add("WARNING", "input_unsorted", "Input was not chronological; returned data are stably sorted.")

    ordered = valid.sort_values().drop_duplicates()
    diffs = ordered.diff().dropna()
    diffs = diffs[diffs > pd.Timedelta(0)]
    detected = None
    if len(diffs):
        modes = diffs.mode()
        if len(modes) == 1:
            detected = str(modes.iloc[0])
        else:
            add("WARNING", "timeframe_ambiguous", "No unique modal interval; configure --timeframe.")
    else:
        add("WARNING", "timeframe_ambiguous", "Too few distinct timestamps to infer timeframe.")
    assumed = pd.Timedelta(expected_timeframe) if expected_timeframe else None
    if assumed is not None and assumed <= pd.Timedelta(0):
        raise ValueError("Timeframe must be positive, e.g. 15min or 1h.")
    missing_slots = None
    if assumed is not None:
        missing_slots = sum(max(0, int(delta // assumed) - 1) for delta in diffs)
        if any(delta > assumed for delta in diffs):
            add("WARNING", "gaps", "Unobserved slots may be closures or missing data; no prices inserted.")
        if any(delta % assumed != pd.Timedelta(0) or delta < assumed for delta in diffs):
            add("WARNING", "irregular_intervals", "Intervals conflict with configured timeframe.")
    else:
        add("WARNING", "timeframe_unconfigured", "Missing interval count requires a configured timeframe.")
    gaps = []
    for idx, delta in diffs.nlargest(5).items():
        end = ordered.loc[idx]
        gaps.append({"end": end.isoformat(), "duration": str(delta)})
    if len(diffs) and diffs.max() >= pd.Timedelta("12h"):
        add("WARNING", "large_gap", "Gap >=12h: check broker schedule, weekends and missing history.")
    def stamp(value):
        return None if pd.isna(value) else value.isoformat()
    summary = dict(input_filename=str(filename), rows_loaded=len(frame),
                   earliest_timestamp=stamp(valid.min()), latest_timestamp=stamp(valid.max()),
                   detected_timeframe=detected, assumed_timeframe=str(assumed) if assumed is not None else None,
                   duplicate_timestamp_count=extra, missing_value_counts=counts,
                   invalid_ohlc_count=int(invalid.sum()), missing_interval_count=missing_slots,
                   largest_time_gaps=gaps, timezone_aware=aware,
                   required_columns_present=not missing, **metadata)
    return QualityReport(summary, issues)
