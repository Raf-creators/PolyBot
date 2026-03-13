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
- **83/83 tests passed**: `/app/backend/tests/test_phase10_weather_models_parser.py`

## Prioritized Backlog
### P1 — Phase 10 Implementation
- Weather strategy models, pricing, feeds, trader, server integration, dashboard

### P2 — Future
- Volume/liquidity heatmap on Markets page
- CLOB WebSocket for real-time fill updates
- Copy trading skeleton
- Manual order entry
