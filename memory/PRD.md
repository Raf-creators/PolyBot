# Polymarket Edge OS — Product Requirements

## Problem Statement
A full-stack Polymarket trading bot (FastAPI + React + MongoDB) that executes paper trades across crypto, weather, and arbitrage strategies with real-time dashboards.

## Architecture
- **Backend**: FastAPI (port 8001), Motor/MongoDB
- **Frontend**: React (port 3000), Shadcn UI
- **DB**: MongoDB (`test_database`)
- **Strategies**: `crypto_sniper`, `weather_trader`, `weather_asymmetric`, `arb_scanner`
- **3rd Party**: Polymarket Gamma/CLOB APIs, Open-Meteo, Telegram

## Completed Work

### Core Infrastructure
- Engine with paper trading adapter, market discovery, price feeds
- Position/trade persistence, Telegram notifications, risk management

### Dashboard Overhaul
- Open positions with enriched strategy metadata, Realized vs Unrealized PnL breakdown

### Weather V2 Strategy
- Overtrading filter, explanation layer, quality score, multi-market types (temp/precip/snow/wind)

### Realized PnL Fix (March 17)
- Paper adapter records PnL on sell trades, resolver uses original strategy_id
- Migrated 220 historical trades

### Weather Asymmetric Mode (March 17)
- Separate `weather_asymmetric` strategy: market_price <= 0.25, prob >= 0.40, edge >= 0.15
- Hold to resolution, separate PnL tracking, dedicated UI tab

### Controlled Calibration & Overconfidence Fix (March 17)
- 1.25x global sigma widening, +/-25% calibration cap, 30-sample minimum
- Brier score, calibration curves, sigma evolution, sigma trace in signals

### Auto-Tuning Framework (March 17)
- Disabled by default, stepwise 0.05 adjustments, capped 1.0-1.5x
- Manual/auto_pending/auto modes, recommendation endpoint + apply endpoint

### Weather-by-Type Performance (March 17)
- PnL breakdown by temp/precip/snow/wind, card-based UI

### Resolution Time Visibility (March 17)
- Each weather position includes: resolves_at, target_date, time_to_resolution, opened_at, resolution_category
- Filter by resolution: All / <6h / 6-24h / >24h, Sort: Resolves soonest / Held longest / Best P&L

### Position Lifecycle Management (March 17)
- **Lifecycle modes**: OFF, TAG_ONLY (default), SHADOW_EXIT, AUTO_EXIT
- **Exit rules** for standard weather only:
  - Profit capture: >= 2.0x price multiple
  - Negative edge: current edge <= -100 bps
  - Edge decay: >= 60% decay from entry edge
  - Time inefficiency: held >= 18h with < 300 bps edge
- **Asymmetric positions NEVER evaluated for exit**
- Backend: `_evaluate_position_lifecycle()` runs every scan
- API: `/api/positions/weather/exit-candidates`, `/api/positions/weather/lifecycle`
- Frontend: Lifecycle badge, Mult/Edge/Decay/Status columns, Exit filter, Best Multiple sort

### Lifecycle Dashboard Tab (March 17)
- **Summary Cards**: Total candidates, avg profit multiple, avg current edge, avg edge decay
- **Exit Reason Distribution**: Visual bars for all 5 exit reasons with counts and avg metrics
- **Resolution Time Breakdown**: <6h / 6-24h / >24h / unknown with position counts, exit rates, avg multiples
- **Price Multiple Distribution**: Histogram across 6 ranges (<0.5x to >2.0x)
- **Shadow Exit Timeline**: Table for simulated exit records (active in SHADOW_EXIT mode)
- **Would Have Sold vs Held**: Per-position comparison of simulated exit PnL vs held PnL with delta and verdict
- **Aggregate by Exit Reason**: Per-reason Sim Exit / Held / Delta comparison cards
- Backend: `/api/positions/weather/lifecycle/dashboard` endpoint with `get_lifecycle_dashboard()` method
- First-flagged snapshot tracking (`_exit_candidate_snapshots`) for persistent comparison

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/positions/by-strategy | GET | Enriched positions with lifecycle |
| /api/positions/weather/exit-candidates | GET | Exit candidates + config |
| /api/positions/weather/lifecycle | GET | Full lifecycle evaluations |
| /api/positions/weather/lifecycle/dashboard | GET | Dashboard for threshold validation |
| /api/strategies/weather/health | GET | Health + lifecycle status |
| /api/strategies/weather/calibration/metrics | GET | Brier, coverage, curves |
| /api/strategies/weather/calibration/auto-tune | GET | Auto-tune recommendation |
| /api/analytics/weather-by-type | GET | PnL by market type |

## Prioritized Backlog
### P0: Validate lifecycle decisions in paper mode (observe exit candidates, tune thresholds)
### P1: Enable SHADOW_EXIT mode, then AUTO_EXIT after validation
### P2: Copy Trading Skeleton
### P3: Manual Order Entry
### P4: UI toggle for auto-tune sigma multiplier
### P5: Resolution Timeline visualization
### P6: Live Trading Mode Integration
