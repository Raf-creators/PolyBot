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

### Weather V2 Strategy
- Overtrading filter, explanation layer, quality score, multi-market types

### Realized PnL Fix, Asymmetric Mode, Calibration, Auto-Tuning (March 17)
- Full PnL attribution, asymmetric hold-to-resolution strategy, sigma widening, disabled-by-default auto-tune

### Resolution Time Visibility (March 17)
- resolves_at, time_left, time_open. Filter/sort by resolution timing

### Position Lifecycle Management (March 17-18)
- Lifecycle modes: OFF, TAG_ONLY (default), SHADOW_EXIT, AUTO_EXIT
- Exit rules: Profit capture (2.0x), Negative edge (-100bp), Edge decay (60%), Time inefficiency (18h/300bp)
- Asymmetric positions NEVER evaluated for exit
- Lifecycle Dashboard: summary cards, reason distribution, time buckets, sold-vs-held, shadow timeline
- Threshold Simulator: 5 sliders, 3 presets, per-reason performance, decision quality
- Mode Control: segmented UI, confirmation modals for SHADOW/AUTO, MongoDB persistence

### Standard Weather Entry Quality Tightening (March 18)
- **Min quality score**: 0.35 composite threshold (edge/confidence/liquidity weighted)
- **Time-aware edge filter**: Long-dated (>24h) markets require 700bp+ edge (vs 500bp standard)
- **Long-hold penalty pre-screen**: Rejects mediocre (quality <0.50 AND edge <800bp) long-dated signals
- **Composite signal ranking**: quality_score + time_preference_bonus (0.15 weight for nearer resolution) - long_hold_penalty (0.20 for mediocre long-dated)
- **Asymmetric weather UNCHANGED** — filters only apply to standard weather signal path
- **Observability**: Entry quality metrics endpoint, rejection counters (low_quality, low_edge_long, long_hold_penalty), avg quality/edge/lead of passed signals, displayed in Lifecycle Dashboard with SELECTIVITY badge

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/positions/by-strategy | GET | Enriched positions with lifecycle |
| /api/positions/weather/exit-candidates | GET | Exit candidates + config |
| /api/positions/weather/lifecycle | GET | Full lifecycle evaluations |
| /api/positions/weather/lifecycle/dashboard | GET | Dashboard for threshold validation |
| /api/positions/weather/lifecycle/simulate | POST | Simulate with custom thresholds |
| /api/strategies/weather/lifecycle/mode | POST | Switch lifecycle mode |
| /api/strategies/weather/entry-quality | GET | Entry quality metrics + rejections |
| /api/strategies/weather/health | GET | Health + lifecycle + entry quality |

## Prioritized Backlog
### P0: Observe TAG_ONLY + entry quality, validate decisions
### P1: Enable SHADOW_EXIT, evaluate exit quality
### P2: Copy Trading Skeleton
### P3: Manual Order Entry
### P4: UI toggle for auto-tune sigma multiplier
### P5: Resolution Timeline visualization
### P6: Live Trading Mode Integration
