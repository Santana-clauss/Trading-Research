from src.scenario import build_scenario_summary


def test_supportive_technical_and_macro_inputs_lean_up_without_probability():
    result = build_scenario_summary(
        {"trend": "Bullish alignment", "range_break": "Above prior range", "change_4bar": 5},
        {"score": 1},
    )

    assert result["view"] == "Upside scenario has more support right now"
    assert result["score"] == 4
    assert result["upward_factors"]
    assert "not probability-calibrated" in result["limitation"]


def test_conflicting_technical_and_macro_inputs_remain_mixed():
    result = build_scenario_summary(
        {"trend": "Bullish alignment", "range_break": "Inside prior range", "change_4bar": -1},
        {"score": 0},
    )

    assert result["view"] == "Signals are mixed; either direction remains plausible"
    assert result["score"] == 0
    assert result["other_factors"]