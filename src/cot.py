"""CFTC disaggregated futures-only snapshots; release timing must be explicit."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zipfile import ZipFile, BadZipFile
import numpy as np
import pandas as pd
from .acquisition import AcquisitionError, utc_now, run_name, write_json, write_csv, sha256

CATEGORIES = {"producer_merchant": ("Prod_Merc_Positions_Long_All", "Prod_Merc_Positions_Short_All"),
              "swap_dealer": ("Swap_Positions_Long_All", "Swap__Positions_Short_All"),
              "managed_money": ("M_Money_Positions_Long_All", "M_Money_Positions_Short_All"),
              "other_reportable": ("Other_Rept_Positions_Long_All", "Other_Rept_Positions_Short_All"),
              "nonreportable": ("NonRept_Positions_Long_All", "NonRept_Positions_Short_All")}


def fetch_bytes(url):
    try:
        with urlopen(Request(url, headers={"User-Agent": "GoldResearch/1.0 (personal research)"}), timeout=45) as response:
            if int(response.headers.get("Content-Length", "0")) > 50_000_000:
                raise AcquisitionError("CFTC archive exceeds 50MB safety limit.")
            payload = response.read(50_000_001)
            if len(payload) > 50_000_000:
                raise AcquisitionError("CFTC response exceeds 50MB.")
            return payload
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AcquisitionError(f"CFTC download unavailable or rate-limited: {exc}. Retry later; no bypass attempted.") from exc


def parse_archive(payload):
    try:
        with ZipFile(BytesIO(payload)) as archive:
            candidates = [info for info in archive.infolist() if info.filename.lower().endswith((".txt", ".csv"))]
            if len(candidates) != 1 or candidates[0].file_size > 200_000_000:
                raise AcquisitionError("Expected one CFTC text file smaller than 200MB.")
            with archive.open(candidates[0]) as stream:
                frame = pd.read_csv(stream, dtype=str, encoding="utf-8-sig", on_bad_lines="error")
        frame.columns = frame.columns.str.strip()
        return frame
    except (BadZipFile, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise AcquisitionError(f"Malformed CFTC archive: {exc}") from exc


def utc_series(values, name):
    # Never silently interpret naive release or decision timestamps as UTC.
    parsed = [pd.Timestamp(v) for v in values]
    if any(pd.isna(v) or v.tzinfo is None for v in parsed):
        raise AcquisitionError(f"{name} requires non-missing timezone-aware timestamps with explicit offsets.")
    return pd.DatetimeIndex([v.tz_convert("UTC") for v in parsed]).as_unit("ns")


def normalize_cot(raw, *, retrieved_at, market_code="088691", releases=None,
                  percentile_window=156, min_history=52):
    """Calendar is optional. Without verified release evidence, data become usable at retrieval only."""
    if not 1 <= min_history <= percentile_window:
        raise AcquisitionError("Require 1 <= min_history <= percentile_window.")
    raw = raw.copy()
    if "As_of_Date_Form_YYYY-MM-DD" not in raw and "Report_Date_as_YYYY-MM-DD" in raw:
        raw = raw.rename(columns={"Report_Date_as_YYYY-MM-DD": "As_of_Date_Form_YYYY-MM-DD"})
    required = {"CFTC_Contract_Market_Code", "As_of_Date_Form_YYYY-MM-DD", "Market_and_Exchange_Names"}
    required |= {col for pair in CATEGORIES.values() for col in pair}
    missing = required - set(raw.columns)
    if missing:
        raise AcquisitionError(f"CFTC columns missing: {sorted(missing)}")
    codes = raw.CFTC_Contract_Market_Code.astype(str).str.strip().str.zfill(6)
    gold = raw.loc[codes.eq(str(market_code).zfill(6))].copy()
    if gold.empty:
        raise AcquisitionError(f"No CFTC rows for market code {market_code}.")
    gold["source_row"] = np.flatnonzero(codes.eq(str(market_code).zfill(6))) + 2
    gold["as_of_date"] = pd.to_datetime(gold["As_of_Date_Form_YYYY-MM-DD"], format="%Y-%m-%d", errors="coerce")
    if gold.as_of_date.isna().any() or gold.as_of_date.duplicated().any():
        raise AcquisitionError("Missing/invalid/duplicate COT report dates. Raw snapshot retained; no records discarded.")
    gold = gold.sort_values("as_of_date", kind="stable").reset_index(drop=True)
    fetched = utc_series([retrieved_at], "retrieved_at")[0]
    available = pd.Series([fetched] * len(gold), dtype="datetime64[ns, UTC]")
    basis = pd.Series(["retrieval_time_only"] * len(gold))
    if releases is not None:
        needed = {"as_of_date", "available_at", "evidence_url"}
        if not needed <= set(releases.columns):
            raise AcquisitionError("Release calendar needs as_of_date, available_at, evidence_url.")
        calendar = releases.copy()
        calendar["as_of_date"] = pd.to_datetime(calendar.as_of_date, format="%Y-%m-%d", errors="raise")
        calendar["available_at"] = utc_series(calendar.available_at, "available_at")
        if calendar.as_of_date.duplicated().any() or calendar.evidence_url.fillna("").str.strip().eq("").any():
            raise AcquisitionError("Calendar dates must be unique and publication evidence URLs nonempty.")
        # Historical finalized archives can contain revisions; release timing alone does not remove revision bias.
        lookup = calendar.set_index("as_of_date")
        for i, date in gold.as_of_date.items():
            if date in lookup.index:
                candidate = lookup.loc[date, "available_at"]
                if candidate <= date.tz_localize("UTC") or candidate > fetched:
                    raise AcquisitionError("Invalid publication timestamp (before observation or after retrieval).")
                available.iloc[i] = candidate
                basis.iloc[i] = "user_verified_release_calendar_revision_risk"
    if not available.is_monotonic_increasing:
        raise AcquisitionError("Publication order is not chronological; resolve missing/delayed releases before calculating causal changes.")
    result = []
    for category, (long_col, short_col) in CATEGORIES.items():
        longs = pd.to_numeric(gold[long_col].str.replace(",", "", regex=False), errors="coerce")
        shorts = pd.to_numeric(gold[short_col].str.replace(",", "", regex=False), errors="coerce")
        bad = ~np.isfinite(longs) | ~np.isfinite(shorts) | (longs < 0) | (shorts < 0)
        if bad.any():
            raise AcquisitionError(f"Invalid {category} positions at source rows {gold.loc[bad, 'source_row'].tolist()}; raw retained.")
        net = longs - shorts
        # Rank current net against strictly PRIOR reports only; no full-sample ranks.
        percentile = []
        for i, value in enumerate(net):
            history = net.iloc[max(0, i - percentile_window):i]
            percentile.append(float((history < value).mean()) if len(history) >= min_history else np.nan)
        result.append(pd.DataFrame(dict(as_of_date=gold.as_of_date, available_at=available,
            availability_basis=basis, market_code=str(market_code).zfill(6),
            market_name=gold.Market_and_Exchange_Names, category=category,
            long_positions=longs, short_positions=shorts, net_positions=net,
            net_change=net.diff(), historical_percentile=percentile,
            source_row=gold.source_row)))
    return pd.concat(result, ignore_index=True)


def align_cot(decisions, positions, category="managed_money", max_age="14D"):
    """Backward as-of join uses decision time, never the Tuesday observation date."""
    left = decisions.copy()
    left["timestamp"] = utc_series(left.timestamp, "decision timestamps")
    left["_original_order"] = range(len(left))
    right = positions.loc[positions.category.eq(category)].copy()
    right["available_at"] = utc_series(right.available_at, "COT availability")
    # Retrieval-only archives can have several reports becoming known simultaneously.
    # Most recent observation is selected; all original reports remain in the archive.
    right = right.sort_values(["available_at", "as_of_date"], kind="stable").drop_duplicates("available_at", keep="last")
    joined = pd.merge_asof(left.sort_values("timestamp"), right, left_on="timestamp", right_on="available_at",
                           direction="backward", allow_exact_matches=False, tolerance=pd.Timedelta(max_age))
    return joined.sort_values("_original_order").drop(columns="_original_order").reset_index(drop=True)


def acquire_cot(year, *, root=".", market_code="088691", releases=None, fetch=fetch_bytes,
                percentile_window=156, min_history=52, local_archives=None):
    years = sorted(set([year] if isinstance(year, int) else year))
    if not years or any(not 2010 <= int(y) <= utc_now().year for y in years):
        raise AcquisitionError("Choose annual formats from 2010 through current year.")
    urls = [f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{int(y)}.zip" for y in years]
    root = Path(root)
    name = run_name("cftc", market_code, f"{years[0]}-{years[-1]}")
    metadata = dict(source="CFTC", report_type="disaggregated_futures_only", urls=urls,
                    years=years, market_code=market_code, synthetic=fetch is not fetch_bytes, status="started",
                    requested_at=utc_now().isoformat(), percentile_window=percentile_window,
                    minimum_prior_reports=min_history,
                    caveats=["Weekly aggregated positions, not individual candle orders.",
                             "Finalized archives may contain revisions; not point-in-time vintages.",
                             "No historical release time inferred from Tuesday or assumed Friday."])
    metadata["input_mode"] = "local_archives_unverified_provenance" if local_archives else "official_url_download"
    try:
        tables = []
        metadata["raw_archives"] = []
        for archive_year, url in zip(years, urls):
            payload = Path(local_archives[int(archive_year)]).read_bytes() if local_archives else fetch(url)
            raw_path = root / "data/raw" / f"{name}_{archive_year}.zip"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            with raw_path.open("xb") as stream:
                stream.write(payload)
            metadata["raw_archives"].append(dict(year=archive_year, url=url, file=str(raw_path), sha256=sha256(raw_path)))
            table = parse_archive(payload)
            table["archive_year"] = str(archive_year)
            tables.append(table)
        raw = pd.concat(tables, ignore_index=True)
        metadata["retrieved_at"] = utc_now().isoformat()
        # Combined CSV provides stable source_row references across multiple archives.
        combined_path = root / "data/raw" / f"{name}_combined.csv"
        write_csv(combined_path, raw)
        metadata["combined_raw_file"] = str(combined_path)
        clean = normalize_cot(raw, retrieved_at=metadata["retrieved_at"], market_code=market_code,
                              releases=releases, percentile_window=percentile_window, min_history=min_history)
        path = root / "data/processed" / f"{name}.csv"
        write_csv(path, clean)
        metadata.update(status="WARNING", rows=len(clean), report_dates=int(clean.as_of_date.nunique()),
                        processed_file=str(path),
                        timing_policy="retrieval_time_only" if releases is None else "explicit_release_calendar_with_retrieval_fallback",
                        warmup_note="Percentiles remain missing until minimum prior reports are present; one annual file usually has insufficient history.")
        if releases is not None:
            calendar_path = root / "data/raw" / f"{name}_release_calendar.csv"
            write_csv(calendar_path, releases)
            metadata["release_calendar_file"] = str(calendar_path)
            metadata["release_calendar_sha256"] = sha256(calendar_path)
        return clean, metadata
    except Exception as exc:
        metadata.update(status="ERROR", error=str(exc))
        raise AcquisitionError(f"CFTC acquisition failed: {exc}") from exc
    finally:
        write_json(root / "data/raw" / f"{name}_metadata.json", metadata)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--year", type=int, nargs="+", required=True, help="One or more archive years.")
    p.add_argument("--config", default="config.json")
    p.add_argument("--release-calendar")
    p.add_argument("--local-archives", nargs="+", help="Reuse saved ZIP files ending in _YYYY.zip; no network.")
    args = p.parse_args(argv)
    try:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))["acquisition"]["cot"]
        releases = pd.read_csv(args.release_calendar, dtype=str) if args.release_calendar else None
        archives = None
        if args.local_archives:
            archives = {}
            for path in args.local_archives:
                match = re.search(r"_(\d{4})\.zip$", path)
                if not match or int(match.group(1)) in archives:
                    raise AcquisitionError("Local archive paths must uniquely end in _YYYY.zip.")
                archives[int(match.group(1))] = path
            if set(archives) != set(args.year):
                raise AcquisitionError("Supply one local archive for each requested year.")
        data, meta = acquire_cot(args.year, market_code=cfg["market_code"], releases=releases,
                                percentile_window=cfg["percentile_window"], min_history=cfg["min_history"],
                                local_archives=archives)
        print(json.dumps(meta, indent=2))
        return 0
    except (AcquisitionError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
