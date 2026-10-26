"""Yahoo futures snapshots via yfinance; no fabricated data or automatic repair."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import sys
import pandas as pd
from .acquisition import AcquisitionError, utc_now, run_name, write_csv, write_json, sha256
from .validation import validate_candles

INTERVALS = {"1m": "1min", "2m": "2min", "5m": "5min", "15m": "15min",
             "30m": "30min", "60m": "1h", "90m": "90min", "1h": "1h",
             "1d": "1d", "5d": "5d", "1wk": "7d", "1mo": None, "3mo": None}


def normalize_yahoo(raw, symbol, interval, source_timezone=None, now=None):
    if interval not in INTERVALS:
        raise AcquisitionError(f"Unsupported interval {interval}; choose {list(INTERVALS)}")
    if raw is None or raw.empty:
        raise AcquisitionError("Yahoo returned no candles: unavailable range, rate limit, symbol or connection error. No prices saved.")
    data = raw.copy()
    if isinstance(data.columns, pd.MultiIndex):
        levels = [i for i in range(data.columns.nlevels) if symbol in data.columns.get_level_values(i)]
        if len(levels) != 1:
            raise AcquisitionError("Cannot identify the requested symbol in Yahoo MultiIndex columns.")
        data = data.xs(symbol, axis=1, level=levels[0], drop_level=True)
    if isinstance(data.columns, pd.MultiIndex) or data.columns.duplicated().any():
        raise AcquisitionError("Unsupported or duplicate Yahoo column schema.")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise AcquisitionError("Yahoo response has no DatetimeIndex.")
    timestamps = data.index
    original_timezone = str(timestamps.tz) if timestamps.tz else None
    if timestamps.tz is None:
        if not source_timezone:
            raise AcquisitionError("Naive Yahoo timestamps require configured source_timezone; UTC is not assumed.")
        timestamps = timestamps.tz_localize(source_timezone, ambiguous="raise", nonexistent="raise")
    frame = data.reset_index(drop=True).rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "real_volume"})
    frame.insert(0, "timestamp", timestamps.tz_convert("UTC"))
    frame["source_row"] = range(2, len(frame) + 2)
    for col in ("open", "high", "low", "close", "real_volume"):
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    ordered = frame.timestamp.dropna().is_monotonic_increasing
    frame = frame.sort_values("timestamp", kind="stable", na_position="last").reset_index(drop=True)
    now = utc_now() if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise AcquisitionError("now must be timezone-aware.")
    duration = INTERVALS[interval]
    if duration:
        frame["bar_available_after"] = frame.timestamp + pd.Timedelta(duration)
    else:
        months = 1 if interval == "1mo" else 3
        frame["bar_available_after"] = frame.timestamp + pd.DateOffset(months=months)
    frame["bar_complete_at_fetch"] = frame.bar_available_after <= now
    issues = []
    if (~frame.bar_complete_at_fetch).any():
        issues.append(dict(severity="WARNING", code="unfinished_bars",
                           message="Potentially unfinished bars retained; exclude before signal use.",
                           rows=frame.loc[~frame.bar_complete_at_fetch, "source_row"].tolist()))
    metadata = dict(source="yahoo_finance_via_yfinance", symbol=symbol, instrument_type="futures_proxy",
                    volume_type="provider_reported_futures_volume_not_spot_CFD_volume",
                    source_timezone=original_timezone or source_timezone, internal_timezone="UTC",
                    input_ordered=bool(ordered), synthetic=False, timestamp_convention="bar_start",
                    availability_caveat="Bar end is a minimum availability bound, not measured vendor latency.")
    report = validate_candles(frame, filename=f"Yahoo:{symbol}", expected_timeframe=duration,
                              metadata=metadata, initial_issues=issues)
    return frame, report, metadata


def acquire_yahoo(*, symbol="GC=F", interval="1h", period="1mo", start=None, end=None,
                  source_timezone=None, root=".", download=None, provider_version=None):
    if interval not in INTERVALS:
        raise AcquisitionError(f"Unsupported Yahoo interval: {interval}")
    if (start is None) != (end is None):
        raise AcquisitionError("Supply both --start and --end, or neither.")
    if start and pd.Timestamp(start) >= pd.Timestamp(end):
        raise AcquisitionError("start must precede end; end is exclusive.")
    if download is None:
        import yfinance as yf
        download = yf.download
        provider_version = version("yfinance")
    request = dict(tickers=symbol, interval=interval, auto_adjust=False, back_adjust=False,
                   repair=False, keepna=True, ignore_tz=False, progress=False,
                   threads=False, timeout=30, multi_level_index=True)
    request.update(dict(start=start, end=end) if start else dict(period=period))
    is_mock = provider_version == "injected_test_provider" or (download is not None and provider_version is None)
    name = run_name("yahoo", symbol, interval)
    root = Path(root)
    attempt = dict(source="yahoo_finance", symbol=symbol, interval=interval,
                   request=request, requested_at=utc_now().isoformat(),
                   yfinance_version=provider_version or "injected_test_provider",
                   synthetic=is_mock, data_kind="mock" if is_mock else "provider_download", status="started")
    try:
        raw = download(**request)
        attempt["retrieved_at"] = utc_now().isoformat()
        if raw is None or raw.empty:
            raise AcquisitionError("Yahoo returned no data; requested history may be unavailable or rate-limited.")
        raw_path = root / "data/raw" / f"{name}_response.csv"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("x", encoding="utf-8", newline="") as stream:
            raw.to_csv(stream)  # preserve provider columns, order, index, NaNs
        attempt["response_file"] = str(raw_path)
        attempt["response_sha256"] = sha256(raw_path)
        frame, report, metadata = normalize_yahoo(raw, symbol, interval, source_timezone)
        metadata["synthetic"] = is_mock
        report.summary["synthetic"] = is_mock
        normalized = root / "data/raw" / f"{name}_normalized.csv"
        write_csv(normalized, frame)
        report_path = root / "results/reports" / f"{name}_quality.json"
        write_json(report_path, report.to_dict())
        attempt.update(metadata)
        attempt["synthetic"] = is_mock
        attempt.update(status=report.status, rows=len(frame), normalized_file=str(normalized),
                       first_timestamp=str(frame.timestamp.min()), last_timestamp=str(frame.timestamp.max()),
                       quality_report=str(report_path),
                       coverage_note="Observed endpoints recorded; complete requested coverage is not guaranteed. Closures are not missing-data proof.")
        if start:
            attempt["requested_start"] = start
            attempt["requested_end_exclusive"] = end
        if report.status != "FAIL":
            processed = root / "data/processed" / f"{name}.csv"
            write_csv(processed, frame)
            attempt["processed_file"] = str(processed)
        return frame, report, attempt
    except Exception as exc:
        attempt.update(status="ERROR", error=str(exc))
        raise AcquisitionError(f"Yahoo acquisition failed: {exc}. No fallback prices used; retry later for rate limits.") from exc
    finally:
        write_json(root / "data/raw" / f"{name}_metadata.json", attempt)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="config.json")
    p.add_argument("--symbol")
    p.add_argument("--interval", choices=list(INTERVALS))
    p.add_argument("--period")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--source-timezone")
    args = p.parse_args(argv)
    try:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))["acquisition"]["yahoo"]
        frame, report, metadata = acquire_yahoo(symbol=args.symbol or cfg["symbol"],
            interval=args.interval or cfg["interval"], period=args.period or cfg["period"],
            start=args.start, end=args.end, source_timezone=args.source_timezone or cfg.get("source_timezone"))
        print(report)
        print(json.dumps(metadata, indent=2))
        return 2 if report.status == "FAIL" else 0
    except (AcquisitionError, OSError, ValueError, KeyError, ImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
