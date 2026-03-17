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

### Weather Asymmetric Mode (March 17)
- Separate `weather_asymmetric` strategy targeting low-price/high-upside markets, hold to resolution

### Controlled Calibration & Overconfidence Fix (March 17)
- 1.25x global sigma widening, +/-25% calibration cap, 30-sample minimum
- Brier score, calibration curves, sigma evolution, sigma trace

### Auto-Tuning Framework (March 17)
- Disabled by default, stepwise 0.05 adjustments, capped 1.0-1.5x
- Manual/auto_pending/auto modes, recommendation + apply endpoints

### Resolution Time Visibility (March 17)
- resolves_at, time_left, time_open data. Filter by resolution: All/<6h/6-24h/>24h. Sort by time/PnL

### Position Lifecycle Management (March 17)
- **Lifecycle modes**: OFF, TAG_ONLY (default), SHADOW_EXIT, AUTO_EXIT
- **Exit rules** for standard weather only:
  - Profit capture: >= 2.0x price multiple
  - Negative edge: current edge <= -100 bps
  - Edge decay: >= 60% decay from entry edge
  - Time inefficiency: held >= 18h with < 300 bps edge
- **Asymmetric positions NEVER evaluated for exit**
- API: `/api/positions/weather/exit-candidates`, `/api/positions/weather/lifecycle`
- Frontend: Lifecycle badge, Mult/Edge/Decay/Status columns, Exit filter, Best Multiple sort

### Lifecycle Dashboard Tab (March 17)
- Summary Cards (candidates, avg mult, avg edge, avg decay)
- Exit Reason Distribution bars for all 5 reasons
- Resolution Time Breakdown with exit rates
- Shadow Exit Timeline (active in SHADOW_EXIT mode)
- Would Have Sold vs Held comparison with per-position delta
- Aggregate by Exit Reason cards

### Threshold Simulator (March 17)
- **Simulation-only** panel — NO live impact (verified by testing)
- 5 slider controls: profit capture, negative edge, edge decay, time threshold, time min edge
- 3 presets: Conservative (3.0x/-200bp/80%/24h/500bp), Balanced (2.0x default), Aggressive (1.5x/-50bp/40%/12h/200bp)
- Reset to Live button when thresholds modified
- Real-time recalculation via `POST /api/positions/weather/lifecycle/simulate`
- Results: comparison cards (exit candidates delta, good/bad exits, portfolio PnL)
- Per-reason performance breakdown (live vs sim counts, PnL, good/bad exits)
- New/Removed exits detail with position-level data
- Decision quality assessment (% improved outcome, % reduced profit, verdict text)

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/positions/by-strategy | GET | Enriched positions with lifecycle |
| /api/positions/weather/exit-candidates | GET | Exit candidates + config |
| /api/positions/weather/lifecycle | GET | Full lifecycle evaluations |
| /api/positions/weather/lifecycle/dashboard | GET | Dashboard for threshold validation |
| /api/positions/weather/lifecycle/simulate | POST | Simulate exit decisions with custom thresholds |
| /api/strategies/weather/health | GET | Health + lifecycle status |
| /api/strategies/weather/calibration/metrics | GET | Brier, coverage, curves |
| /api/strategies/weather/calibration/auto-tune | GET | Auto-tune recommendation |
| /api/analytics/weather-by-type | GET | PnL by market type |

## Prioritized Backlog
### P0: Validate lifecycle decisions in paper mode, then enable SHADOW_EXIT
### P1: Enable AUTO_EXIT for standard weather after shadow validation
### P2: Copy Trading Skeleton
### P3: Manual Order Entry
### P4: UI toggle for auto-tune sigma multiplier
### P5: Resolution Timeline visualization
### P6: Live Trading Mode Integration
