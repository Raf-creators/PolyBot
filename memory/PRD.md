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
- Position/trade persistence to MongoDB, Telegram notifications, risk management

### Dashboard Overhaul
- Open positions with enriched strategy metadata
- Realized vs Unrealized PnL breakdown

### Weather V2 Strategy
- Overtrading filter, explanation layer, quality score
- Multi-market types: temperature, precipitation, snowfall, wind
- Celsius market support

### Realized PnL Fix (March 17)
- Paper adapter records PnL on sell trades, resolver uses original strategy_id
- Migration fixed 220 historical trades → Realized PnL: $142.70

### Weather Asymmetric Mode (March 17)
- Separate `weather_asymmetric` strategy: market_price ≤ 0.25, prob ≥ 0.40, edge ≥ 0.15
- Hold to resolution, higher allocation, separate PnL, dedicated UI tab

### Controlled Calibration & Overconfidence Fix (March 17)
- 1.25x global sigma widening (temporary, configurable)
- ±25% calibration adjustment cap, 30-sample minimum threshold
- Brier score, 1σ/2σ coverage, calibration curves, sigma evolution
- Full sigma trace pipeline in signal explanations
- Fixed non-temp sigma table bracket format mismatch

### Auto-Tuning Framework (March 17)
- Disabled by default (`auto_tune_enabled=false`)
- Computes recommended multiplier from coverage vs 68.27% target
- Stepwise adjustments: 0.05 max change per step, capped 1.0-1.5x
- Three modes: manual (operator), auto_pending (enabled but waiting), auto (active)
- `GET /api/strategies/weather/calibration/auto-tune` — recommendation endpoint
- `POST /api/strategies/weather/calibration/auto-tune/apply` — apply one step
- UI: Split layout showing Current State vs Auto-Tune Recommendation

### Performance by Weather Market Type (March 17)
- `GET /api/analytics/weather-by-type` — PnL breakdown by temp/precip/snow/wind
- Card-based UI with color-coded type cards

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/analytics/summary | GET | Portfolio PnL |
| /api/analytics/strategies | GET | Per-strategy metrics |
| /api/analytics/strategy-attribution | GET | Deep PnL breakdown |
| /api/analytics/weather-by-type | GET | PnL by market type |
| /api/strategies/weather/health | GET | Weather health + sigma_pipeline + auto_tune |
| /api/strategies/weather/calibration/metrics | GET | Brier, coverage, curves |
| /api/strategies/weather/calibration/auto-tune | GET | Auto-tune recommendation |
| /api/strategies/weather/calibration/auto-tune/apply | POST | Apply one step |
| /api/strategies/weather-asymmetric/summary | GET | Asymmetric positions + PnL |

## Prioritized Backlog
### P1: Enable Auto-Tune (when 30+ samples collected)
### P2: Copy Trading Skeleton
### P3: Manual Order Entry
### P4: Live Trading Mode Integration
