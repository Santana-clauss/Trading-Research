# XAU/USD Supply-and-Demand Research

Research and paper trading only. No live order execution. Candidate zones are price-action hypotheses, not evidence of hidden institutional orders. Market-data snapshots and research reports exist; no strategy-performance results are established.

## Project status

Scaffold, CSV validation, Yahoo/CFTC acquisition and research registers are implemented. Milestone A now adds the Pine v6 indicator source; TradingView compilation/replay remains unverified. No strategy is implemented. Python 3.14.0 and the existing virtual environment are reused.

## Gold Market Monitor platform

Launch the interactive, research-only dashboard from the project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The Price action tab requests Yahoo candles on demand, excludes bars marked incomplete, and explains moving averages, prior range, ATR and RSI. It overlays active supply/demand price-action candidates formed after a confirmed swing break and directional displacement, using the last opposing candle range. The nearby-zone table reports bounds, distance, age and retests for candidates within 5 ATR; completed closes can invalidate a zone. These are possible reaction areas, not guaranteed reactions or evidence of resting institutional orders. Yahoo OHLCV does not provide the live order book, and spot/CFD gold has no single consolidated order book. CFTC futures-only positioning remains weekly aggregated category data, not live orders or exact price levels. The Drivers and next scenarios tab compares the latest released FRED 10-year real yield and broad U.S. dollar index with their values 20 observations earlier, then lists upside/downside evidence and invalidation conditions. Macro series are delayed and their observation dates are shown. The Research and limits tab links institutional and academic sources and explains what the data cannot establish. Scenario balance is not a probability forecast; there are no orders, position sizes, backtests, or performance claims. Network/provider outages leave prior snapshots intact; acquisition artifacts are append-only under data/raw, with validated outputs under data/processed.

## Windows PowerShell setup

Run these commands from the project folder, one at a time:

```powershell
Set-Location -LiteralPath 'C:\Users\HP PC\Desktop\Trading'
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m json.tool config.json
```

Virtual-environment creation normally produces no output. Installation should end with successful installation messages (or "Requirement already satisfied"). The last command prints formatted configuration. Using the environment's Python directly avoids PowerShell activation-policy changes.

Dependency versions below are initial compatibility bounds, not a reproducibility lock. A clean installation and dependency checks must be verified when the environment is created. The existing virtual environment passed package import checks and pip check after setup.

## Folders

- data/raw: original MT5 exports; preserve these unchanged.
- data/processed: later validated outputs; never fabricate missing prices.
- src: Python data/research utilities and limited Pine source-safety audit.
- tests: automated tests added alongside each implementation.
- scripts: later sample generator and command-line helpers.
- tradingview/indicators: Milestone A indicator; tradingview/strategies reserved for later review.
- results/reports and results/charts: generated research artifacts.
- docs: project progress and methodology notes.

Market data and generated results are excluded from Git by default. Keep independent backups of original exports.

## Configuration

config.json uses JSON (no comments). Null means unknown or undecided, not zero. All strategy settings are provisional hypotheses and are not executable until the engine is implemented.

Before real CSV analysis, supply source_timezone and confirm whether timestamps label candle opens or closes. Never assume broker server time is UTC. Ask your broker for its historical server-time and daylight-saving policy; comparing current server time with UTC alone cannot establish historical offsets. Output timestamps will use UTC.

Before monetary position sizing, obtain the broker's XAU/USD symbol specification: contract size, tick size, tick value in account currency, minimum and maximum volume, volume step, account currency, spread units, and commission basis. Unknown fields must block exact sizing. Synthetic specifications will later be explicitly labelled and separate.

Session windows are provisional local-clock definitions, not official market hours. London and New York use daylight-saving-aware IANA zones. Overlaps will receive explicit labels.

Research starts with A (touch), B (close confirmation), and C (close confirmation with H1 alignment), with identical periods, costs, and exit assumptions. Pivot confirmation must be timestamped when known. Confirmation entries are planned for the next bar open; touch orders must already exist before the touched bar. Ambiguous stop/target bars will use stop-first assumptions. These are intended rules, not implemented behavior.

Development/validation/final-test splits are chronological. Final-test execution will require an explicit later action and must remain unused while rules are developed. No parameter search or performance inference has been run.

The optional Maven profile is disabled with all firm-specific limits unset. Personal risk controls are not official firm rules; verify current official terms before configuring a profile.

## Milestone roadmap

2. COMPLETE: MT5 loader, synthetic fixture and data-quality checks (38 offline tests passed).
3. Causal pivots, BOS and zones.
4. Three entry hypotheses.
5. Risk, costs and event-driven backtest.
6. Metrics, charts and chronological validation.
7. Matching Pine v6 indicator and strategy.
8. Signal comparison and documented feed/execution differences.

Each milestone will add and run relevant tests before proceeding. Pine compilation must eventually be verified in TradingView; local file creation alone does not establish compilation.

## Research references (not reviewed in milestone 1)

- Bailey, Borwein, Lopez de Prado and Zhu, The Probability of Backtest Overfitting: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Marcos Lopez de Prado, Advances in Financial Machine Learning.
- Cont, Kukanov and Stoikov, The Price Impact of Order Book Events: https://arxiv.org/abs/1011.6402

These are methodology leads, not proof of this strategy. Equity order-book findings cannot establish hidden orders or profitability from OTC gold candles and tick volume.

## Milestone 2: CSV loading and quality checks

The loader and offline tests are implemented. Use the existing .venv; do not create a second environment. Install missing dependencies with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Try the synthetic demonstration

The committed synthetic_xauusd_m15.csv contains eight invented candles, not real XAU/USD prices. UTC is explicitly chosen only for this fixture.

```powershell
.\.venv\Scripts\python.exe -m src.data_loader --input data/raw/synthetic_xauusd_m15.csv --source-timezone UTC --timeframe 15min
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Expected demo: Data quality: PASS, Rows loaded: 8, no duplicate timestamps, no invalid OHLC candles, zero unobserved interval slots. This checks software behavior only; no trading conclusions follow.

### Export your broker's MT5 candles

In desktop MT5, open Market Watch, right-click and choose Symbols. Select your broker's gold symbol (its name may include a suffix). Open Bars, select M15, choose the date range, Request the history and Export to CSV. Repeat separately for H1 if needed. Keep the original files unchanged and save copies as data/raw/xauusd_m15.csv and data/raw/xauusd_h1.csv. Export completed candles and record the broker, symbol, date range, timezone policy and timestamp convention separately.

Official reference: [MetaTrader 5 Market Watch: downloading price history](https://www.metatrader5.com/en/terminal/help/trading/market_watch). Tick volume counts quote activity; it is not centralized exchange-traded volume. The loader preserves real volume separately when supplied.

### Configure broker time

Edit only the data section in config.json. Set source_timezone to the broker-confirmed IANA timezone, such as Europe/Helsinki ONLY if the broker confirms that historical clock policy. Leave it null while unknown. An unknown source timezone makes naive timestamps FAIL; the loader never assumes UTC. Explicit offsets in timestamps can be used without a source timezone.

Daylight-saving ambiguous or nonexistent wall times are flagged and retained with an unusable internal timestamp. Resolve them from broker records or provide timestamps with explicit UTC offsets. No automatic DST guess is made. raw_timestamp, source_row and the original raw DataFrame retain source evidence.

Set datetime_format when dates are ambiguous: for example %d/%m/%Y %H:%M:%S. Supported automatic dates start with YYYY-MM-DD or YYYY.MM.DD. Set decimal to "," for decimal-comma files (typically separated by semicolons). Delimiter is auto-detected among comma, tab, semicolon and pipe; configure it when detection fails. UTF-8/UTF-8 BOM and UTF-16 BOM are supported; use --encoding for other encodings.

column_mapping maps exact source headers to internal names; for example {"BidOpen": "open"}. Canonical columns are timestamp, open, high, low, close, tick_volume, real_volume and spread. Native MT5 TICKVOL is tick volume and VOL is real volume. A lone Volume is interpreted as tick volume; where Tick Volume and Volume coexist, Volume is real volume. Check broker semantics and override the mapping if necessary. Spread is preserved in the export's units; no point-to-price conversion is assumed.

### Validate real data and save a report

After setting the confirmed source timezone in config.json:

```powershell
.\.venv\Scripts\python.exe -m src.data_loader --input data/raw/xauusd_m15.csv --timeframe 15min
.\.venv\Scripts\python.exe -m src.data_loader --input data/raw/xauusd_h1.csv --timeframe 1h
.\.venv\Scripts\python.exe -m src.data_loader --input data/raw/xauusd_m15.csv --timeframe 15min --report results/reports/xauusd_m15_quality.json
```

Report files refuse overwrite; use a new filename for each run. Input CSVs are never rewritten. Running from the project root loads config.json by default; --config selects another file.

PASS means these structural checks passed, not that history is complete, bar timestamps are correctly labelled, every candle is finished, or the strategy works. WARNING means inspect observations such as absent volumes, sorting, irregular intervals or gaps. FAIL means unusable timestamps, duplicates, missing columns, invalid prices or invalid candle relationships. FAIL exits with code 2; PASS and WARNING exit with code 0. Malformed/empty files produce a clear error and code 2 before a dataset report can be created.

Rows in issues are logical CSV record numbers, with the header as row 1. Loaded records are stably sorted by timestamp; duplicates and invalid records remain present, with invalid timestamps last. load_csv returns candles, raw and report. Numeric conversion failures appear as missing numeric values but original strings remain in raw; source_row links back to them.

The report gives missing-value counts, offending records, UTC range, assumed interval, modal observed interval and five largest time gaps. A missing interval is an unobserved slot relative to the configured interval, including closures. No trading calendar is assumed; gaps are warnings and no missing candle is fabricated. Without a configured interval the missing-slot count is unknown. A modal interval is descriptive, not proof of a timeframe; ties are reported as ambiguous. Override --timeframe for H1 rather than relying on the M15 configuration default.

No resampling, H1 derivation, trading logic, backtesting or Pine code is included in this milestone.

## Gold data acquisition and institutional research

This milestone adds Yahoo futures and CFTC positioning tools, not trading logic. Reuse the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m src.yahoo_data --interval 1h --period 1mo
.\.venv\Scripts\python.exe -m src.yahoo_data --interval 15m --period 1mo
```

GC=F is a Yahoo gold-futures proxy, not broker XAU/USD spot/CFD. Basis, contract rolls, venue hours and feed differences matter; the proxy roll construction has not been independently verified. Provider futures volume is stored as real_volume, never broker tick volume. No missing volume, spread or commission is replaced with zero.

The new acquisition.yahoo configuration is separate from broker data settings. Set symbol, interval, period and source_timezone (fallback for naive provider timestamps only). Broker timezone remains unset. Supported intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo. M15 is 15m; H1 is 1h or 60m.

The [yfinance API reference](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html) states a general 60-day intraday limit. Actual interval retention may vary; requests are attempted and failures reported. Chunking does not restore expired history. Use Yahoo data according to its terms for personal research; this unofficial wrapper provides no completeness guarantee.

Explicit ranges use inclusive start and exclusive end. Choose dates within actual retention; this example is relative to the project review date 2026-10-18:

```powershell
.\.venv\Scripts\python.exe -m src.yahoo_data --interval 15m --start 2026-10-01 --end 2026-10-16
```

Each attempt has a unique filename with symbol, timeframe, source, timestamp and ID. data/raw contains the provider DataFrame response snapshot (not HTTP bytes), normalized candles, and metadata with request/version/hash/timezone. The downloader requests keepna=True, repair=False, auto_adjust=False and ignore_tz=False. It cannot restore records Yahoo itself omitted. Gaps, missing prices and duplicate rows are preserved and reported. Failed downloads record error metadata; no synthetic fallback is used.

Only non-FAIL data get copies under data/processed. Quality JSON reports go to results/reports. PASS/WARNING do not establish trading readiness or full range coverage. All-NaN provider rows, including possible nontrading placeholders, fail the existing strict candle checks; they are not silently discarded. A separate explicit calendar-aware cleaning decision would be needed before using such snapshots.

bar_available_after and bar_complete_at_fetch retain a minimum bar-completion bound. Unfinished bars are warned about and retained; future strategies must exclude them. Daily/calendar bounds are approximate and none of these bounds measure actual vendor latency.

Revalidate the latest H1 snapshot:

```powershell
$goldCsv = Get-ChildItem -LiteralPath data/raw -Filter 'yahoo_GC_F_1h_*_normalized.csv' | Sort-Object LastWriteTime | Select-Object -Last 1
if ($null -eq $goldCsv) { throw 'No H1 snapshot exists; inspect download errors.' }
.\.venv\Scripts\python.exe -m src.data_loader --input $goldCsv.FullName --timeframe 1h
```

The generic CSV validator does not evaluate extra bar-availability columns. Use the acquisition quality report as well.

### CFTC positioning

```powershell
.\.venv\Scripts\python.exe -m src.cot --year 2023 2024 2025
```

The downloader uses official annual Disaggregated Futures Only ZIP archives, default COMEX gold code 088691. Original ZIP bytes and hashes remain in data/raw. Combined CSV source_row references allow tracing processed records to input. Multiple years are combined before features are calculated.

Processed categories include producer/merchant, swap dealer, managed money, other reportable and nonreportable. Net = long - short; separately reported spreading is excluded. Net changes use the preceding observation; historical_percentile is the fraction of strictly previous window values below the current net. Defaults: window 156 reports, minimum 52 prior reports. Warmup remains missing. H05 specifies a stricter 104-report minimum for future tests.

Positions usually describe Tuesday and are released Friday 15:30 America/New_York; holidays and exceptional delays matter. Sources: [CFTC archives](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm), [release schedule](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm).

No Friday release timestamps are guessed. Default available_at is retrieval time, so old reports cannot inform earlier historical decisions. For historical alignment, independently verify ACTUAL publication times and supply a release CSV with as_of_date, available_at (explicit UTC offset), and evidence_url. Do not treat a tentative schedule as verified publication.

```powershell
.\.venv\Scripts\python.exe -m src.cot --year 2023 2024 2025 --release-calendar data/raw/verified_cot_releases.csv
```

The release calendar is snapshotted and hashed. Missing release dates fall back to retrieval time; nonchronological availability is rejected. align_cot uses strict backward as-of joins on actual decision time, excluding exact release instants and observations older than 14 days by default. Pass candle-close decision times when appropriate, not earlier candle-open times. If many reports first become available simultaneously, the latest observation is selected; source archives remain intact.

Finalized archives can contain revisions. Verified release dates alone do NOT make revised values point-in-time correct: a vintage audit is still needed. Weekly categories reveal neither exact trader identity nor orders/stop levels behind intraday candles. The downloader does not bypass rate limits, authentication or access restrictions; failures are logged and should be retried later.

### Evidence and hypotheses

research/sources/catalog.json records nine academic, official and software references with original summaries and explicit access limits. research/hypotheses/register.json defines seven measurable hypotheses, baselines, parameter sets, data requirements, uncertainty methods and rejection criteria. Activate only H01 entry comparisons plus H07 cost stress first; defer other filters.

```powershell
.\.venv\Scripts\python.exe -m src.research --output results/reports/gold_research_review.md
.\.venv\Scripts\python.exe -m src.research --freeze-plan results/reports/research_plan_v1.json
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Reports/plan paths refuse overwrite; choose new names for repeated runs. Plan snapshots freeze definitions only. Add exact data hashes, costs, split dates and code identifier before any future strategy test, and log all attempted configurations including failures to the existing configured parameter registry. No empirical tests of the hypotheses have been run here.

The research renderer is local and reproducible; no restricted-paper scraper is installed. Abstract-only review is labelled explicitly. Automated tests inject mocked provider/archive responses, never use the internet and mark saved mock artifacts synthetic. Short Yahoo intraday history cannot satisfy multi-year out-of-sample requirements. Credible context does not establish profitability of candle-based zones.


### Reuse saved CFTC ZIPs after a network interruption

The original downloaded files remain available. This command selects a saved archive for each requested year and reprocesses it without network access:

```powershell
$cotArchives = foreach ($cotYear in 2023, 2024, 2025) {
    $cotZip = Get-ChildItem -LiteralPath data/raw -Filter "cftc_088691_*_$cotYear.zip" | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($null -eq $cotZip) { throw "Missing saved archive for $cotYear" }
    $cotZip.FullName
}
.\.venv\Scripts\python.exe -m src.cot --year 2023 2024 2025 --local-archives $cotArchives
```

Locally supplied ZIP provenance is labelled unverified by the generic reuse tool; compare hashes with the original downloaded metadata when provenance matters. This milestone's reused ZIP hashes were checked and matched. New filenames prevent overwriting the original evidence.

Latest verified results: 70 offline tests passed; pip check passed. Yahoo returned 584 H1 rows (113 missing-price rows) and 2,335 M15 rows (461 missing-price rows): both FAIL quality, retained without a processed copy. COT processing succeeded for 157 report dates and five categories (785 rows), with WARNING for publication/vintage limitations. No strategy was backtested. Read results/reports/gold_data_milestone_summary.md first; the detailed register report is results/reports/gold_research_review.md.


## TradingView indicator: Milestone A

The complete Pine v6 indicator is [xauusd_sd_detector.pine](tradingview/indicators/xauusd_sd_detector.pine). Read [exact rules, installation, replay checklist and limitations](docs/tradingview_indicator.md).

It draws candidate supply/demand zones, confirmed pivots/BOS/CHoCH, closed-bar BUY/SELL hypotheses, chart-price entry/SL/TP levels and a status table. HTF structure/EMA, freshness/retests, displacement, session, ATR, relative-volume, body-size and distance rules are configurable signal gates. Optional previous-day levels are display-only. Both entry models are close-observed hypotheses: A marks a new touch episode; B requires a strictly later confirmation candle. Neither is an executed trade.

```powershell
Get-Content -LiteralPath .\tradingview\indicators\xauusd_sd_detector.pine -Raw | Set-Clipboard
```

In TradingView, choose your broker's XAU/USD standard 15-minute chart, open Pine Editor, create a new indicator, replace the entire template, paste, Save and Add to chart. Keep Entry timeframe15 and Higher timeframe60 initially. Actual Pine compilation and Bar Replay MUST be verified there; no connected TradingView compiler was available here.

Defaults disable entries on mismatched chart timeframes. On H1 you can view the completed H1 context with default settings but no M15 entries are compressed onto H1 bars. To test H1 entries, change Entry to60 and HTF to240 and log that separate experiment. All alerts are close-gated; choose Once Per Bar Close. Recreate alerts after changing settings.

Research decisions: [traceability register](research/research_to_code.csv), [Pine-specific hypothesis variant](research/hypotheses/pine_milestone_a.json), [future ablation plan](research/pine_ablation_plan.csv), [empty manual validation log](research/pine_validation_runs.csv). Existing research is reused, with explicit indirect-evidence limits; no claim that any filter improved performance. COT access via a supported TradingView library is feasible but not implemented until publication timing/category/revision audits. No order-book/OFI or spread is inferred from OHLCV.

```powershell
.\.venv\Scripts\python.exe -B -m src.pine_audit
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
Get-FileHash -LiteralPath .\tradingview\indicators\xauusd_sd_detector.pine -Algorithm SHA256
```

The audit is a narrow source-safety check, NOT a Pine parser/compiler, runtime test or backtest. Full offline suite: 78 passed. TradingView compilation/runtime: UNVERIFIED. Comparative strategy performance: NOT TESTED. No strategy file, new data download or dependency is added in A. Existing Yahoo/MT5/COT workflows above remain available; none is required by the standalone indicator.

## Historical chart display

Signals are evaluated on all loaded historical closed bars as well as new closed bars. They are not restricted to barstate.islast or realtime. Only the compact table is last-bar-only.

Historical BUY/SELL shapes remain across loaded history. The new default-on historical level plots also preserve blue entry, red stop and green target dots on each signal candle even after old drawing objects are pruned. Use the Data Window to inspect the signal's exact reference prices and planned R.

Retain archived historical zone boxes defaults on, with 80 archived boxes (configurable up to150), in addition to the retained signal-engine zones. Archived boxes are gray and explicitly labelled not monitored; archiving does not add them back to signal or target selection. Oldest archives are pruned at the configured cap. Recent continuous level sets remain capped separately; historical dots are plot series and do not consume line objects.

The status table now counts BUY and SELL signals in the LOADED chart history, not trades, wins or future predictions. A zero count can mean insufficient history, mismatched chart/entry timeframe or no qualifying setups. Use standard M15 XAU/USD with Entry15 and HTF60 for the default configuration. Enabling more historical drawing retention does not weaken filters or invent setups.

Scroll left after adding the script. Loaded history depends on TradingView and account/feed availability; max_bars_back controls series-reference buffers, not a last-1000-bars calculation window. Historical alerts are not replayed as notifications. Use Bar Replay to inspect when each signal became known. Successful TradingView recompilation remains unverified locally.

