"""Offline fixtures; test files are temporary and source CSVs stay unchanged."""
import json
from pathlib import Path
import pandas as pd
import pytest
from src.data_loader import load_csv, DataLoadError, main

HEADER = "Timestamp,Open,High,Low,Close,Volume,Spread\n"
ROWS = ["2026-01-05 09:00:00,2000,2002,1999,2001,100,20",
        "2026-01-05 09:15:00,2001,2003,2000,2002,110,20",
        "2026-01-05 09:30:00,2002,2004,2001,2003,120,20"]


def load(tmp_path, rows=None, header=HEADER, **kwargs):
    path = tmp_path / "fixture.csv"
    selected = ROWS if rows is None else rows
    content = header + ("\n".join(selected) + "\n" if selected else "")
    path.write_text(content, encoding="utf-8")
    result = load_csv(path, source_timezone=kwargs.pop("source_timezone", "UTC"),
                      expected_timeframe=kwargs.pop("expected_timeframe", "15min"), **kwargs)
    assert path.read_text(encoding="utf-8") == content
    return result


def codes(result):
    return {x["code"] for x in result.report.issues}


def test_success_and_report(tmp_path):
    r = load(tmp_path)
    assert len(r.candles) == len(r.raw) == 3
    assert r.candles.tick_volume.tolist() == [100, 110, 120]
    assert r.report.summary["missing_interval_count"] == 0
    assert r.report.status == "WARNING"  # real volume is unavailable
    assert json.loads(r.report.to_json())["status"] == "WARNING"
    assert "Rows loaded: 3" in str(r.report)


def test_synthetic_mt5():
    r = load_csv("data/raw/synthetic_xauusd_m15.csv", source_timezone="UTC", expected_timeframe="15min")
    assert r.report.status == "PASS"
    assert r.report.summary["synthetic"]
    assert r.candles.real_volume.eq(0).all()


@pytest.mark.parametrize("header", [
    "Date Time;Open;High;Low;Close;Tick Volume;Real Volume;Spread\n",
    "<DATE>; <OPEN>; <HIGH>; <LOW>; <CLOSE>; <TICKVOL>; <VOL>; <SPREAD>\n"])
def test_names_decimal_and_delimiter(tmp_path, header):
    r = load(tmp_path, header=header, rows=["2026.01.05 09:00:00;2000,1;2002,1;1999,1;2001,1;100;0;20"], decimal=",")
    assert r.candles.open.iloc[0] == 2000.1
    assert r.candles.real_volume.iloc[0] == 0


def test_split_datetime_and_volume_disambiguation(tmp_path):
    r = load(tmp_path, header="Date,Time,Open,High,Low,Close,Tick Volume,Volume,Spread\n",
             rows=["2026.01.05,09:00:00,2000,2002,1999,2001,100,0,20"])
    assert r.candles.tick_volume.iloc[0] == 100
    assert r.candles.real_volume.iloc[0] == 0


def test_missing_columns(tmp_path):
    r = load(tmp_path, header=HEADER.replace("Open", "Wrong"))
    assert "missing_columns" in codes(r)
    assert r.report.status == "FAIL"


def test_duplicates_and_sorting(tmp_path):
    r = load(tmp_path, rows=[ROWS[1], ROWS[0], ROWS[0]])
    assert len(r.candles) == 3
    assert r.report.summary["duplicate_timestamp_count"] == 1
    assert {"duplicates", "input_unsorted"} <= codes(r)
    issue = next(i for i in r.report.issues if i["code"] == "duplicates")
    assert set(issue["rows"]) == {3, 4}


@pytest.mark.parametrize("row", [
    "2026-01-05 09:00:00,2000,1998,1999,2001,100,20",
    "2026-01-05 09:00:00,2000,2002,2003,2001,100,20",
    "2026-01-05 09:00:00,,2002,1999,2001,100,20",
    "2026-01-05 09:00:00,nope,2002,1999,2001,100,20",
    "2026-01-05 09:00:00,inf,2002,1999,2001,100,20",
    "2026-01-05 09:00:00,0,2002,1999,2001,100,20",
    "2026-01-05 09:00:00,-1,2002,1999,2001,100,20"])
def test_invalid_prices(tmp_path, row):
    r = load(tmp_path, rows=[row])
    assert r.report.status == "FAIL"
    assert r.report.summary["invalid_ohlc_count"] == 1


def test_timezone_conversion(tmp_path):
    r = load(tmp_path, source_timezone="Africa/Nairobi")
    assert r.candles.timestamp.iloc[0] == pd.Timestamp("2026-01-05 06:00:00Z")


def test_unknown_timezone(tmp_path):
    r = load(tmp_path, source_timezone=None)
    assert "source_timezone_unknown" in codes(r)
    assert r.candles.timestamp.isna().all()
    assert len(r.candles) == 3


@pytest.mark.parametrize("stamp", ["2026-11-01 01:30:00", "2026-03-08 02:30:00"])
def test_dst_fail_closed(tmp_path, stamp):
    r = load(tmp_path, rows=[ROWS[0].replace("2026-01-05 09:00:00", stamp)], source_timezone="America/New_York")
    assert "dst_ambiguous_or_nonexistent" in codes(r)


def test_aware_offsets_need_no_source_zone(tmp_path):
    r = load(tmp_path, rows=[ROWS[0].replace("2026-01-05 09:00:00", "2026-01-05T09:00:00+03:00")], source_timezone=None)
    assert r.candles.timestamp.iloc[0] == pd.Timestamp("2026-01-05T06:00:00Z")
    assert "source_timezone_unknown" not in codes(r)


def test_date_format(tmp_path):
    rows = [ROWS[0].replace("2026-01-05", "05/01/2026")]
    assert load(tmp_path, rows=rows).report.status == "FAIL"
    r = load(tmp_path, rows=rows, datetime_format="%d/%m/%Y %H:%M:%S")
    assert r.candles.timestamp.iloc[0].day == 5


def test_invalid_timestamp(tmp_path):
    r = load(tmp_path, rows=[ROWS[0].replace("2026-01-05 09:00:00", "")])
    assert "invalid_timestamp" in codes(r)


def test_gap_and_closure_are_warnings(tmp_path):
    r = load(tmp_path, rows=[ROWS[0], ROWS[2], ROWS[2].replace("2026-01-05", "2026-01-08")])
    assert {"gaps", "large_gap"} <= codes(r)
    assert r.report.status == "WARNING"
    assert r.report.summary["missing_interval_count"] > 0
    assert len(r.candles) == 3


def test_irregular_and_ambiguous(tmp_path):
    r = load(tmp_path, rows=[ROWS[0], ROWS[1], ROWS[2].replace("09:30", "09:32")])
    assert {"timeframe_ambiguous", "irregular_intervals"} <= codes(r)


@pytest.mark.parametrize("content", ["", "   ", "a,b\n1,2,3\n", 'a,b\n"unclosed,2\n', "a,b\n\n"])
def test_empty_or_malformed(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(DataLoadError):
        load_csv(path)


def test_header_only(tmp_path):
    r = load(tmp_path, rows=[])
    assert r.report.status == "FAIL"
    assert "no_rows" in codes(r)


def test_optional_bad_values(tmp_path):
    r = load(tmp_path, rows=[ROWS[0].replace(",100,20", ",-1,inf")])
    assert "optional_invalid" in codes(r)


def test_mapping_and_collision(tmp_path):
    r = load(tmp_path, header=HEADER.replace("Open", "BidOpen"), column_mapping={"BidOpen": "open"})
    assert "open" in r.candles
    with pytest.raises(DataLoadError):
        load(tmp_path, header=HEADER.replace("Open", "Close"))


def test_no_assumed_timeframe(tmp_path):
    r = load(tmp_path, expected_timeframe=None)
    assert r.report.summary["missing_interval_count"] is None


def test_cli(tmp_path, capsys):
    report = tmp_path / "report.json"
    args = ["--input", "data/raw/synthetic_xauusd_m15.csv", "--source-timezone", "UTC", "--report", str(report)]
    assert main(args) == 0
    assert json.loads(report.read_text())["status"] == "PASS"
    assert main(args) == 2  # never overwrite
    assert main(["--input", "data/raw/synthetic_xauusd_m15.csv"]) == 2
    assert "source_timezone_unknown" in capsys.readouterr().out


def test_utf16(tmp_path):
    path = tmp_path / "utf16.csv"
    path.write_text(HEADER + "\n".join(ROWS), encoding="utf-16")
    r = load_csv(path, source_timezone="UTC", expected_timeframe="15min")
    assert len(r.candles) == 3

def test_h1_interval(tmp_path):
    rows = [ROWS[0], ROWS[1].replace("09:15", "10:00"), ROWS[2].replace("09:30", "11:00")]
    r = load(tmp_path, rows=rows, expected_timeframe="1h")
    assert r.report.summary["missing_interval_count"] == 0
    assert r.report.summary["detected_timeframe"] == "0 days 01:00:00"


def test_dst_seasonal_offsets(tmp_path):
    rows = [ROWS[0], ROWS[1].replace("2026-01-05", "2026-07-05")]
    r = load(tmp_path, rows=rows, source_timezone="America/New_York")
    assert r.candles.timestamp.iloc[0].hour == 14
    assert r.candles.timestamp.iloc[1].hour == 13


def test_missing_volume_and_spread(tmp_path):
    r = load(tmp_path, header="Timestamp,Open,High,Low,Close\n",
             rows=[",".join(ROWS[0].split(",")[:5])])
    assert r.report.status == "WARNING"
    assert len([i for i in r.report.issues if i["code"] == "optional_missing"]) == 3


def test_missing_timestamp_column(tmp_path):
    r = load(tmp_path, header=HEADER.replace("Timestamp", "UnknownDate"))
    assert "missing_timestamp_column" in codes(r)
    assert r.report.status == "FAIL"
