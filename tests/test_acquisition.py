"""All provider responses here are MOCKED. No automated test uses the network."""
from io import BytesIO
import json
from zipfile import ZipFile
import pandas as pd
import pytest
from src.acquisition import AcquisitionError
from src.yahoo_data import acquire_yahoo, normalize_yahoo
from src.cot import CATEGORIES, normalize_cot, parse_archive, acquire_cot, align_cot


def yahoo_frame():
    return pd.DataFrame({"Open": [2000., 2001., 2002.], "High": [2002., 2003., 2004.],
                         "Low": [1999., 2000., 2001.], "Close": [2001., 2002., 2003.],
                         "Volume": [100., float("nan"), 120.]},
                        index=pd.date_range("2024-01-02", periods=3, freq="15min", tz="America/New_York"))


def cot_frame(dates=("2024-01-02", "2024-01-09", "2024-01-16")):
    data = {"CFTC_Contract_Market_Code": ["088691"] * len(dates),
            "Market_and_Exchange_Names": ["GOLD - COMMODITY EXCHANGE INC."] * len(dates),
            "As_of_Date_Form_YYYY-MM-DD": list(dates)}
    for long_col, short_col in CATEGORIES.values():
        data[long_col] = [str(100 + 10*i) for i in range(len(dates))]
        data[short_col] = ["20"] * len(dates)
    return pd.DataFrame(data)


def archive(frame):
    payload = BytesIO()
    with ZipFile(payload, "w") as z:
        z.writestr("f_year.txt", frame.to_csv(index=False))
    return payload.getvalue()


def calendar():
    return pd.DataFrame({"as_of_date": ["2024-01-02", "2024-01-09", "2024-01-16"],
        "available_at": ["2024-01-05T20:30:00Z", "2024-01-12T20:30:00Z", "2024-01-22T20:30:00Z"],
        "evidence_url": ["https://example.invalid/MOCK-release-evidence"] * 3})


def test_yahoo_normalization():
    data, report, meta = normalize_yahoo(yahoo_frame(), "GC=F", "15m")
    assert data.timestamp.iloc[0] == pd.Timestamp("2024-01-02T05:00:00Z")
    assert len(data) == 3
    assert pd.isna(data.real_volume.iloc[1])  # never set missing volume to zero
    assert "tick_volume" not in data
    assert report.status == "WARNING"
    assert "not_spot_CFD" in meta["volume_type"]


@pytest.mark.parametrize("order", ["field_first", "ticker_first"])
def test_yahoo_multiindex(order):
    frame = yahoo_frame()
    if order == "field_first":
        frame.columns = pd.MultiIndex.from_tuples([(c, "GC=F") for c in frame.columns])
    else:
        frame.columns = pd.MultiIndex.from_tuples([("GC=F", c) for c in frame.columns])
    normalized, _, _ = normalize_yahoo(frame, "GC=F", "15m")
    assert len(normalized) == 3


def test_yahoo_bad_rows_preserved():
    frame = yahoo_frame()
    frame.iloc[0, frame.columns.get_loc("High")] = 1000
    frame = pd.concat([frame, frame.iloc[:1]])
    normalized, report, _ = normalize_yahoo(frame, "GC=F", "15m")
    assert len(normalized) == 4
    assert report.status == "FAIL"
    assert report.summary["duplicate_timestamp_count"] == 1
    assert report.summary["invalid_ohlc_count"] == 2


def test_yahoo_naive():
    frame = yahoo_frame()
    frame.index = frame.index.tz_localize(None)
    with pytest.raises(AcquisitionError, match="Naive"):
        normalize_yahoo(frame, "GC=F", "15m")
    assert len(normalize_yahoo(frame, "GC=F", "15m", source_timezone="America/New_York")[0]) == 3


def test_yahoo_incomplete():
    frame = yahoo_frame()
    data, report, _ = normalize_yahoo(frame, "GC=F", "15m", now="2024-01-02T05:20:00Z")
    assert data.bar_complete_at_fetch.tolist() == [True, False, False]
    assert "unfinished_bars" in {i["code"] for i in report.issues}


def test_yahoo_save_and_request(tmp_path):
    captured = {}
    def download(**kwargs):
        captured.update(kwargs)
        return yahoo_frame()
    data, report, meta = acquire_yahoo(root=tmp_path, interval="15m", download=download)
    assert captured["keepna"] and not captured["repair"] and not captured["auto_adjust"]
    assert meta["synthetic"]  # injected data cannot be labelled a real download
    assert report.summary["synthetic"]
    assert meta["rows"] == 3
    assert (tmp_path / "data/raw").exists()
    loaded = json.loads(next((tmp_path / "data/raw").glob("*metadata.json")).read_text())
    assert len(loaded["response_sha256"]) == 64
    assert pd.read_csv(meta["processed_file"]).real_volume.isna().sum() == 1


@pytest.mark.parametrize("mode", ["empty", "exception"])
def test_yahoo_network_errors(tmp_path, mode):
    def download(**kwargs):
        if mode == "exception":
            raise RuntimeError("HTTP 429 rate limit MOCK")
        return pd.DataFrame()
    with pytest.raises(AcquisitionError):
        acquire_yahoo(root=tmp_path, download=download)
    meta = json.loads(next((tmp_path / "data/raw").glob("*metadata.json")).read_text())
    assert meta["status"] == "ERROR"
    assert not list((tmp_path / "data/raw").glob("*normalized.csv"))


def test_yahoo_failure_not_processed(tmp_path):
    frame = yahoo_frame()
    frame.iloc[0, 0] = -1
    _, report, meta = acquire_yahoo(root=tmp_path, download=lambda **kw: frame)
    assert report.status == "FAIL"
    assert "processed_file" not in meta
    assert "normalized_file" in meta


def test_yahoo_date_range(tmp_path):
    calls = []
    acquire_yahoo(root=tmp_path, start="2024-01-01", end="2024-01-03",
                  download=lambda **kw: calls.append(kw) or yahoo_frame())
    assert calls[0]["end"] == "2024-01-03" and "period" not in calls[0]
    with pytest.raises(AcquisitionError):
        acquire_yahoo(start="2024-01-01", root=tmp_path, download=lambda **kw: yahoo_frame())


def test_cot_parse_and_features():
    raw = parse_archive(archive(cot_frame()))
    result = normalize_cot(raw, retrieved_at="2024-02-01T00:00:00Z", min_history=2)
    mm = result[result.category.eq("managed_money")].reset_index(drop=True)
    assert mm.net_positions.tolist() == [80, 90, 100]
    assert pd.isna(mm.net_change.iloc[0]) and mm.net_change.iloc[1] == 10
    assert mm.historical_percentile.isna().sum() == 2
    assert mm.historical_percentile.iloc[2] == 1
    assert mm.available_at.eq(pd.Timestamp("2024-02-01T00:00:00Z")).all()


def test_cot_release_alignment_and_delayed_holiday():
    positions = normalize_cot(cot_frame(), retrieved_at="2024-02-01T00:00:00Z", releases=calendar(), min_history=2)
    decisions = pd.DataFrame({"timestamp": [
        "2024-01-05T20:29:59Z", "2024-01-05T20:30:00Z", "2024-01-05T20:30:01Z",
        "2024-01-19T21:00:00Z", "2024-01-22T20:30:01Z"]})
    aligned = align_cot(decisions, positions)
    assert pd.isna(aligned.net_positions.iloc[0]) and pd.isna(aligned.net_positions.iloc[1])
    assert aligned.net_positions.iloc[2] == 80
    assert aligned.net_positions.iloc[3] == 90  # no assumed Friday release of Jan 16 report
    assert aligned.net_positions.iloc[4] == 100


def test_retrieval_only_cannot_leak_backwards():
    positions = normalize_cot(cot_frame(), retrieved_at="2024-02-01T00:00:00Z", min_history=2)
    d = pd.DataFrame({"timestamp": ["2024-01-30T00:00:00Z", "2024-02-01T00:00:01Z", "2024-03-01T00:00:00Z"]})
    aligned = align_cot(d, positions)
    assert pd.isna(aligned.net_positions.iloc[0])
    assert aligned.net_positions.iloc[1] == 100
    assert pd.isna(aligned.net_positions.iloc[2])  # stale >14d


def test_future_cot_perturbation():
    raw = cot_frame()
    original = normalize_cot(raw, retrieved_at="2024-02-01T00:00:00Z", releases=calendar(), min_history=2)
    raw.loc[2, "M_Money_Positions_Long_All"] = "99999"
    changed = normalize_cot(raw, retrieved_at="2024-02-01T00:00:00Z", releases=calendar(), min_history=2)
    pd.testing.assert_frame_equal(original[original.as_of_date < "2024-01-16"].reset_index(drop=True),
                                  changed[changed.as_of_date < "2024-01-16"].reset_index(drop=True))


@pytest.mark.parametrize("problem", ["missing", "duplicate", "negative", "bad_date", "wrong_market"])
def test_cot_invalid(problem):
    raw = cot_frame()
    if problem == "missing":
        raw = raw.drop(columns="M_Money_Positions_Long_All")
    elif problem == "duplicate":
        raw.loc[1, "As_of_Date_Form_YYYY-MM-DD"] = "2024-01-02"
    elif problem == "negative":
        raw.loc[1, "M_Money_Positions_Long_All"] = "-1"
    elif problem == "bad_date":
        raw.loc[1, "As_of_Date_Form_YYYY-MM-DD"] = "wrong"
    else:
        raw.CFTC_Contract_Market_Code = "999999"
    with pytest.raises(AcquisitionError):
        normalize_cot(raw, retrieved_at="2024-02-01T00:00:00Z")


def test_cot_naive_calendar_refused():
    releases = calendar()
    releases.available_at = ["2024-01-05 15:30:00"] * 3
    with pytest.raises(AcquisitionError, match="timezone-aware"):
        normalize_cot(cot_frame(), retrieved_at="2024-02-01T00:00:00Z", releases=releases)


def test_cot_dst_release_offsets():
    raw = cot_frame(("2024-03-05", "2024-03-12"))
    releases = pd.DataFrame({"as_of_date": ["2024-03-05", "2024-03-12"],
        "available_at": ["2024-03-08T15:30:00-05:00", "2024-03-15T15:30:00-04:00"],
        "evidence_url": ["https://example.invalid/MOCK"] * 2})
    result = normalize_cot(raw, retrieved_at="2024-04-01T00:00:00Z", releases=releases)
    mm = result[result.category.eq("managed_money")]
    assert mm.available_at.dt.hour.tolist() == [20, 19]


def test_cot_download_artifacts(tmp_path):
    data, meta = acquire_cot(2024, root=tmp_path, fetch=lambda url: archive(cot_frame()), min_history=2)
    assert meta["synthetic"]
    assert meta["report_dates"] == 3 and len(data) == 15
    assert len(meta["raw_archives"][0]["sha256"]) == 64
    assert pd.read_csv(meta["processed_file"]).shape[0] == 15


def test_cot_multiple_years(tmp_path):
    def fetch(url):
        dates = ("2023-12-26",) if "2023" in url else ("2024-01-02", "2024-01-09")
        return archive(cot_frame(dates))
    data, meta = acquire_cot([2023, 2024], root=tmp_path, fetch=fetch, min_history=2)
    assert meta["report_dates"] == 3
    assert data[data.category.eq("managed_money")].historical_percentile.notna().sum() == 1


def test_cot_bad_network_and_archive(tmp_path):
    with pytest.raises(AcquisitionError):
        acquire_cot(2024, root=tmp_path, fetch=lambda url: b"MOCK 403 not a ZIP")
    meta = json.loads(next((tmp_path / "data/raw").glob("*metadata.json")).read_text())
    assert meta["status"] == "ERROR"
    with pytest.raises(AcquisitionError):
        parse_archive(b"MOCK not zip")


def test_cot_nonmonotonic_publication_refused():
    releases = calendar()
    releases.loc[0, "available_at"] = "2024-01-24T20:30:00Z"
    with pytest.raises(AcquisitionError, match="Publication order"):
        normalize_cot(cot_frame(), retrieved_at="2024-02-01T00:00:00Z", releases=releases)

def test_cot_current_archive_date_header():
    raw = cot_frame().rename(columns={"As_of_Date_Form_YYYY-MM-DD": "Report_Date_as_YYYY-MM-DD"})
    normalized = normalize_cot(raw, retrieved_at="2024-02-01T00:00:00Z")
    assert len(normalized) == 15


def test_availability_uses_response_completion_not_request_start(tmp_path):
    finished = []
    def download(**kwargs):
        finished.append(pd.Timestamp.now(tz="UTC"))
        return yahoo_frame()
    _, _, meta = acquire_yahoo(root=tmp_path, download=download)
    assert pd.Timestamp(meta["retrieved_at"]) >= finished[0]
    assert pd.Timestamp(meta["retrieved_at"]) >= pd.Timestamp(meta["requested_at"])


def test_cot_retrieval_time_is_after_final_response(tmp_path):
    finished = []
    def fetch(url):
        data = archive(cot_frame())
        finished.append(pd.Timestamp.now(tz="UTC"))
        return data
    data, meta = acquire_cot(2024, root=tmp_path, fetch=fetch)
    assert pd.Timestamp(meta["retrieved_at"]) >= finished[0]
    assert data.available_at.min() == pd.Timestamp(meta["retrieved_at"])


def test_reuse_saved_archives_without_network(tmp_path):
    saved = tmp_path / "downloaded_2024.zip"
    saved.write_bytes(archive(cot_frame()))
    def no_network(url):
        raise AssertionError("Network must not be used")
    data, meta = acquire_cot(2024, root=tmp_path, fetch=no_network, local_archives={2024: saved})
    assert len(data) == 15
    assert meta["input_mode"] == "local_archives_unverified_provenance"
    assert meta["synthetic"]  # injected test provenance remains explicit

