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
- Overtrading filter, explanation layer, quality score, multi-market types

### Realized PnL Fix (March 17)
- Paper adapter records PnL on sell trades, resolver uses original strategy_id

### Weather Asymmetric Mode (March 17)
- Separate `weather_asymmetric` strategy: hold to resolution, dedicated UI tab

### Controlled Calibration & Overconfidence Fix (March 17)
- 1.25x global sigma widening, calibration guardrails, Brier score

### Auto-Tuning Framework (March 17)
- Disabled by default, stepwise adjustments, recommendation + apply endpoints

### Resolution Time Visibility (March 17)
- resolves_at, time_left, time_open. Filter/sort by resolution timing

### Position Lifecycle Management (March 17)
- **Lifecycle modes**: OFF, TAG_ONLY (default), SHADOW_EXIT, AUTO_EXIT
- **Exit rules**: Profit capture (2.0x), Negative edge (-100bp), Edge decay (60%), Time inefficiency (18h/300bp)
- **Asymmetric positions NEVER evaluated for exit**
- API: exit-candidates, lifecycle status, positions enrichment
- Frontend: Lifecycle badge, Mult/Edge/Decay/Status columns, Exit filter

### Lifecycle Dashboard Tab (March 17)
- Summary Cards, Exit Reason Distribution, Time Bucket Breakdown
- Shadow Exit Timeline, Would Have Sold vs Held comparison
- Aggregate by Exit Reason cards

### Threshold Simulator (March 17)
- Simulation-only panel with 5 sliders and 3 presets
- Per-reason performance, decision quality, new/removed exits detail

### Lifecycle Mode Control (March 18)
- **Segmented control** with 4 mode buttons (OFF, TAG ONLY, SHADOW, AUTO EXIT)
- **Confirmation modals**: SHADOW_EXIT (amber) and AUTO_EXIT (red with stronger warning)
- **Backend**: POST /api/strategies/weather/lifecycle/mode persists to MongoDB
- **Logging**: Every mode change logged with timestamp and previous → new mode
- **Toast feedback**: Success notification on mode switch
- **Safety**: OFF/TAG_ONLY = direct switch; SHADOW_EXIT/AUTO_EXIT = require confirmation

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/positions/by-strategy | GET | Enriched positions with lifecycle |
| /api/positions/weather/exit-candidates | GET | Exit candidates + config |
| /api/positions/weather/lifecycle | GET | Full lifecycle evaluations |
| /api/positions/weather/lifecycle/dashboard | GET | Dashboard for threshold validation |
| /api/positions/weather/lifecycle/simulate | POST | Simulate with custom thresholds |
| /api/strategies/weather/lifecycle/mode | POST | Switch lifecycle mode |
| /api/strategies/weather/health | GET | Health + lifecycle status |

## Prioritized Backlog
### P0: Observe TAG_ONLY mode, validate exit candidates
### P1: Enable SHADOW_EXIT to collect shadow exit data, evaluate quality
### P2: Copy Trading Skeleton
### P3: Manual Order Entry
### P4: UI toggle for auto-tune sigma multiplier
### P5: Resolution Timeline visualization
### P6: Live Trading Mode Integration
