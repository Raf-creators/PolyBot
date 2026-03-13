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
### Phase 6 — Telegram Alerts
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
- Full CLOB WebSocket fill notifications (currently polling 5s)
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

## Prioritized Backlog
### P1 — Phase 10 Implementation
- Weather strategy models, pricing, feeds, trader, server integration, dashboard

### P2 — Future
- Volume/liquidity heatmap on Markets page
- CLOB WebSocket for real-time fill updates
- Copy trading skeleton
- Manual order entry
