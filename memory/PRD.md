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
- Position/trade persistence to MongoDB
- Telegram notifications, risk management

### Dashboard Overhaul (Complete)
- Open positions with enriched strategy metadata
- Realized vs Unrealized PnL breakdown

### Weather V2 Strategy (Complete)
- Overtrading filter (min_edge=500bps, min_confidence=0.55, position cap)
- Explanation layer & quality score per signal
- Multi-market types: temperature, precipitation, snowfall, wind
- Celsius market support

### Realized PnL Fix (Complete — March 17, 2026)
- Paper adapter records PnL on sell trades
- Market resolver uses original strategy_id (not "resolver")
- Migration fixed 220 historical trades → Realized PnL: $142.70

### Weather Asymmetric Mode (Complete — March 17, 2026)
- Separate strategy: `weather_asymmetric`
- Filters: market_price ≤ 0.25, model_prob ≥ 0.40, edge ≥ 0.15
- Hold to resolution, no early flip, higher allocation ($5 default)
- Separate PnL tracking, dedicated UI tab

### Controlled Calibration & Overconfidence Fix (Complete — March 17, 2026)
- **1.25x overconfidence multiplier**: All sigma values widened by 25% (temporary)
- **Calibration guardrails**: ±25% cap on adjustments, 30-sample min threshold
- **Brier score**: 1.064 (5 samples), 1σ coverage 40% (model overconfident)
- **Segmentation**: By lead-hours bracket, market type, station
- **Sigma trace**: Full pipeline visibility (default → base → OC-adjusted → final) in signal explanations
- **UI**: Sigma Pipeline section, calibration metrics, calibration curve, sigma evolution

### Performance by Weather Market Type (Complete — March 17, 2026)
- `GET /api/analytics/weather-by-type`: PnL breakdown for temp/precip/snow/wind
- Card-based UI with per-type realized/unrealized PnL, trade counts, win rates

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/analytics/summary | GET | Portfolio PnL, Sharpe |
| /api/analytics/strategies | GET | Per-strategy metrics |
| /api/analytics/strategy-attribution | GET | Deep PnL breakdown |
| /api/analytics/weather-by-type | GET | PnL by market type |
| /api/positions/by-strategy | GET | Enriched positions |
| /api/strategies/weather/health | GET | Weather health + sigma_pipeline |
| /api/strategies/weather/calibration/metrics | GET | Brier, coverage, curves |
| /api/strategies/weather-asymmetric/summary | GET | Asymmetric positions + PnL |
| /api/admin/fix-resolver-trades | POST | Migrate trade strategy_ids |

## Prioritized Backlog

### P1: Auto-Apply Sigma Recommendations
- When calibration matures (≥30 samples), automatically update sigma from calibration data
- Add toggle to enable/disable auto-apply

### P2: Reduce Overconfidence Multiplier
- As data accumulates and coverage approaches 68%, reduce multiplier toward 1.0

### P3: Copy Trading Skeleton
### P4: Manual Order Entry
### P5: Live Trading Mode Integration
