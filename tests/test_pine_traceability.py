"""Static safety and research trace checks; never substitute for TradingView."""
import csv
import json
from pathlib import Path
import pytest
from src.pine_audit import audit_source

PINE = Path("tradingview/indicators/xauusd_sd_detector.pine")


def test_limited_pine_source_safety():
    assert audit_source(PINE.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("old,new", [
    ("bias[1], d[1]", "bias, d[1]"),
    ("[high[1], low[1]]", "[high, low]"),
    ("if barstate.isconfirmed and timeframesOk", "if timeframesOk"),
    ('alertcondition(buyB and barstate.isconfirmed,', 'alertcondition(buyB,'),
    ("alert.freq_once_per_bar_close", "alert.freq_all"),
])
def test_audit_detects_causal_guard_regressions(old, new):
    source = PINE.read_text(encoding="utf-8")
    assert old in source
    assert audit_source(source.replace(old, new))


def test_traceability_sources_implementations_and_results():
    original = json.loads(Path("research/sources/catalog.json").read_text())
    extra = json.loads(Path("research/sources/pine_reference_sources.json").read_text())
    known = {s["id"] for s in original["sources"] + extra["sources"]}
    with Path("research/research_to_code.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"research_id", "source_ids", "source_title", "source_url", "finding",
                "evidence_limits", "hypothesis", "exact_rule", "pine_file", "code_anchor",
                "implementation_status", "validation_method", "observed_result", "decision_reason"}
    assert len(rows) >= 12
    assert required <= set(rows[0])
    assert len({r["research_id"] for r in rows}) == len(rows)
    pine = PINE.read_text()
    for row in rows:
        assert set(row["source_ids"].split(";")) <= known
        assert row["implementation_status"] in {"implemented", "testing", "rejected", "unavailable"}
        assert row["evidence_limits"] and row["observed_result"]
        assert "not tested" in row["observed_result"].lower()
        if row["implementation_status"] == "implemented":
            assert row["pine_file"] == PINE.as_posix()
            assert row["code_anchor"] in pine
        else:
            assert row["decision_reason"]


def test_no_strategy_claim_in_milestone_a():
    assert not Path("tradingview/strategies/xauusd_sd_backtest.pine").exists()
    doc = Path("docs/tradingview_indicator.md").read_text(encoding="utf-8")
    assert "Compilation: UNVERIFIED" in doc
    assert "Performance: NOT TESTED" in doc

@pytest.mark.parametrize("old,new", [
    ("string noteText", "string text"),
    ("string setupText", "string text"),
])
def test_audit_detects_text_identifier_error(old, new):
    source = PINE.read_text(encoding="utf-8")
    assert old in source
    assert any("CE10150" in error for error in audit_source(source.replace(old, new)))


def test_text_named_arguments_remain_valid():
    source = PINE.read_text(encoding="utf-8")
    assert 'text = "BUY\\nTOUCH"' in source
    assert 'text = (direction == 1' in source
    assert not any("CE10150" in error for error in audit_source(source))


def test_session_profile_and_confluence_are_explicit_and_causal():
    source = PINE.read_text(encoding="utf-8")
    assert 'input.string("Chart market open"' in source
    assert '"Chart market open" => session.ismarket' in source
    assert "float profileFloor = ta.lowest(low[1], profileBars)" in source
    assert "for offset = 1 to profileBars" in source
    assert '"High-confluence BUY"' in source
    assert '"High-confluence SELL"' in source
    assert "not a probability" in source

