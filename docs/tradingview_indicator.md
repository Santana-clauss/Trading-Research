# TradingView indicator: Milestone A

Compilation: UNVERIFIED in TradingView. No connected Pine compiler/browser session is available here. The source has local safety checks, which are NOT compilation or runtime validation.
Performance: NOT TESTED. No strategy, portfolio, fills or statistical edge is claimed.

The complete standalone script is tradingview/indicators/xauusd_sd_detector.pine. It needs no Python process, files, API key or library import. Existing Yahoo/CFTC tools and raw data remain unchanged. No strategy file is created in A; B/C require review first.

## Add it to your chart

1. Open your broker's XAU/USD feed in TradingView. Choose standard candles and the 15-minute chart, not Heikin Ashi, Renko or a tick/range chart.
2. Open Pine Editor, create a new indicator and replace the template with the ENTIRE local .pine file, including //@version=6.
3. Save as XAUUSD Candidate Zones Research A, then select Add to chart. This invokes TradingView's actual compiler.
4. Default Entry timeframe is 15 and Higher timeframe is 60. If the chart differs, a status warning appears and entries/zone mutations are disabled. Both timeframes are configurable; the entry timeframe must be intraday below one day and HTF strictly greater.
5. If compilation reports an error, record its exact message and line number. Do not interpret local Python checks as proof of compilation.
6. For alerts, choose the indicator and Confirmed BUY / Confirmed SELL / Touch BUY at close / Touch SELL at close / zone / hypothetical-level event. Choose Once Per Bar Close. For detailed price/reason messages, enable detailed alert() messages and select Any alert() function call.
7. Alerts snapshot the script and inputs. Recreate alerts after changing settings. Alerts are notifications, not executed orders.

PowerShell copy command:

```powershell
Get-Content -LiteralPath .\tradingview\indicators\xauusd_sd_detector.pine -Raw | Set-Clipboard
```

No local compiler installation is required or claimed. TradingView access/market history depends on the user's account and selected feed.

## Exact structure and HTF rules

- A swing requires left=3 and right=3 bars by default. ta.pivothigh/low becomes available only on the right-confirmation candle. A circle is placed on the confirmation bar at that price, NEVER shifted backward to the original pivot.
- Known swing levels are tested before installing the newly confirmed pivots on a bar. A completed close strictly above an unbroken swing high is a bullish structure event; strictly below an unbroken swing low is bearish. Each level is consumed once. If contradictory levels would break simultaneously, neither direction is forced.
- A break opposite the last event direction is called CHoCH; an initial or same-direction break is BOS. These terms are this script's explicit price rules, not proof of institutional activity.
- The latest event sets structural direction. HTF becomes neutral if either swing side is not known, no event has occurred, the event is older than 48 HTF bars, or latest swing high <= previous swing high AND latest swing low >= previous swing low (a contraction proxy).
- Optional EMA50 agreement (on by default within the HTF gate) also neutralizes bullish structure if close <= EMA, or bearish structure if close >= EMA. Missing EMA blocks aligned signals.
- request.security uses ticker.standard for the current feed; EVERY returned HTF field is shifted [1] inside f_htf(), with lookahead_on and gaps_off. Only the preceding completed HTF observation is visible. No barstate.isconfirmed trick is used inside security.
- Completed context updates at the next HTF opening; signals still wait for the entry-bar close. At an exact H1 boundary this can add up to one M15 bar of recognition delay. This conservative lag is deliberate.
- requireHtf gates actual signals. Turning it off also bypasses its embedded EMA rule. To isolate EMA, keep requireHtf on and toggle contextEma.
- requireLocal independently requires current entry-chart break direction and absence of the contraction proxy. These are heuristic range/conflict definitions, not a complete regime classifier.

## Zone rules and lifecycle

A directional BOS OR CHoCH candle must have a same-direction body and, by default, abs(close-open) >= 1.0 * PRIOR ATR14. The prior ATR excludes the break candle. The threshold can be independently disabled.

Search the preceding 10 candles, excluding the break candle, for the most recent opposite body. Dojis are skipped. Demand uses the last bearish candle; supply uses the last bullish candle. Full high/low boundaries are default; Body is the alternative. Require positive width and a break close beyond the near edge. Candle clusters are not implemented.

The zone exists at the completed break candle, not at its historical origin. Box left edge is creation time. It cannot be retested on its creation candle. Boxes are teal (demand) / maroon (supply), become lighter after a retest, and gray when invalid/expired.

A touch is high >= bottom AND low <= top on a later bar. A retest episode increments only when overlap changes from false to true. Consecutive overlapping bars count once. At least one non-overlap bar is required to start another episode. Gap-through bars with no overlap do not get a fictional touch.

Close invalidation (default) requires a strict close beyond the far boundary; Wick uses strict high/low beyond it. Equality at the boundary is not invalidation. Age >96 entry bars expires the zone (bar96 is still eligible). Oldest objects are pruned when maxZones=12 is exceeded, including active zones if necessary; maximum setting40. This bounds script resources.

Default firstOnly permits episode1 and rejects episode2+. By default each model can signal only once for a zone. repeatVisit only rearms models on a new episode when firstOnly is disabled. If all gates fail on the touch candle, A does not later pretend to have signalled that earlier touch.

Box status/extension naturally changes as later bars arrive. Historic signal markers are not relocated or deleted by zone invalidation. Pruned old drawings disappear by the documented cap, not by hindsight selection.

## Entry rules

All events require a completed standard entry-timeframe candle. There is no intrabar mode in A.

Common gates: sufficient prior ATR; valid nonexpired zone; eligible touch episode; enabled local/HTF alignment; allowed session; enabled volatility/relative-volume gates; current body/range >= minimum body fraction; optional absolute distance(close, near edge) <= maxDistanceAtr * prior ATR; valid planned stop/target/R; signal bar has NOT already crossed the proposed stop.

A (aggressive): the completed bar begins a NEW overlap episode. Signal reference entry is that bar's CLOSE. This is a touch observed at close, NOT a resting limit entry at the near edge and NOT evidence of an earlier intrabar fill.

B (confirmed): a directional candle occurs strictly AFTER the touch bar, within the next3 bars by default. Bullish is close>open; bearish is close<open. Reclaim near edge additionally requires demand close>top or supply close<bottom. It may occur after price has left the zone; enable the distance filter to constrain that. The current zone must still be valid.

Both models can be enabled. Each has a separate sent flag. B takes priority if both qualify on the same candle. Newest qualifying zone wins and at most one signal is issued per candle. Different models can signal at different times on the same zone: these are comparison hypotheses, not simultaneous live positions.

The close is an observable reference, not a promised executable price. A future strategy must use realizable subsequent fills; historical resting touch orders require a separate preplaced-order model. This explicitly differs from the original H01 intrabar A hypothesis. The new milestone-specific variant is recorded in research/hypotheses/pine_milestone_a.json.

## Hypothetical price levels

- BUY SL = floor_to_chart_tick(bottom - max(prior ATR*0.1, chart tick*1)).
- SELL SL = ceil_to_chart_tick(top + max(prior ATR*0.1, chart tick*1)).
- No universal gold pip or lot/contract conversion is used. No position sizing or monetary risk is presented.
- Require a stop distance of at least one tick and the signal bar low>SL for a BUY or high<SL for a SELL. This rejects signals whose proposed stop was already crossed during their setup bar.
- Fixed target = entry +/- targetR * risk, rounded toward entry to a chart tick.
- Nearest opposing zone mode chooses the closest near edge AHEAD of entry among currently valid retained opposite zones. No opposite zone means no signal, rather than a silent fallback. Same-bar broken/expired zones are excluded.
- Planned gross price R = direction*(target-entry)/abs(entry-stop); require positive reward and plannedR>=minimumR. It is not net of spread/slippage/fees.
- Blue entry, red SL and green TP lines start at the signal candle. Default five level sets retained (maximum20). Reasons show model, originating structure event, zone creation UTC time, HTF bias and retest status.
- On later CLOSED bars, observed stop/target crossings end the line set and update the table. If both are inside the same OHLC bar, stop observation takes priority. This is not a fill model, win/loss metric or backtest. Signals from the close do not test exits against earlier prices in that same signal candle.

## Filters and displays

Chart market open is the default session gate and uses the chart symbol's `session.ismarket`. For feeds without separate market/extended sessions, TradingView can report this as true whenever the symbol has bars; no script can infer a broker outage or liquidity condition from that flag. Alerts only run on realtime bars, so an exchange-closed feed normally produces no new alert events. Asian09-18 Asia/Tokyo, London08-17 Europe/London and NewYork08-17 America/New_York remain configurable local windows; All explicitly disables the session gate. Pine time() checks bar-OPEN membership; a signal closes at bar end. Sessions use all calendar days with available feed bars, not a broker holiday calendar. IANA zones handle DST; overlapping selected sessions form a union (no double signal). Shading is display-only.

Optional ATR-percent filter: 100*prior ATR/prior close within inclusive min/max. It is a simple volatility proxy, not a fitted regime model.
Optional relative volume: current completed feed volume / mean of previous20 volumes >=1.5. Missing/zero current volume or missing/zero denominator BLOCKS signals when enabled. It never invents centralized spot volume, trade aggressor direction or OFI. Default off.
Prior-bars volume-profile proxy (displayed by default): previous96 bars only, 24 configurable price rows, with each candle's chart-reported volume spread uniformly across its high-low range. POC is the highest-volume row; VAH/VAL enclose the configured 70% value area. This is NOT TradingView's built-in lower-timeframe volume profile and does not know the within-bar traded-price distribution. It is feed-dependent and particularly weak for OTC XAU/USD tick volume. The proxy is context, not an institutional-flow signal. High-confluence ranking gives one point each for matching HTF direction, local structure direction, B confirmation, close on the favorable side of profile POC, close outside the profile value area in the signal direction, EMA20/EMA50 alignment, and relative volume >=1.5. The default highlight threshold is 5/7. It is an uncalibrated checklist, not a win probability, expected return or proven high-probability setup.
Body fraction applies to the signal candle; departure/body ATR applies to the structure-break candle.
Distance filter defaults off. These settings genuinely gate signals when enabled; they are not decorative.
Previous-day high/low display uses completed daily [1] values; it does NOT gate signals. A day means this feed's bar boundary, not a universal gold session.
Display toggles for zones, pivots, structure, markers, reason labels, levels, shading, prior-day levels and table are independent of signal qualification.

The table distinguishes chart/entry/HTF, completed HTF bias, closed chart structure, latest hypothetical setup and observed level state, retained active zones, session/ATR/volume gates, profile proxy levels, the high-confluence count/threshold and feed limitations.

## Research decisions and data boundaries

The existing nine-source catalog is retained. Four official Pine references are in research/sources/pine_reference_sources.json. Every implemented or considered feature is mapped in research/research_to_code.csv.

S01 gold price-discovery evidence motivates fixed session comparisons, not a guaranteed London/New York edge. S06 multi-month momentum motivates testing trend context, but its horizon does not validate H1/M15 rules. S02 equity OFI evidence is used to AVOID mislabelling chart volume; optional relative volume is a new unsigned-volume hypothesis. S07 stop-policy research motivates explicit risk tests, not these exact stop parameters. S08 motivates fixed definitions, a small baseline and honest uncertainty. Numeric zone/ATR/EMA/rejection thresholds remain researcher-chosen hypotheses.

LibraryCOT is a genuine supported TradingView access route, not technically impossible. It is NOT imported or used here: symbol/category mapping, actual release availability and archive revisions must be audited before a causal weekly gate. Existing Python COT remains available externally. No arbitrary local Python/yfinance CSV can be read by this standalone indicator.

Actual order-book event OFI, cancellations and depth are not recoverable from ordinary OHLCV. Pine has specialist supported footprint capabilities for some symbols/accounts, but that is not automatically a complete book or available on this broker XAU/USD feed. A uses none of it. Historical broker spreads, commissions and slippage are also NOT inferred from candle range; no fake cost filter is offered.

Equal highs/lows, prior-session extrema and liquidity-sweep gates are feasible price proxies but deferred due insufficient direct evidence and added selection complexity. Prior-day levels are the descriptive alternative. No claim of actual hidden institutional orders, stops or trader identity is made. No additional default filters are justified by their names.

## Visual acceptance checklist (must be run in TradingView)

Record each observation, feed, settings and script hash in research/pine_validation_runs.csv. The CSV initially has only a header: no compilation/trade results were invented.

1. Compile and add to a standard M15 XAU/USD chart. Record exact editor warnings/errors and script version. Confirm no runtime errors after loading sufficient history. The default `Chart market open` session uses the feed's market-state flag; it is not a custom liquidity-hours detector.
2. Bar Replay: before a right-confirmation bar closes, no pivot should be available. After close, its dot is on the confirmation candle, not on the old pivot.
3. Step through a BOS/CHoCH. The box begins at the closed break candle, and no touch entry appears on that candle. Verify the chosen prior opposing candle and displacement arithmetic.
4. During a forming H1 candle, its unfinished high/low/close must not influence HTF bias. Record closed-bar signals; reload with identical data/settings and compare timestamps.
5. Verify adjacent overlap bars remain a single episode; leave and revisit to get touch2. Check firstOnly blocks it. Verify no model repeats during the same visit.
6. Enable A only, then B only. B must occur strictly after touch, not on it. Check directional close versus near-edge reclaim, the3-bar window, neutral/conflicting HTF blocks, and missing-volume behavior.
7. Check long SL below zone, short SL above; gross R after tick rounding; reject prior stop crosses and missing opposing-zone target. Step into later simultaneous SL/TP OHLC range: stop observation wins, without a claimed fill.
8. Toggle every signal filter separately and keep dates/data fixed. Toggle visuals independently: they must not change signal qualification. No signal means inspect warmup, bias, touch counts and gate table rather than lowering thresholds until attractive.
9. Verify session boundaries around March/November DST changes, retaining IANA zones. Compare bars using bar-open membership.
10. Switch to H1 with default settings: HTF bias is viewable but entry signals/zones are intentionally disabled with a timeframe warning. For H1 entries change entry to60 and HTF to240; that is a DIFFERENT experiment and must be logged. Return to M15/60 for the intended baseline.
11. Create a paper alert using Any BUY/SELL setup or a direction-specific/high-confluence alert with Once Per Bar Close; confirm no open-bar trigger. The script cannot create a running TradingView alert itself. Recreate alerts after settings change.
12. Compare the prior-bars POC/VAH/VAL proxy with the platform's built-in profile on the same session. Differences are expected because this proxy allocates each bar's volume uniformly through its high-low range rather than using lower-timeframe trades. Confirm profile values at each signal use only earlier bars and inspect both exchange-volume futures and OTC tick-volume feeds separately.

## Local checks and later performance validation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B -m src.pine_audit
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
Get-FileHash -LiteralPath .\tradingview\indicators\xauusd_sd_detector.pine -Algorithm SHA256
```

The audit only checks a narrow set of delimiters/timing guards and known request forms; it is NOT a Pine grammar parser/compiler, simulated Pine execution or profitability test. Source mutation tests verify it catches removed timing safeguards. Python tests also validate traceability and preserve existing downloader/parser/COT coverage. TradingView compilation and replay remain manual acceptance steps.

For existing data tools (not dependencies of this indicator):

```powershell
.\.venv\Scripts\python.exe -m src.yahoo_data --interval 1h --period 1mo
.\.venv\Scripts\python.exe -m src.yahoo_data --interval 15m --period 1mo
.\.venv\Scripts\python.exe -m src.data_loader --input data/raw/xauusd_m15.csv --timeframe 15min
.\.venv\Scripts\python.exe -m src.cot --year 2023 2024 2025
```

Set the broker timezone in config.json before naive broker CSV validation. Yahoo GC=F differs from spot/CFD feeds and has limited intraday retention. Existing real Yahoo snapshots failed OHLC checks and were preserved; no cleaning or redownload is part of A.

research/pine_ablation_plan.csv defines later A/B, HTF/EMA, freshness, session, ATR/displacement, volume, body, distance, confirmation and target comparisons. Each starts from a frozen baseline; the combination is predefined rather than selected from the best historical curve. All observed performance fields remain NOT TESTED until Milestone C. Compare identical feeds/periods/costs, record every parameter set and failure, use chronological untouched holdouts and purged/embargoed walk-forward folds. Account for serial dependence and multiple comparisons; no significance claim from win rate or screenshots.

Known remaining limits: actual Pine compilation/replay unverified; chart feed revisions and loaded-history start can change recalculated pivots/EMA; bounded drawings prune old zones/levels; OHLC paths and actual spreads/fills unknown; A close-touch is not an intrabar limit fill; neutral states can be conservative; source papers do not establish these thresholds; no strategy or performance test is included in A.

## Compiler correction: CE10150

The user-reported text identifier compiler error was corrected by renaming the function parameter to noteText and the local setup-label variable to setupText. Drawing function text= named arguments remain unchanged. Latest full offline suite: 81 passed; source audit passed. Successful TradingView recompilation remains UNVERIFIED; replace the entire editor source with the corrected local file and compile again.

## Historical chart display

Signals are evaluated on all loaded historical closed bars as well as new closed bars. They are not restricted to barstate.islast or realtime. Only the compact table is last-bar-only.

Historical BUY/SELL shapes remain across loaded history. The new default-on historical level plots also preserve blue entry, red stop and green target dots on each signal candle even after old drawing objects are pruned. Use the Data Window to inspect the signal's exact reference prices and planned R.

Retain archived historical zone boxes defaults on, with 80 archived boxes (configurable up to150), in addition to the retained signal-engine zones. Archived boxes are gray and explicitly labelled not monitored; archiving does not add them back to signal or target selection. Oldest archives are pruned at the configured cap. Recent continuous level sets remain capped separately; historical dots are plot series and do not consume line objects.

The status table now counts BUY and SELL signals in the LOADED chart history, not trades, wins or future predictions. A zero count can mean insufficient history, mismatched chart/entry timeframe or no qualifying setups. Use standard M15 XAU/USD with Entry15 and HTF60 for the default configuration. Enabling more historical drawing retention does not weaken filters or invent setups.

Scroll left after adding the script. Loaded history depends on TradingView and account/feed availability; max_bars_back controls series-reference buffers, not a last-1000-bars calculation window. Historical alerts are not replayed as notifications. Use Bar Replay to inspect when each signal became known. Successful TradingView recompilation remains unverified locally.


## BUY / SELL display clarification

Qualified entry markers now use normal-sized filled green BUY labels below candles and red SELL labels above candles. TOUCH identifies model A and CONFIRMED identifies model B. Zones say BUY AREA - demand (not entry) or SELL AREA - supply (not entry); those areas are candidates, not entry instructions. A table legend explains entry markers and blue entry/red stop/green target price levels. Red stop dots are not SELL signals and green target dots are not BUY signals. Entry rules and historical evaluation are unchanged. Replace the entire Pine Editor source to load this display update; successful TradingView compilation remains unverified locally.


## Readable chart defaults (supersedes earlier defaults)

Newest two active zones per side are visible; hidden zones remain eligible for signals and opposing targets. Archives, pivots, structure/reason labels and historical price dots default off. One level set and a compact table remain. Detailed table is optional. Confirmed zone status records a past signal.

Touch A defaults off. B defaults to Reclaim + retest break: a later directional candle within the confirmation window must close above demand top AND the first retest candle high for BUY; below supply bottom AND retest low for SELL. Retest extremes stay fixed during the visit. All existing alignment, risk and filter gates apply. Earlier confirmation options remain available. Signals change with these stricter defaults; performance is NOT TESTED.

Replace full Pine source and reset indicator settings to load new defaults; recreate alerts. Replay checks: no touch-only or same-touch-bar B entry; later qualifying close produces one marker; invalid/expired zones cannot signal; visual toggles do not change signals. Compilation: UNVERIFIED locally.
