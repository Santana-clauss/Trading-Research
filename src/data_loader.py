"""Strict CSV parsing, explicit timezones and a non-destructive validation CLI."""
import argparse
import csv
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from .validation import validate_candles

ALIASES = {
    "timestamp": "timestamp", "datetime": "timestamp", "dateandtime": "timestamp",
    "date": "date", "time": "time", "open": "open", "high": "high",
    "low": "low", "close": "close", "tickvolume": "tick_volume",
    "tickvol": "tick_volume", "volume": "tick_volume",
    "realvolume": "real_volume", "realvol": "real_volume", "vol": "real_volume",
    "spread": "spread",
}


class DataLoadError(ValueError):
    """A file cannot be parsed without guessing or losing records."""


@dataclass
class LoadResult:
    candles: pd.DataFrame
    raw: pd.DataFrame
    report: object


def normalize(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_csv(path, *, source_timezone=None, datetime_format=None, delimiter=None,
             decimal=".", column_mapping=None, expected_timeframe=None, encoding=None):
    path = Path(path)
    try:
        payload = path.read_bytes()
        enc = encoding or ("utf-16" if payload.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
        text = payload.decode(enc)
        if not text.strip():
            raise DataLoadError("Empty CSV file.")
        sep = delimiter or csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
        if len(sep) != 1 or decimal not in (".", ",") or sep == decimal:
            raise DataLoadError("Delimiter must differ from decimal separator; decimal must be '.' or ','.")
        records = list(csv.reader(io.StringIO(text), delimiter=sep, strict=True))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DataLoadError(f"Cannot read CSV {path}: {exc}. Set delimiter/encoding explicitly if needed.") from exc
    if not records or not records[0]:
        raise DataLoadError("CSV header is missing.")
    header = records[0]
    for rownum, row in enumerate(records[1:], 2):
        if len(row) != len(header):
            raise DataLoadError(f"Malformed CSV record {rownum}: expected {len(header)} fields, got {len(row)}. No records dropped.")
    mapping = column_mapping or {}
    names = [mapping.get(h, ALIASES.get(normalize(h), h)) for h in header]
    # MT5 <TICKVOL> + <VOL>, or 'Tick Volume' + 'Volume': latter Volume is real.
    if "tick_volume" in names:
        explicit_tick = any(normalize(h) in ("tickvol", "tickvolume") for h in header)
        if explicit_tick:
            names = ["real_volume" if normalize(h) == "volume" and h not in mapping else n
                     for h, n in zip(header, names)]
    if len(set(names)) != len(names):
        raise DataLoadError("Column names collide after normalization; supply column_mapping (source header -> canonical name).")
    raw = pd.DataFrame(records[1:], columns=header)
    frame = pd.DataFrame(records[1:], columns=names)
    frame["source_row"] = range(2, len(frame) + 2)
    issues = []
    for col in ("open", "high", "low", "close", "tick_volume", "real_volume", "spread"):
        if col in frame:
            values = frame[col].str.strip().replace("", np.nan)
            if decimal == ",":
                values = values.str.replace(",", ".", regex=False)
            frame[col] = pd.to_numeric(values, errors="coerce")
    if "timestamp" in frame:
        texts = frame["timestamp"].copy()
    elif "date" in frame:
        texts = frame["date"].str.strip()
        if "time" in frame:
            texts = texts + " " + frame["time"].str.strip()
    else:
        texts = pd.Series([""] * len(frame), index=frame.index)
        issues.append(dict(severity="ERROR", code="missing_timestamp_column",
                           message="Need timestamp or Date (optionally Time).", rows=[]))
    frame["raw_timestamp"] = texts
    parsed = []
    zone = None
    if source_timezone:
        try:
            zone = ZoneInfo(source_timezone)
        except (ValueError, KeyError) as exc:
            raise DataLoadError(f"Unknown source timezone: {source_timezone}") from exc
    unknown_rows, failed_rows, dst_rows = [], [], []
    for i, value in texts.items():
        rownum = int(frame.loc[i, "source_row"])
        try:
            value = value.strip()
            if not value:
                raise ValueError("missing timestamp")
            if not datetime_format and not re.match(r"^\d{4}[-.]\d{2}[-.]\d{2}(?:[ T]|$)", value):
                raise ValueError("ambiguous format; configure datetime_format")
            ts = pd.to_datetime(value, format=datetime_format, errors="raise") if datetime_format else pd.Timestamp(value)
            if pd.isna(ts):
                raise ValueError("missing timestamp")
            if ts.tzinfo is None:
                if zone is None:
                    unknown_rows.append(rownum)
                    parsed.append(pd.NaT)
                    continue
                try:
                    ts = ts.tz_localize(zone, ambiguous="raise", nonexistent="raise")
                except Exception:
                    dst_rows.append(rownum)
                    parsed.append(pd.NaT)
                    continue
            parsed.append(ts.tz_convert("UTC"))
        except (ValueError, TypeError, OverflowError):
            failed_rows.append(rownum)
            parsed.append(pd.NaT)
    for code, rows, message in (
        ("source_timezone_unknown", unknown_rows, "Naive timestamps need source_timezone; UTC was not assumed."),
        ("timestamp_parse", failed_rows, "Missing or invalid date/time; ambiguous formats require datetime_format."),
        ("dst_ambiguous_or_nonexistent", dst_rows, "DST wall time is ambiguous or nonexistent; supply explicit UTC offsets or resolve with broker.")):
        if rows:
            issues.append(dict(severity="ERROR", code=code, message=message, rows=rows))
    frame["timestamp"] = pd.Series(pd.to_datetime(parsed, utc=True), index=frame.index)
    input_ordered = frame["timestamp"].dropna().is_monotonic_increasing
    frame = frame.sort_values("timestamp", kind="stable", na_position="last").reset_index(drop=True)
    metadata = dict(source_timezone=source_timezone, internal_timezone="UTC",
                    input_ordered=bool(input_ordered), delimiter=sep, decimal=decimal, encoding=enc,
                    synthetic="synthetic" in path.name.lower())
    report = validate_candles(frame, filename=path, expected_timeframe=expected_timeframe,
                              metadata=metadata, initial_issues=issues)
    return LoadResult(frame, raw, report)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate MT5 candles without changing the input.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--source-timezone")
    parser.add_argument("--datetime-format")
    parser.add_argument("--delimiter", help="Single character; use 'tab' for tab-separated files.")
    parser.add_argument("--decimal", choices=[".", ","])
    parser.add_argument("--timeframe", help="Expected interval, e.g. 15min or 1h.")
    parser.add_argument("--encoding")
    parser.add_argument("--report", help="Write JSON report to an existing directory; refuses overwrite.")
    args = parser.parse_args(argv)
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))["data"]
        result = load_csv(args.input,
            source_timezone=args.source_timezone or config.get("source_timezone"),
            datetime_format=args.datetime_format or config.get("datetime_format"),
            delimiter=("\t" if args.delimiter == "tab" else args.delimiter) or config.get("delimiter"),
            decimal=args.decimal or config.get("decimal", "."),
            column_mapping=config.get("column_mapping"),
            expected_timeframe=args.timeframe or config.get("entry_timeframe"), encoding=args.encoding)
        print(result.report)
        if args.report:
            target = Path(args.report)
            if target.resolve() == Path(args.input).resolve():
                raise DataLoadError("Report path must differ from input CSV.")
            with target.open("x", encoding="utf-8") as stream:
                stream.write(result.report.to_json() + "\n")
        return 2 if result.report.status == "FAIL" else 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
