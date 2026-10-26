"""Streamlit research dashboard for current gold market context."""
import json
from pathlib import Path
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.cot import acquire_cot
from src.fundamentals import SERIES, combine_macro_context, fetch_fred_series, summarize_fred_series
from src.market_analysis import detect_supply_demand_zones, prepare_price_action, summarize_price_action
from src.scenario import build_scenario_summary
from src.yahoo_data import acquire_yahoo


ROOT = Path(__file__).resolve().parent
INSTRUMENTS = {
    "COMEX Gold Futures (GC=F)": "GC=F",
    "Spot Gold indicative (XAUUSD=X)": "XAUUSD=X",
}
INTERVALS = {"15 minutes": "15m", "1 hour": "1h", "1 day": "1d"}

st.set_page_config(page_title="Gold market monitor", page_icon=":material/monitoring:", layout="wide")


@st.cache_data(ttl=6 * 60 * 60, max_entries=1, show_spinner=False)
def load_macro_context():
    summaries = []
    errors = []
    for definition in SERIES.values():
        try:
            observations = fetch_fred_series(definition["id"])
            summaries.append(summarize_fred_series(definition["id"], observations))
        except Exception as exc:
            errors.append(f"{definition['name']}: {exc}")
    return summaries, errors


def _saved_yahoo(symbol, interval):
    safe_symbol = re.sub(r"[^A-Za-z0-9_-]", "_", symbol)
    candidates = []
    for meta_path in (ROOT / "data/raw").glob(f"yahoo_{safe_symbol}_{interval}_*_metadata.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("status") == "ERROR":
                continue
            data_path = ROOT / meta["normalized_file"]
            if data_path.exists():
                candidates.append((meta.get("retrieved_at", ""), data_path, meta))
        except (OSError, ValueError, KeyError):
            continue
    if not candidates:
        return None
    _, data_path, meta = max(candidates, key=lambda item: item[0])
    data = pd.read_csv(data_path, parse_dates=["timestamp"])
    if "bar_complete_at_fetch" in data:
        data["bar_complete_at_fetch"] = data.bar_complete_at_fetch.astype(str).str.lower().eq("true")
    return data, meta


def _saved_cot():
    candidates = sorted((ROOT / "data/processed").glob("cftc_*.csv"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        return None
    data = pd.read_csv(candidates[-1], parse_dates=["as_of_date", "available_at"])
    return data, {"source": "saved CFTC snapshot", "processed_file": str(candidates[-1].relative_to(ROOT))}


def _price_chart(data, symbol, zones=()):
    has_volume = "real_volume" in data and data.real_volume.notna().any()
    has_rsi = "rsi14" in data and data.rsi14.notna().any()
    rows = 1 + int(has_volume) + int(has_rsi)
    heights = ([0.62, 0.18, 0.20] if has_volume and has_rsi else
               [0.76, 0.24] if has_volume or has_rsi else [1])
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=heights)
    fig.add_trace(go.Candlestick(x=data.timestamp, open=data.open, high=data.high,
        low=data.low, close=data.close, name="OHLC", increasing_line_color="#087f5b",
        decreasing_line_color="#c3523d"), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.timestamp, y=data.ema20, name="EMA 20",
        line={"color": "#b78022", "width": 1.4}), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.timestamp, y=data.ema50, name="EMA 50",
        line={"color": "#315b79", "width": 1.4}), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.timestamp, y=data.prior_range_high,
        name="Prior range high", line={"color": "#94a69d", "width": 1, "dash": "dot"}), row=1, col=1)
    fig.add_trace(go.Scatter(x=data.timestamp, y=data.prior_range_low,
        name="Prior range low", line={"color": "#94a69d", "width": 1, "dash": "dot"}), row=1, col=1)
    next_row = 2
    if has_volume:
        fig.add_trace(go.Bar(x=data.timestamp, y=data.real_volume, name="Provider volume",
            marker_color="#94a69d", opacity=0.55), row=next_row, col=1)
        fig.update_yaxes(title_text="Volume", row=next_row, col=1)
        next_row += 1
    if has_rsi:
        fig.add_trace(go.Scatter(x=data.timestamp, y=data.rsi14, name="RSI 14",
            line={"color": "#315b79", "width": 1.3}), row=next_row, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#94a69d", row=next_row, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#94a69d", row=next_row, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=next_row, col=1)
    fig.update_layout(height=560, margin={"l": 10, "r": 10, "t": 28, "b": 8},
        paper_bgcolor="#fff", plot_bgcolor="#fff", font={"color": "#182522", "size": 11},
        xaxis_rangeslider_visible=False, legend={"orientation": "h", "y": 1.03},
        title={"text": f"{symbol} · completed bars", "x": 0.01, "xanchor": "left"})
    chart_end = data.timestamp.iloc[-1]
    for zone in zones:
        if not zone["active"] or zone["distance_atr"] > 5:
            continue
        demand = zone["direction"] == 1
        zone_color = "rgba(8, 127, 91, 0.12)" if demand else "rgba(195, 82, 61, 0.12)"
        border_color = "#087f5b" if demand else "#c3523d"
        fig.add_shape(type="rect", x0=zone["created_at"], x1=chart_end,
            y0=zone["bottom"], y1=zone["top"], xref="x", yref="y",
            fillcolor=zone_color, line={"color": border_color, "width": 1}, layer="below")
        fig.add_annotation(x=chart_end, y=(zone["bottom"] + zone["top"]) / 2,
            xref="x", yref="y", text="Demand candidate" if demand else "Supply candidate",
            showarrow=False, xanchor="right", font={"color": border_color, "size": 10},
            bgcolor="rgba(255,255,255,0.82)")
    fig.update_xaxes(showgrid=True, gridcolor="#edf1ee")
    fig.update_yaxes(showgrid=True, gridcolor="#edf1ee", title_text="Price", row=1, col=1)
    return fig


def _render_cot(data, metadata):
    managed = data.loc[data.category.eq("managed_money")].sort_values("as_of_date")
    if managed.empty:
        st.info("No managed-money observations in this CFTC snapshot.")
        return
    latest = managed.iloc[-1]
    current_net = int(latest.net_positions)
    change = latest.net_change
    percentile = latest.historical_percentile
    first, second, third = st.columns(3)
    first.metric("Managed money net", f"{current_net:,}",
        delta=f"{int(change):+,} contracts" if pd.notna(change) else None)
    second.metric("Latest report date", latest.as_of_date.strftime("%d %b %Y"))
    third.metric("Prior-history percentile",
        f"{percentile:.0%}" if pd.notna(percentile) else "Not enough history")
    fig = go.Figure(go.Scatter(x=managed.as_of_date, y=managed.net_positions,
        mode="lines", line={"color": "#087f5b", "width": 2}, name="Net positions"))
    fig.update_layout(height=340, margin={"l": 10, "r": 10, "t": 24, "b": 10},
        paper_bgcolor="#fff", plot_bgcolor="#fff", title="COMEX gold · managed-money net positions",
        yaxis_title="Long minus short contracts", font={"color": "#182522", "size": 11})
    fig.update_xaxes(showgrid=True, gridcolor="#edf1ee")
    fig.update_yaxes(showgrid=True, gridcolor="#edf1ee")
    st.plotly_chart(fig, width="stretch", alt="Weekly COMEX gold managed-money net positions")
    st.caption(
        "CFTC categories are weekly, aggregated futures positions, not identified traders, live orders, "
        "or an intraday directional signal. Finalized archives may be revised. "
        f"Availability basis: {latest.get('availability_basis', 'not recorded')}."
    )
    st.caption(f"Snapshot: {metadata.get('processed_file', 'newly acquired CFTC archive')}")


st.title("Gold market monitor")
st.markdown(
    "See the latest completed price bars, released economic data, and what would support either direction. "
    "This is a market scenario summary, not a promise or a trade instruction."
)

with st.sidebar:
    st.header("Price data")
    instrument_label = st.selectbox("Instrument", list(INSTRUMENTS))
    symbol = INSTRUMENTS[instrument_label]
    interval_label = st.selectbox("Chart interval", list(INTERVALS), index=0)
    interval = INTERVALS[interval_label]
    period_options = {"15m": ["5d", "1mo"], "1h": ["1mo", "3mo", "6mo", "1y"],
                      "1d": ["3mo", "1y", "5y"]}[interval]
    period = st.selectbox("History", period_options, index=0)
    st.caption("Yahoo data is an indicative provider snapshot. GC=F is a futures proxy, not broker XAU/USD.")
    fetch_market = st.button("Refresh prices", type="primary", width="stretch")
    st.divider()
    st.header("Positioning and drivers")
    cot_start = st.selectbox("CFTC archive from", list(range(2010, pd.Timestamp.now().year + 1)),
                             index=max(0, 2023 - 2010))
    fetch_positioning = st.button("Refresh CFTC report", width="stretch")
    refresh_macro = st.button("Refresh economic data", width="stretch")
    st.caption("CFTC positioning is weekly, not a live order feed.")

if refresh_macro:
    load_macro_context.clear()

if fetch_market:
    with st.spinner(f"Requesting {symbol} {interval} data..."):
        try:
            frame, report, metadata = acquire_yahoo(symbol=symbol, interval=interval, period=period, root=ROOT)
            st.session_state.market_data = frame
            st.session_state.market_meta = metadata
            st.session_state.market_quality = report.status
            st.session_state.market_key = (symbol, interval)
            st.session_state.market_error = None
        except Exception as exc:
            st.session_state.market_error = str(exc)

if fetch_positioning:
    with st.spinner("Downloading official CFTC futures-only archives..."):
        try:
            cot_data, cot_meta = acquire_cot(list(range(cot_start, pd.Timestamp.now().year + 1)), root=ROOT)
            st.session_state.cot_data = cot_data
            st.session_state.cot_meta = cot_meta
            st.session_state.cot_error = None
        except Exception as exc:
            st.session_state.cot_error = str(exc)

if st.session_state.get("market_error"):
    st.error(st.session_state.market_error, title="Price data could not be refreshed")
if st.session_state.get("cot_error"):
    st.error(st.session_state.cot_error, title="CFTC report could not be refreshed")

with st.spinner("Loading released U.S. economic data..."):
    macro_summaries, macro_errors = load_macro_context()
macro_context = combine_macro_context(macro_summaries)

market_data = st.session_state.get("market_data")
market_meta = st.session_state.get("market_meta", {})
market_quality = st.session_state.get("market_quality", "")
if st.session_state.get("market_key") != (symbol, interval):
    saved = _saved_yahoo(symbol, interval)
    if saved:
        market_data, market_meta = saved
        market_quality = market_meta.get("status", "Saved snapshot")
    else:
        market_data = None

cot_snapshot = st.session_state.get("cot_data")
cot_metadata = st.session_state.get("cot_meta", {})
if cot_snapshot is None:
    saved_cot = _saved_cot()
    if saved_cot:
        cot_snapshot, cot_metadata = saved_cot

market_tab, drivers_tab, research_tab = st.tabs(["Price action", "Drivers and next scenarios", "Research and limits"])

with market_tab:
    if market_data is None:
        st.info("No saved snapshot for this selection. Refresh market data to request the latest provider bars.")
    else:
        try:
            price_data = prepare_price_action(market_data)
            summary = summarize_price_action(price_data)
        except ValueError as exc:
            st.warning(str(exc))
            price_data = pd.DataFrame()
        if not price_data.empty:
            change = summary["change_1bar"]
            change_pct = change / (summary["close"] - change) * 100 if pd.notna(change) and summary["close"] != change else None
            zones = detect_supply_demand_zones(price_data)
            with st.container(horizontal=True):
                st.metric("Latest completed price", f"{summary['close']:,.2f}",
                    delta=f"{change:+,.2f} ({change_pct:+.2f}%)" if change_pct is not None else None)
                st.metric("Trend", summary["trend"])
                st.metric("Compared with recent range", summary["range_break"])
                st.metric("Typical recent movement", f"{summary['atr14']:,.2f}" if pd.notna(summary["atr14"]) else "Warming up")
                st.metric("Momentum gauge (RSI)", f"{summary['rsi14']:.0f}/100" if pd.notna(summary["rsi14"]) else "Warming up")
            st.plotly_chart(_price_chart(price_data, symbol, zones), width="stretch",
                alt=f"{symbol} chart with completed candles, trend indicators, and nearby supply and demand candidate ranges")
            nearby_zones = [zone for zone in zones if zone["active"] and zone["distance_atr"] <= 5]
            st.subheader("Nearby supply and demand candidates")
            st.warning(
                "These shaded ranges are inferred from past candle structure. They are places to watch for a possible price reaction, not confirmed resting orders or guaranteed support/resistance.",
                title="Institutional orders are not visible in this feed",
            )
            if nearby_zones:
                zone_rows = [{
                    "Area": zone["type"],
                    "Price range": f"{zone['bottom']:,.2f} – {zone['top']:,.2f}",
                    "Distance": f"{zone['distance_atr']:.1f} ATR",
                    "Age": f"{zone['age_bars']} bars",
                    "Retests": zone["touches"],
                    "Formed": pd.Timestamp(zone["created_at"]).strftime("%d %b %H:%M UTC"),
                } for zone in nearby_zones]
                st.dataframe(pd.DataFrame(zone_rows), hide_index=True, alt="Nearby price-action supply and demand candidate zones")
            else:
                st.info("No active candidate zones are within 5 ATR of the latest completed price.")
            direction = "above" if pd.notna(summary["ema20"]) and summary["close"] > summary["ema20"] else "below"
            if pd.notna(summary["ema20"]) and pd.notna(summary["ema50"]):
                st.markdown(
                    f"**In plain language:** the last finished bar closed {direction} the short-term average. "
                    f"The averages are {'stacked upward' if summary['ema20'] > summary['ema50'] else 'stacked downward'}, "
                    f"and price is {summary['range_break'].lower()} compared with its previous 20 bars."
                )
            else:
                st.markdown(f"**In plain language:** {summary['range_break']}; there is not enough history for the average comparison yet.")
            scenario = build_scenario_summary(summary, macro_context)
            st.info(scenario["view"], title="What the current evidence leans toward")
            st.caption(scenario["limitation"])
            st.caption(
                f"Last bar: {summary['timestamp']} · Data source: Yahoo · Retrieved: {market_meta.get('retrieved_at', 'saved snapshot; time not recorded')} · "
                f"Data check: {market_quality}."
            )
            st.download_button("Download displayed candles", price_data.to_csv(index=False),
                file_name=f"{symbol.replace('=', '_')}_{interval}_completed.csv", mime="text/csv", width="content")
        if market_quality == "FAIL":
            st.warning("The data check found problems with this snapshot. Individual valid bars are shown for inspection only; do not use this series for conclusions.", title="Check the data quality")
        if symbol == "GC=F":
            st.warning("GC=F is a continuous gold-futures proxy, not your broker's spot-gold price. Futures/spot differences, contract rolls, gaps, and trading hours can affect the comparison.", title="About this gold price")

with drivers_tab:
    st.subheader("Economic drivers: real yields and the U.S. dollar")
    st.markdown("Gold often responds to changes in the return available on inflation-protected bonds and to the U.S. dollar. These relationships can change; they are context, not mechanical rules.")
    if macro_summaries:
        macro_columns = st.columns(len(macro_summaries))
        for column, item in zip(macro_columns, macro_summaries):
            value = f"{item['latest']:.2f}%" if item["id"] == "DFII10" else f"{item['latest']:.2f}"
            change_text = None
            if item["change"] is not None:
                suffix = " pp over 20 releases" if item["id"] == "DFII10" else " points over 20 releases"
                change_text = f"{item['change']:+.2f}{suffix}"
            column.metric(item["name"], value, delta=change_text, delta_color="off")
            column.caption(f"Latest release: {item['date']:%d %b %Y} · {item['view']}")
            column.markdown(f"[Open official series]({item['source_url']})")
    if macro_errors:
        for error in macro_errors:
            st.warning(error, title="Economic data unavailable")
    st.caption("The real-yield series is daily; the broad dollar series can arrive with a delay. Each value shows its observation date. Old releases are excluded from the directional context.")

    if market_data is not None:
        try:
            scenario = build_scenario_summary(summarize_price_action(prepare_price_action(market_data)), macro_context)
            st.subheader("What could happen next")
            st.info(scenario["view"], title="Scenario balance, not a forecast")
            left, right = st.columns(2)
            with left:
                with st.container(border=True):
                    st.markdown("**Upside case**")
                    st.markdown("**What would support it**")
                    if scenario["upward_factors"]:
                        for factor in scenario["upward_factors"]:
                            st.markdown(f"- {factor}")
                    else:
                        st.markdown("- No strong upward factors in the selected data.")
                    st.markdown(f"**What would weaken it:** {scenario['upside_invalidation']}")
            with right:
                with st.container(border=True):
                    st.markdown("**Downside case**")
                    st.markdown("**What would support it**")
                    if scenario["downward_factors"]:
                        for factor in scenario["downward_factors"]:
                            st.markdown(f"- {factor}")
                    else:
                        st.markdown("- No strong downward factors in the selected data.")
                    st.markdown(f"**What would weaken it:** {scenario['downside_invalidation']}")
            if scenario["other_factors"]:
                st.caption("Other observations: " + " ".join(scenario["other_factors"]))
            st.caption(scenario["limitation"])
        except ValueError as exc:
            st.info(f"Refresh price data before comparing scenarios. {exc}")
    else:
        st.info("Refresh price data to compare the upside and downside scenarios.")

    st.divider()
    st.subheader("What futures traders are reporting")
    if cot_snapshot is None:
        st.info("No CFTC report is loaded. Use **Refresh CFTC report** to fetch the official futures-only archives.")
    else:
        _render_cot(cot_snapshot, cot_metadata)

with research_tab:
    st.subheader("How to read this page")
    st.markdown("**Moving averages** describe recent direction. **RSI** compares recent upward and downward moves; it does not tell you when a reversal will happen. **ATR** describes typical price movement, not direction.")
    st.markdown("**Real yields and the dollar** are observable economic drivers. This page compares each latest released value with its value 20 observations earlier; it does not infer central-bank intent or use unreleased data.")
    st.markdown("**CFTC positioning** groups futures reports by trader category. The data are weekly and delayed: they do not show a specific institution, its live orders, or the cause of today's candle.")
    st.markdown("**Volume profile** is only an approximate allocation of candle volume across each bar's price range. It is not the platform's full lower-timeframe profile and may represent tick activity for spot/CFD feeds.")
    st.subheader("Research sources and limits")
    sources = [
        ("World Gold Council, Gold as a strategic asset (2026)",
         "https://www.gold.org/goldhub/research/relevance-of-gold-as-a-strategic-asset",
         "Gold demand has several sources; investment demand can respond to uncertainty while consumer demand behaves differently."),
        ("Federal Reserve / FRED, 10-year inflation-adjusted Treasury yield (DFII10)",
         "https://fred.stlouisfed.org/series/DFII10", "Daily percent series; use the displayed observation date."),
        ("Federal Reserve / FRED, broad U.S. dollar index (DTWEXBGS)",
         "https://fred.stlouisfed.org/series/DTWEXBGS", "Official broad trade-weighted dollar series; releases can lag."),
        ("Hauptfleisch, Putniņš & Lucey (2016), gold price discovery",
         "https://doi.org/10.1002/fut.21775", "London spot and New York futures both contributed; relative contribution varied by time and liquidity."),
        ("CFTC, Commitments of Traders explanatory notes",
         "https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm", "Official category and reporting context; weekly aggregated positions."),
        ("Osler (2001), Federal Reserve Bank of New York Staff Report 125",
         "https://www.newyorkfed.org/research/staff_reports/sr125.html", "Observed stop/take-profit clustering in FX dealing-bank orders; not evidence about gold candles."),
        ("Cont, Kukanov & Stoikov (2014), order-book events",
         "https://doi.org/10.1093/jjfinec/nbt003", "NYSE equity event/book data; candle volume alone cannot reproduce order-flow imbalance."),
    ]
    for title, url, note in sources:
        with st.container(border=True):
            st.markdown(f"[{title}]({url})")
            st.caption(note)
    st.caption(
        "These studies inform which factors to monitor; they do not prove this dashboard can predict gold returns. "
        "The registered strategy hypotheses remain untested."
    )

st.caption("Research and education only · delayed data may be shown · no personalized advice or order routing")