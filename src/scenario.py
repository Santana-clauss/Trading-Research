"""Transparent directional scenario balance; not a calibrated forecast."""


def build_scenario_summary(price, macro):
    technical_score = 0
    technical_factors = []
    upward_factors = []
    downward_factors = []

    trend = price.get("trend")
    if trend == "Bullish alignment":
        technical_score += 1
        upward_factors.append("Price is above the 20- and 50-bar averages, with the shorter average on top.")
    elif trend == "Bearish alignment":
        technical_score -= 1
        downward_factors.append("Price is below the 20- and 50-bar averages, with the shorter average underneath.")
    else:
        technical_factors.append("Moving averages do not agree on direction.")

    range_break = price.get("range_break")
    if range_break == "Above prior range":
        technical_score += 1
        upward_factors.append("The latest close is above the previous 20-bar high.")
    elif range_break == "Below prior range":
        technical_score -= 1
        downward_factors.append("The latest close is below the previous 20-bar low.")
    else:
        technical_factors.append("Price remains within the previous 20-bar range.")

    momentum = price.get("change_4bar")
    if momentum is not None and momentum > 0:
        technical_score += 1
        upward_factors.append("The four-bar price change is positive.")
    elif momentum is not None and momentum < 0:
        technical_score -= 1
        downward_factors.append("The four-bar price change is negative.")
    else:
        technical_factors.append("Recent four-bar momentum is flat or unavailable.")

    macro_score = int(macro.get("score", 0))
    if macro_score > 0:
        upward_factors.append("Released real-yield / dollar data lean supportive for gold.")
    elif macro_score < 0:
        downward_factors.append("Released real-yield / dollar data lean against gold.")
    else:
        technical_factors.append("Macro drivers are mixed, stale, or unavailable.")

    score = technical_score + macro_score
    if score >= 2:
        view = "Upside scenario has more support right now"
    elif score <= -2:
        view = "Downside scenario has more support right now"
    else:
        view = "Signals are mixed; either direction remains plausible"

    return {
        "view": view,
        "score": score,
        "technical_score": technical_score,
        "macro_score": macro_score,
        "upward_factors": upward_factors,
        "downward_factors": downward_factors,
        "other_factors": technical_factors,
        "upside_trigger": "A completed close holds above the previous 20-bar high and EMA 20.",
        "upside_invalidation": "Price closes back inside the prior range and below EMA 20.",
        "downside_trigger": "A completed close holds below the previous 20-bar low and EMA 20.",
        "downside_invalidation": "Price closes back inside the prior range and above EMA 20.",
        "limitation": "This factor checklist is not probability-calibrated, backtested, or a promise of the next move.",
    }