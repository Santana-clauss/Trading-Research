# Milestone log

## 1: Scaffold

Inspected an empty workspace; Python and py report 3.14.0. Created directories, dependency bounds, provisional JSON configuration and PowerShell setup instructions. No broker data found. No strategy or data-loader code implemented. No dependency installation or market research performed. JSON and scaffold checks are the applicable verification for this stage; automated behavioral tests begin in milestone 2.

Await user confirmation or setup output before milestone 2.

## 2: CSV loader and validation

Implemented strict CSV parsing, explicit timezone localization, non-destructive reports, a synthetic MT5 fixture and offline tests. No broker history or trading code added. See README for commands and limitations.

Verification: 38 tests passed (pytest, offline); synthetic CLI returned PASS for 8 rows, zero duplicate timestamps, zero invalid OHLC candles and zero unobserved interval slots. Milestone 2 complete; await user confirmation before Milestone 3.

## Historical gold data and institutional research

Added Yahoo futures acquisition, official CFTC ZIP acquisition and offline reuse, causal positioning features/alignment, nine-source evidence catalog, seven defined hypotheses and local report rendering. Extended existing configuration and requirements without replacing the MT5 loader.

Verification: 70 offline tests passed in 10.67s; pip check passed. Real Yahoo H1/M15 downloads succeeded as retrievals but both failed strict OHLC validation (113/584 and 461/2335 missing-price rows). All rows and metadata retained. Downloaded 2023-2025 CFTC archives; handled real date-header variation; reprocessed saved ZIPs after a remote disconnect. Hashes matched original downloads. Processed 157 dates and 785 category records with retrieval-time-only availability and revision warnings.

Reports: results/reports/gold_data_milestone_summary.md and gold_research_review.md. No trading engine or strategy evidence implemented. Await user review.


## Milestone A: Pine v6 entry indicator

Inspected existing project, environment, loader/configuration/tests and empty Pine folders. Implemented standalone tradingview/indicators/xauusd_sd_detector.pine using confirmed pivots, BOS/CHoCH, completed HTF structure/EMA context, objective zones/lifecycle, independent close-observed touch and later-confirmation hypotheses, hypothetical SL/TP/R, optional filters, bounded drawings, table and close-gated alerts.

Added docs/tradingview_indicator.md, research/research_to_code.csv (19 research decisions), pine_reference_sources.json, pine_milestone_a.json, pine_ablation_plan.csv and empty pine_validation_runs.csv. Added a deliberately limited Pine source-safety audit and traceability/timing-guard regression tests. Existing Python data tools/configuration/requirements were retained. No strategy or performance test implemented.

Verification: full offline suite 78 passed in 8.45 seconds; limited source audit passed; pip check reported no broken requirements. Pine SHA256: 663F922C77E1490875F4099780D061B2B6D63DEAB035180A30E1D4907292E914. TradingView compile/runtime/Bar Replay UNVERIFIED because no connected compiler/chart session was available. No research-profitability improvement claimed. Milestone A source implementation delivered; manual TradingView acceptance pending. Stop for user review before B/C.


## Pine correction: CE10150

User supplied TradingView compiler error: text cannot be used as a variable or function name. Renamed the f_note parameter to noteText and the setup label variable to setupText; preserved drawing API text= argument names. Added a limited audit guard plus regression cases for both declarations and permitted named arguments. Full offline suite: 81 passed in 5.77s; source audit passed. Successful TradingView recompilation remains unverified. Previous milestone SHA refers to the original source before this correction.
