"""Read and render the curated research register; no paper scraping or trading."""
import argparse
import json
from pathlib import Path
from .acquisition import write_json, utc_now
import hashlib


def load_register(root="."):
    root = Path(root)
    sources = json.loads((root / "research/sources/catalog.json").read_text(encoding="utf-8"))
    register = json.loads((root / "research/hypotheses/register.json").read_text(encoding="utf-8"))
    required = {"id", "title", "authors", "year", "source", "url", "market_dataset",
                "methodology", "key_findings", "limitations", "gold_applicability",
                "hypothesis", "classification", "access_reviewed"}
    ids = set()
    for source in sources["sources"]:
        if not required <= set(source) or source["id"] in ids:
            raise ValueError("Invalid or duplicate source metadata.")
        ids.add(source["id"])
    hypotheses = register["hypotheses"]
    if len({h["id"] for h in hypotheses}) != len(hypotheses):
        raise ValueError("Duplicate hypothesis IDs.")
    for h in hypotheses:
        if not set(h["source_ids"]) <= ids or not {"signal", "baseline", "parameters", "validation", "statistical_test", "minimum_sample"} <= set(h):
            raise ValueError("Invalid hypothesis definition or source link.")
    return sources, register


def render(root="."):
    sources, register = load_register(root)
    lines = ["# Gold evidence and research plan", "", f"Reviewed: {sources['review_date']}", "",
        "No strategy was backtested. Source review establishes context, not an intraday edge.",
        "Gold price-discovery research supports studying venue and session differences. US equity OFI findings require event data and cannot be reconstructed from gold candles. COT describes weekly categories, not real-time institutional orders.",
        "First test H01 (three entry models) with H07 (cost sensitivity). Defer other filters to limit multiple testing. Short Yahoo intraday history cannot support the planned multi-year validation.",
        "Historical COT requires verified release timestamps AND a revision/vintage audit. Retrieval-time-only data cannot be joined to earlier candles. Even supplied release calendars do not remove archive revision bias.",
        "Order-block patterns remain price-action hypotheses. No reviewed source establishes exact institutional orders or stop locations from OHLCV.", "",
        "## Evidence catalog", ""]
    for s in sources["sources"]:
        lines += [f"### {s['id']}: {s['title']}", "",
            f"Authors: {', '.join(s['authors'])}. Year: {s['year'] or 'undated/live documentation'}. Type: {s['classification']}.",
            f"Source: [{s['source']}]({s['url']})", f"Access reviewed: {s['access_reviewed']}",
            f"Dataset: {s['market_dataset']}", f"Method: {s['methodology']}",
            f"Finding: {s['key_findings']}", f"Limitations: {s['limitations']}",
            f"Gold relevance: {s['gold_applicability']}", f"Proposed test: {s['hypothesis']}", ""]
    lines += ["## Hypotheses (not executed)", "", register["activation_policy"], ""]
    for h in register["hypotheses"]:
        lines += [f"### {h['id']}: {h['title']}", "",
            f"Signal: {h['signal']}", f"Baseline: {h['baseline']}",
            f"Parameters: {json.dumps(h['parameters'])}", f"Data: {h['required_data']}",
            f"Sample requirements: {h['minimum_sample']}", f"Validation: {h['validation']}",
            f"Statistical test: {h['statistical_test']}", f"Decision rule: {h['rejection_rule']}",
            f"Notes: {h['notes']}", ""]
    lines += ["## Remaining data gaps", "",
        "Need broker XAU/USD history and contract/cost specifications for CFD conclusions. Yahoo futures are a different instrument and vendor roll construction is not verified.",
        "Need synchronized gold spot/futures quotes for price discovery replication, and quote/trade/depth events for OFI, aggressor classification, spread and execution-quality research.",
        "Session, regime, reversal and stop studies must be registered before testing; candlestick zone vocabulary is not evidence of institutional causation.", ""]
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", help="Optional Markdown report; refuses overwrite.")
    p.add_argument("--freeze-plan", help="Write a dated JSON plan snapshot before future testing; refuses overwrite.")
    args = p.parse_args(argv)
    text = render()
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(text)
        print(f"Research report saved: {target}")
    else:
        print(text)
    if args.freeze_plan:
        sources, register = load_register()
        blob = json.dumps(register, sort_keys=True).encode()
        write_json(args.freeze_plan, dict(frozen_at=utc_now().isoformat(), register=register,
            sha256=hashlib.sha256(blob).hexdigest(), status="plan_only_no_tests_executed",
            warning="Freeze exact data hashes, costs, split dates and code identifier before executing any strategy test."))


if __name__ == "__main__":
    main()
