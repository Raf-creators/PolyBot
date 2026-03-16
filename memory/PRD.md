# Polymarket Edge OS — PRD

## Problem Statement
Build a production-grade 24/7 automated trading platform for Polymarket markets.

## Architecture
- Frontend: React SPA, zustand, single global WebSocket, dark-mode terminal
- Backend: FastAPI async Python, MongoDB
- Execution: Dual adapter — PaperAdapter (default) + LiveAdapter (py-clob-client)

## Implemented Phases

### Phase 1-3 — Engine, Feeds, Arb Strategy
### Phase 4 — Dashboard (AUDITED)
### Phase 5A — Crypto Sniper Strategy (AUDITED)
### Phase 5B — Sniper Dashboard
### P&L Curve + Trade Ticker
### Phase 6 — Telegram Alerts (Configured + Noise Reduced, 2026-03-16)
- Credentials set in `backend/.env`, auto-enabled on startup
- Only TRADE EXECUTED and TRADE CLOSED sent to Telegram
- Removed: signals, weather alerts, risk, system events, scanner noise
- Weather alerts still stored in-memory + logged, not dispatched to Telegram
### Phase 7 — Config Persistence (MongoDB)
### Phase 8 — Live Polymarket Execution Adapter
### Phase 8A — Order Lifecycle, Partial Fills, Wallet Visibility
### Phase 8B — Final Live Trading Safeguards (2026-03-13)

### Phase 9 — Rich Analytics & Strategy Performance Dashboard (2026-03-13)
- **Backend analytics service** (`/app/backend/services/analytics_service.py`): Pure computation layer computing portfolio summary, per-strategy metrics, execution quality, and time-series analytics from in-memory trade state.
- **4 API endpoints**:
  - `GET /api/analytics/summary` — Total PnL, realized/unrealized, drawdown, win rate, profit factor, Sharpe, expectancy, streaks, fees, volume
  - `GET /api/analytics/strategies` — Per-strategy (arb_scanner, crypto_sniper) breakdown with same metrics + avg edge in bps
  - `GET /api/analytics/execution-quality` — Fill ratio, slippage, rejection reasons, latency, partial fills
  - `GET /api/analytics/timeseries` — Daily PnL, equity curve, drawdown curve, trade frequency, rolling 7D/30D PnL, executions by strategy
- **Frontend Analytics page** (`/analytics`): 4-tab dashboard (Overview, Strategies, Execution, Charts) with recharts visualizations
- **Bug fixed**: `compute_timeseries` empty-state return had mismatched keys (`rolling_7d` vs `rolling_7d_pnl`) and missing `drawdown_curve`/`executions_by_strategy`
- **Test endpoints**: `POST /api/test/inject-trades` and `POST /api/test/clear-trades` for populating synthetic data
- Testing: **17/17 backend (100%), all frontend UI tests passed**

## Order Lifecycle States
```
submitted        → Order sent to CLOB, awaiting match
open             → Order live on book
partially_filled → Some shares matched, order still active
filled           → All shares matched, complete
cancelled        → Cancelled (manual, system, or offline)
rejected         → Rejected (preflight, risk, slippage, CLOB error)
expired          → Expired on CLOB
```

## Safety Protections
1. POLYMARKET_PRIVATE_KEY required for live mode
2. Kill switch blocks live mode switch
3. Preflight: auth + mode + kill switch + size cap + slippage
4. Conservative LIVE_DEFAULTS: max_order=2, max_position=5, max_exposure=20
5. Risk engine gates ALL orders
6. Partial fills tracked (never treated as complete)
7. Slippage protection: rejects orders > max_live_slippage_bps
8. Cancel support for open/partial orders
9. Paper fallback if live adapter loses auth
10. Errors tracked and surfaced in health

## Remaining Before Real-Money Launch
- ~~Full CLOB WebSocket fill notifications (currently polling 5s)~~ ✓ Done (P6)
- Multi-wallet support
- Rate limit awareness for CLOB API
- Manual order entry (for ad-hoc trades)

## Phase 10 — Weather Trading Strategy
### Architecture (Complete, 2026-03-13)
- Full architecture designed: `/app/memory/PHASE10_WEATHER_ARCHITECTURE.md`

### Step 1 — Models (Complete, 2026-03-13)
- `weather_models.py`: WeatherConfig, StationInfo, StationType, Season, TempBucket, WeatherMarketClassification, ForecastSnapshot, SigmaCalibration, BucketProbability, WeatherSignal, WeatherExecution, WeatherSignalStatus
- All follow existing conventions (Pydantic BaseModel, new_id, utc_now)
- Multi-outcome bucket support (5-7 buckets per market vs binary)

### Step 2 — Station Registry + Market Parser (Complete, 2026-03-13)
- `weather_parser.py`: STATION_REGISTRY (8 stations), lookup_station(), classify_weather_market(), parse_temp_buckets(), validate_buckets()
- Regex city/date extraction with alias fallback
- Bucket parsing: "X or below", "X-Y F", "X or higher", degree symbols, en-dashes
- Clean rejection reasons for all failure paths
- Contiguous bucket coverage validation (gap + overlap detection)
- **85/85 tests passed**: `/app/backend/tests/test_phase10_weather_models_parser.py`

### Step 3 — Pricing Engine (Complete, 2026-03-13)
- `weather_pricing.py`: normal_cdf, calibrate_sigma, compute_bucket_probability, compute_all_bucket_probabilities, compute_edge_bps, evaluate_all_buckets, kelly_size, compute_weather_confidence, blend_forecasts
- Distribution-based bucket probabilities with continuity correction (±0.5F)
- Sigma calibration by lead time (5 brackets), season (4), station type (coastal/inland)
- Probability normalization enforced (sum = 1.0)
- Quarter-Kelly sizing with floor/ceiling guards
- Multi-source forecast blending with inter-model disagreement inflation
- **63/63 tests passed**: `/app/backend/tests/test_phase10_weather_pricing.py`

### Step 4 — Weather Feeds (Complete, 2026-03-13)
- `weather_feeds.py`: WeatherFeedManager with Open-Meteo (primary) + NWS METAR (secondary)
- Forecast caching with configurable TTL, staleness detection, eviction
- Open-Meteo: hourly temp fetch → daily high extraction → ForecastSnapshot
- NWS: METAR observation fetch → C→F conversion
- Graceful failure handling (HTTP errors, network errors, malformed responses)
- Health/observability dict for monitoring
- Bulk fetch with rate limiting (5 req/sec)
- **27/27 tests passed**: `/app/backend/tests/test_phase10_weather_feeds.py`

### Step 5 — Weather Trader Strategy (Complete, 2026-03-13)
- `weather_trader.py`: WeatherTrader(BaseStrategy) with 5-stage scan loop
- Classification from StateManager markets (multi-outcome weather detection)
- Forecast ingestion via WeatherFeedManager (Stage 2)
- Bucket probability modeling via pricing engine (Stage 3)
- EV evaluation + multi-filter pipeline (Stage 4): edge, liquidity, confidence, lead time, sigma, freshness, cooldown, kill switch, concurrency
- Execution via RiskEngine → ExecutionEngine → fill tracking via EventBus
- Full metrics tracking: scans, classifications, forecasts, rejections by reason, executions, fills
- **21/21 tests passed**: `/app/backend/tests/test_phase10_weather_trader.py`

### Step 6 — Server Integration (Complete, 2026-03-13)
- Strategy registration in engine startup (`server.py`)
- Config persistence: `build_snapshot` / `apply_to_engine` in ConfigService
- Granular config update via `PUT /api/config` for `weather_trader`
- 7 API endpoints: signals, executions, health, config, forecasts, stations, inject-test
- **7/7 API tests passed**: `/app/backend/tests/test_phase10_weather_api.py`

### Step 7 — Weather Dashboard (Complete, 2026-03-13)
- `/weather` page with dark terminal style matching existing dashboard
- 7 stat cards: Markets, Tradable, Rejected, Executed, Filled, Forecasts, Scan Latency
- 5 tabs: Signals, Rejected, Executions, Forecasts, Health
- Health tab: 6 sections (Calibration status with default NWS MOS sigma table, Scanner Metrics, Feed Health, Rejection Reasons, Strategy Config, Classified Markets)
- Empty states render safely when engine idle
- CloudSun icon in sidebar nav between Sniper and Positions
- Spread-sum validation added to trader (max_spread_sum config)
- Calibration status exposed in health API (using_defaults, calibrated_stations, note)

### Step 8 — Full Integration Testing (Complete, 2026-03-13)
- Testing agent: 26/26 backend + all frontend UI tests passed (100%)
- All 7 weather API endpoints verified (correct response shapes)
- No regression: all existing pages and APIs working
- Empty states validated across all tabs
- `/app/test_reports/iteration_16.json`

### Phase 10A — Paper-Mode Validation (Complete, 2026-03-13)
- Full report: `/app/memory/PHASE10A_VALIDATION_REPORT.md`
- Ran against live Polymarket Gamma API + Open-Meteo
- 135 markets discovered, 15 events classified, 15/15 forecasts fetched
- 50 tradable signals generated, 10 paper executions, 10 fills (100%)
- Rejection breakdown: stale_market 84%, edge 13.4%, risk 1.4%, max_buckets 1.1%
- Zero parser errors, zero Open-Meteo errors, zero crashes
- **Architecture fix applied:** Adapted to Polymarket's event-based binary market structure
- **Verdict: READY for cautious shadow-mode testing**

### Demo Mode (Complete, 2026-03-13)
- Safe, isolated demo data system for dashboard preview
- Backend: `DemoDataService` generates realistic 7-day trading history in-memory (no MongoDB)
- Frontend: Toggle on Settings page, localStorage persistence, DEMO MODE badge in TopBar
- Generates: ~200 trades, ~13 positions, equity curve $4K->$14.7K with drawdowns
- All 3 strategies populated (ArbScanner, CryptoSniper, WeatherTrader)
- Separate `/api/demo/*` endpoints — zero modification to real trading logic
- Engine controls disabled in demo mode
- Regenerate button for new randomized data
- Testing: 23/23 backend + all frontend tests passed (100%)
- `/app/test_reports/iteration_17.json`

## Prioritized Backlog
### P0 — Shadow-Mode Testing (Complete, 2026-03-14)
- Shadow config overrides: min_edge=500bps, kelly=0.15, max_stale=600s, cooldown=2400s, max_concurrent=4
- Forecast accuracy service: MongoDB `forecast_accuracy` collection, records forecasts on every scan, manual resolution endpoint
- Calibration visibility: Calibration tab on Weather page with shadow summary, calibration health, per-station accuracy, accuracy log
- New endpoints: `/api/strategies/weather/shadow-summary`, `/shadow/enable`, `/shadow/reset`, `/accuracy/history`, `/accuracy/calibration`, `/accuracy/unresolved`, `/accuracy/resolve`
- Live run results: 25 markets classified, 18 signals generated (500bps+ threshold), 4 shadow executions filled
- 30 forecast accuracy records collected (1 resolved: KLGA forecast=47.3F actual=43F error=-4.3F)
- Testing: 30/30 backend + all frontend tests passed (100%)
- `/app/test_reports/iteration_18.json`

### P1 — Historical Calibration Bootstrap (Complete, 2026-03-15)
- Fetched 90 days of historical forecast vs observed data from Open-Meteo APIs
- Computed empirical sigma per station: KLGA 2.78F, KORD 1.83F, KATL 2.15F, KDFW 2.05F, KMIA 1.23F (0-24h)
- Lead-time scaling: sigma grows ~sqrt(lead_days), from 0-24h to 120-168h
- Seasonal factors computed (winter/spring/summer/fall)
- Stored in MongoDB `weather_sigma_calibration` (5 stations, 91 samples each)
- WeatherTrader auto-loads calibrations on engine start; replaces default NWS MOS table
- API: `/calibration/run`, `/calibration/status`, `/calibration/{station_id}`, `/calibration/reload`
- Weather page: Sigma Calibration section with Run/Reload buttons, Calibrated Sigma Values per station
- Testing: 22/22 backend + all frontend passed (100%) — `/app/test_reports/iteration_19.json`

### P2 — CLOB WebSocket Integration (Complete, 2026-03-15)
- Real-time market data via `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- ClobWebSocketClient: auto-connect, heartbeat/ping, exponential backoff reconnect
- WeatherTrader auto-subscribes discovered token IDs (265 tokens from 5 cities)
- Results: 5108 messages, 4990 price updates, 102 book updates, 5 trades — zero stale_market rejections
- Health endpoint: `/api/health/clob-ws` + integrated into weather health
- Weather Health tab shows CLOB WebSocket card with live metrics
- Polling fallback preserved (MarketDataFeed unchanged)
- Testing: 30/30 backend + all frontend passed (100%) — `/app/test_reports/iteration_20.json`

### P3 — Real-time Weather Signal Alerting (Complete, 2026-03-15)
- **WeatherAlertService** (`/app/backend/services/weather_alert_service.py`): Detects 5 alert types from CLOB WS data stream
  - `PRICE_MOVE`: Large price changes (>300bps default)
  - `EDGE_CHANGE`: Significant edge shifts (>200bps default)
  - `BECAME_TRADABLE`: Market crossing tradability threshold
  - `NO_LONGER_TRADABLE`: Market falling below tradability
  - `SPREAD_DEVIATION`: Bucket spread-sum approaching rejection threshold
- **Spam control**: Per-market debounce with configurable cooldown (default 300s per alert_key = type:station:date:bucket)
- **Config**: 4 new `WeatherConfig` fields persisted via existing MongoDB config system
  - `weather_alerts_enabled` (bool, default true), `min_weather_alert_edge_bps` (200), `min_weather_alert_price_move_bps` (300), `weather_alert_cooldown_seconds` (300)
- **Telegram**: Formatted messages via existing `TelegramNotifier.send_message()` (fire-and-forget)
- **API**: `GET /api/strategies/weather/alerts` returns `{alerts: [], stats: {...}}`
- **Dashboard**: "Alerts" tab on Weather page with stats bar, alert feed, type badges, and empty state
- **Settings**: Weather Trader config section with ON/OFF toggle for alerts, editable threshold fields
- **No changes** to core trading logic, execution behavior, or risk engine
- Testing: 22/22 backend API + all frontend UI passed (100%) + 15/15 unit tests — `/app/test_reports/iteration_21.json`

### P4 — Rolling Calibration System (Complete, 2026-03-15)
- **RollingCalibrationService** (`/app/backend/services/rolling_calibration_service.py`): Aggregates resolved `forecast_accuracy` records by station + lead-time bracket + season to compute rolling sigma values and bias estimates
- **Tri-level calibration priority**: rolling_live > historical_bootstrap > default_sigma_table
  - WeatherTrader loads historical calibrations first, then overlays rolling calibrations for stations with sufficient data
  - Each station's calibration source is tracked and reported in health endpoint
- **Minimum sample safety**: Requires `rolling_min_samples` (default 15) resolved records per station before producing a rolling calibration. Falls back to historical/default when sparse
- **Recalculation policy** (configurable, whichever fires first):
  - Time-based: every `rolling_recalc_interval_hours` (default 168h = weekly)
  - Record-count-based: after `rolling_recalc_after_n_records` (default 20) new resolved records
- **Bias tracking**: Per-station, per-lead-bracket, per-season mean forecast error tracked and exposed
- **Config**: 4 new `WeatherConfig` fields: `rolling_calibration_enabled` (bool), `rolling_min_samples` (15), `rolling_recalc_interval_hours` (168), `rolling_recalc_after_n_records` (20)
- **Storage**: `weather_rolling_calibration` MongoDB collection (separate from raw forecast_accuracy and historical bootstrap)
- **API endpoints**:
  - `GET /api/strategies/weather/calibration/rolling/status`
  - `POST /api/strategies/weather/calibration/rolling/run`
  - `POST /api/strategies/weather/calibration/rolling/reload`
- **Dashboard**: 
  - Calibration tab: "Rolling Live Calibration" section with stats, per-station bias/sigma details, Run Now/Reload buttons
  - Health tab: Dynamic "Calibration Source" card showing active source badge, station counts, source breakdown
  - Strategy Config: Shows rolling calibration settings
- **Settings**: Rolling calibration toggle and numeric threshold fields
- Testing: 31/31 backend API + all frontend UI passed (100%) + 8/8 unit tests — `/app/test_reports/iteration_22.json`

### P5 — Volume/Liquidity Heatmap (Complete, 2026-03-15)
- **LiquidityService** (`/app/backend/services/liquidity_service.py`): Per-token and per-event liquidity scoring (0-100)
  - Score formula: spread width (40%), orderbook depth (30%), 24h volume (30%)
  - Reference normalization: REF_SPREAD=4c, REF_DEPTH=$1000, REF_VOLUME=$5000
- **Heatmap API**: `GET /api/markets/liquidity-heatmap` aggregates weather market tiles by condition_id (city+date), with per-bucket scores and summary stats
- **Scores API**: `GET /api/markets/liquidity-scores` returns `{token_id: score}` for all tracked markets
- **Strategy awareness**: WeatherTrader refreshes liquidity scores each scan cycle via `refresh_liquidity_scores()`
- **Liquidity threshold filter**: `min_liquidity_score` config (default 35) rejects markets scoring below threshold with `liquidity_too_low` reason. Exposed in health metrics. 0 disables.
- **Markets page**: Complete rewrite with dual-tab layout:
  - "Liquidity Heatmap" tab: city-grouped tiles with color-coded score badges (DRY/SPARSE/THIN/MODERATE/GOOD/DEEP), mini bucket bars, click-to-detail dialog
  - "All Markets" tab: existing searchable market table
- **Detail dialog**: Per-bucket breakdown showing mid price, spread, liquidity, and individual scores
- **Signals table**: Shows `Liq` column with color-coded liquidity score per signal
- **Rejected signals**: `liquidity_too_low` rejections highlighted in orange
- Testing: 20/20 backend API + all frontend UI tests (100%) + 12/12 liquidity unit tests + 3 rejection threshold tests — `/app/test_reports/iteration_23.json`

### P6 — CLOB WebSocket Fill Updates (Complete, 2026-03-16)
- **ClobFillWsClient** (`/app/backend/engine/clob_fill_ws.py`): WebSocket client for Polymarket CLOB user/trade channel
  - Connects to `wss://ws-subscriptions-clob.polymarket.com/ws/user` with API credentials
  - Processes trade events: MATCHED, MINED, CONFIRMED, FAILED
  - Heartbeat ping (10s), exponential backoff reconnect (2s base, 60s max)
  - Market subscription management (subscribe/unsubscribe condition_ids)
  - Graceful degradation: no credentials → not connected, no errors, system falls back to polling
- **LiveAdapter integration** (`/app/backend/engine/live_adapter.py`):
  - `set_fill_ws()` + `on_ws_fill()` callback for real-time fill processing
  - Fill delta computation, position/trade updates, EventBus emission
  - Dual fill method: `websocket+polling` when WS connected, `polling` when not
  - Reduced polling interval when WS active (30s vs 5s)
  - ws_fill_count / poll_fill_count tracking for observability
- **ExecutionEngine** (`/app/backend/engine/execution.py`): `live_adapter_status` property exposes fill_ws_health, fill_update_method
- **WeatherTrader**: Receives fill events via EventBus ORDER_UPDATE — works with both WS and polling sources
- **API endpoints**:
  - `GET /api/health/fill-ws` — Full health: connected, has_credentials, trade_events, confirmed_fills, etc.
  - `GET /api/status` — stats.health includes fill_ws_connected, fill_ws_has_credentials, fill_ws_health, fill_update_method
  - `GET /api/execution/status` — live_adapter includes fill_ws_health, fill_update_method, poll_interval_seconds
- **WebSocket broadcast**: Includes fill WS health data in every snapshot (2s interval)
- **Frontend Overview page**: System Status shows "Fill Updates: polling" and "Fill WS: no credentials/connected/disconnected"
- Testing: 29/29 backend API + all frontend UI passed (100%) — `/app/test_reports/iteration_24.json`

### P7 — Global Analytics Dashboard (Complete, 2026-03-16)
- **GlobalAnalyticsService** (`/app/backend/services/global_analytics_service.py`): Aggregates shadow-mode strategy quality metrics
  - Strategy performance: signals, executions, fills, win rate, PnL, per-strategy breakdown (weather, arb, sniper)
  - Forecast quality: global MAE/bias, error distribution histogram, per-station metrics from MongoDB forecast_accuracy
  - Liquidity insights: avg/min/max liquidity scores, rejection breakdown with percentages
  - Timeseries: cumulative PnL curve, daily PnL, signal frequency by strategy
- **API endpoint**: `GET /api/analytics/global` — returns full report with 4 sections
- **Frontend**: `/global-analytics` page with 4 tabs:
  - Performance: 6 stat cards + aggregate performance + per-strategy cards (weather, arb, sniper)
  - Forecast Quality: MAE/bias/calibration stat cards + error distribution histogram (color-coded: green <=2F, yellow <=4F, red >4F) + station metrics table
  - Liquidity: score cards + rejection breakdown with progress bars + horizontal bar chart
  - Charts: cumulative PnL area chart + daily P&L bar chart + stacked signal frequency chart
- **Navigation**: Globe icon in sidebar between Analytics and Risk
- Testing: 25/25 backend + 100% frontend passed — `/app/test_reports/iteration_25.json`

### P8 — Automated Forecast Resolution (Complete, 2026-03-16)
- **AutoResolverService** (`/app/backend/services/auto_resolver_service.py`):
  - Background job: first pass 30s after startup, then every 6h (configurable via `AUTO_RESOLVER_INTERVAL_HOURS`)
  - Scans `forecast_accuracy` for unresolved records whose target_date <= yesterday (UTC)
  - Groups by station → batch-fetches observed daily highs from Open-Meteo Archive API
  - Resolves via existing `ForecastAccuracyService.resolve_forecast()` (computes error, abs_error, marks resolved)
  - Triggers `RollingCalibrationService.run_rolling_calibration()` after resolving new records
  - Safety: never overwrites resolved records, never fabricates data, graceful on API errors
  - Rate-limited: 0.5s between station API calls
- **Results on first run**: 9 records auto-resolved across 5 stations (KATL, KDFW, KLGA, KMIA, KORD)
  - Global MAE improved from 4.3F → 1.7F
  - Global Bias improved from -4.3F → -0.1F
  - Error distribution now spans 9 bins (was 1)
- **API endpoints**:
  - `GET /api/health/auto-resolver` — health with running, interval, total_runs, pending_records, etc.
  - `POST /api/auto-resolver/run` — manual trigger, returns {resolved, pending, skipped, errors}
  - Weather health (`/api/strategies/weather/health`) now includes `auto_resolver` object
  - Global analytics (`/api/analytics/global`) now includes `auto_resolver` object
- **Frontend**: Forecast Quality tab in Global Analytics shows Auto-Resolver section with status, interval, run counts, pending
- Testing: 22/22 backend + 100% frontend passed — `/app/test_reports/iteration_26.json`

### P9 — Future
- Copy trading skeleton
- Manual order entry
