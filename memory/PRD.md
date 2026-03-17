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
- Migrated 220 historical trades → $142.70 realized PnL

### Weather Asymmetric Mode (March 17)
- Separate `weather_asymmetric` strategy: market_price ≤ 0.25, prob ≥ 0.40, edge ≥ 0.15
- Hold to resolution, separate PnL tracking, dedicated UI tab

### Controlled Calibration & Overconfidence Fix (March 17)
- 1.25x global sigma widening, ±25% calibration cap, 30-sample minimum
- Brier score, calibration curves, sigma evolution, sigma trace in signals

### Auto-Tuning Framework (March 17)
- Disabled by default, stepwise 0.05 adjustments, capped 1.0–1.5x
- Manual/auto_pending/auto modes, recommendation endpoint + apply endpoint

### Weather-by-Type Performance (March 17)
- PnL breakdown by temp/precip/snow/wind, card-based UI

### Resolution Time Visibility (March 17)
- Each weather position includes: resolves_at (UTC timestamp), target_date, time_to_resolution, opened_at, resolution_category
- Date parser: handles "March 17" (no year) and "March 17, 2026" (with year)
- Frontend: Resolves, Time Left, Held columns with human-readable formatting
- Filter by resolution: All / <6h / 6-24h / >24h
- Sort: Resolves soonest / Held longest / Best P&L

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/analytics/summary | GET | Portfolio PnL |
| /api/analytics/weather-by-type | GET | PnL by market type |
| /api/positions/by-strategy | GET | Enriched positions with resolution times |
| /api/strategies/weather/health | GET | Health + sigma_pipeline + auto_tune |
| /api/strategies/weather/calibration/metrics | GET | Brier, coverage, curves |
| /api/strategies/weather/calibration/auto-tune | GET | Auto-tune recommendation |
| /api/strategies/weather/calibration/auto-tune/apply | POST | Apply one step |
| /api/strategies/weather-asymmetric/summary | GET | Asymmetric positions + PnL |

## Prioritized Backlog
### P1: Enable Auto-Tune (when 30+ samples collected)
### P2: Copy Trading Skeleton
### P3: Manual Order Entry
### P4: Live Trading Mode Integration
