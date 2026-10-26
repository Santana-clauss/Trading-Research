"""Narrow source-safety checks, NOT a Pine parser/compiler or execution test."""
from pathlib import Path
import re


def strip_literals_and_comments(source):
    # Keep line positions; ignore brackets inside text and // comments.
    pattern = r'"(?:\\.|[^"\\])*"|//[^\n]*'
    return re.sub(pattern, lambda m: " " * len(m.group(0)), source)


def audit_source(source):
    errors = []
    if not source.startswith("//@version=6\n"):
        errors.append("Pine v6 header missing.")
    clean = strip_literals_and_comments(source)
    if re.search(r"\b(?:string|int|float|bool|color)\s+text\b", clean):
        errors.append("Pine CE10150: text cannot be a user-defined variable or parameter name.")
    stack = []
    closing = {")": "(", "]": "[", "}": "{"}
    for character in clean:
        if character in "([{":
            stack.append(character)
        elif character in closing:
            if not stack or stack.pop() != closing[character]:
                errors.append("Unbalanced delimiters.")
                break
    if stack:
        errors.append("Unclosed delimiters.")
    if re.search(r"\b(strategy\s*\(|strategy\.|import\s)", clean):
        errors.append("Milestone A indicator must remain independent of strategy orders/imports.")
    if re.search(r"offset\s*=\s*-|\[\s*-\d+", clean):
        errors.append("Negative plotting/history offset requires review; pivots must not be backdated.")
    # This audit deliberately only supports the two known request forms in this file.
    requests = re.findall(r"request\.security\(", clean)
    if len(requests) != 2 or clean.count("lookahead = barmerge.lookahead_on") != 2:
        errors.append("Review changed request count or HTF lookahead settings.")
    try:
        htf = source.split("f_htf() =>", 1)[1].split("f_event(", 1)[0]
        return_tuple = htf.strip().splitlines()[-1].strip()
        if return_tuple != "[bias[1], d[1], ev[1], ema[1], close[1], time_close[1], ranging[1]]":
            errors.append("Every HTF returned value must have an in-context one-bar offset.")
    except IndexError:
        errors.append("HTF wrapper not found.")
    if '[high[1], low[1]]' not in clean:
        errors.append("Previous-day request must use completed values.")
    if "if barstate.isconfirmed and timeframesOk" not in clean:
        errors.append("Closed-bar mutation gate missing.")
    for line in clean.splitlines():
        if line.strip().startswith("alertcondition(") and "barstate.isconfirmed" not in line:
            errors.append("Alert condition is not explicitly close-gated.")
        if re.search(r"\balert\(", line) and "alert.freq_once_per_bar_close" not in line:
            errors.append("Detailed alert frequency must be once per close.")
    return errors


def main():
    path = Path("tradingview/indicators/xauusd_sd_detector.pine")
    errors = audit_source(path.read_text(encoding="utf-8"))
    for error in errors:
        print("FAIL:", error)
    if not errors:
        print("PASS: limited Pine source-safety checks. TradingView compilation/runtime remain UNVERIFIED.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
