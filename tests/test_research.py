import json
from src.research import load_register, render, main


def test_source_and_hypothesis_registers():
    sources, register = load_register()
    assert len(sources["sources"]) == 9
    assert len(register["hypotheses"]) == 7
    assert all(s["access_reviewed"] for s in sources["sources"])
    assert all(h["status"] == "defined_not_tested" for h in register["hypotheses"])


def test_report_and_plan(tmp_path):
    output = tmp_path / "report.md"
    plan = tmp_path / "plan.json"
    main(["--output", str(output), "--freeze-plan", str(plan)])
    assert "No strategy was backtested" in output.read_text()
    assert json.loads(plan.read_text())["status"] == "plan_only_no_tests_executed"
