# Polymarket Edge OS — Product Requirements

## Problem Statement
A full-stack Polymarket trading bot (FastAPI + React + MongoDB) that executes paper trades across crypto, weather, and arbitrage strategies. The bot runs on Railway with Telegram notifications and a real-time dashboard.

## Architecture
- **Backend**: FastAPI (port 8001), Motor/MongoDB
- **Frontend**: React (port 3000), Recharts, Shadcn UI
- **DB**: MongoDB (`test_database`)
- **Strategies**: `crypto_sniper`, `weather_trader`, `weather_asymmetric`, `arb_scanner`
- **3rd Party**: Polymarket Gamma/CLOB APIs, Open-Meteo, Telegram

## What's Been Implemented

### Core Infrastructure (Complete)
- Engine with paper trading adapter
- Market discovery, price feeds (Binance WS, Polymarket CLOB WS)
- Position/trade persistence to MongoDB
- Telegram notifications for signals/trades
- Risk management with kill switch

### Phase 1-2: Dashboard Overhaul (Complete)
- `GET /api/positions/by-strategy` — enriched position data
- `GET /api/weather/positions-breakdown` — weather position age/PnL breakdown
- Rewrote Analytics, Weather, Sniper pages for open positions + PnL breakdown

### Weather V2 Features (Complete)
- **Overtrading Filter**: min_edge=500bps, min_confidence=0.55, max_weather_positions cap
- **Explanation Layer**: Human-readable thesis + quality score per signal
- **Multi-Market Types**: Temperature, precipitation, snowfall, wind markets

### Realized PnL Fix (Complete — March 17, 2026)
- **Paper adapter** now sets `pnl` on sell trades: `(fill_price - avg_cost) * size`
- **Market resolver** uses original position's `strategy_id` instead of "resolver"
- **Migration endpoint** `POST /api/admin/fix-resolver-trades` — retroactively fixed 220 trades
- **Result**: Realized PnL went from $0 to $142.70 across all strategies

### Weather Asymmetric Mode (Complete — March 17, 2026)
- Separate strategy mode: `weather_asymmetric`
- Filters: market_price ≤ 0.25, model_prob ≥ 0.40, edge ≥ 0.15
- Hold to resolution, no early flip
- Higher allocation: $5 default size, 0.35 Kelly scale
- Separate PnL tracking and UI tab
- `GET /api/strategies/weather-asymmetric/summary`

### Calibration & Self-Improvement (Complete — March 17, 2026)
- **Brier Score**: Measures sigma calibration accuracy (current: 1.06)
- **1σ Coverage**: 40% (ideal 68.3%) — model is overconfident
- **Segmented by**: lead-hours bracket, market type, station
- **Calibration curve**: Predicted sigma vs actual error visualization
- **Sigma evolution**: Time-ordered tracking of z-scores
- **Sigma recommendations**: Per-bracket adjustment suggestions
- `GET /api/strategies/weather/calibration/metrics`

## Prioritized Backlog

### P1: Track Performance by Weather Market Type
- Backend + frontend PnL breakdown by temp/precip/snow/wind

### P2: Apply Sigma Recommendations Automatically
- Use calibration metrics to auto-adjust sigma values
- Dynamic sigma update during scan loop based on recent calibration

### P3: Copy Trading Skeleton
### P4: Manual Order Entry
### P5: Live Trading Mode Integration

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/analytics/summary | GET | Portfolio-level PnL, win rate, Sharpe |
| /api/analytics/strategies | GET | Per-strategy trade metrics |
| /api/analytics/strategy-attribution | GET | Deep per-strategy PnL breakdown |
| /api/positions/by-strategy | GET | Open positions enriched |
| /api/strategies/weather-asymmetric/summary | GET | Asymmetric positions + PnL |
| /api/strategies/weather/calibration/metrics | GET | Brier score, calibration curves |
| /api/admin/fix-resolver-trades | POST | Migrate resolver trade strategy_ids |

## Key DB Collections
- **trades**: All trade records (buy/sell) with pnl, strategy_id
- **positions_snapshots**: Periodic position snapshots
- **configs**: Engine configuration (`_id: "engine_config"`)
- **forecast_accuracy**: Resolved forecast vs actual data
- **weather_rolling_calibration**: Rolling sigma calibration per station
