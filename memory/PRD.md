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
- Engine with paper trading adapter, market discovery, price feeds, risk management, Telegram alerts

### Weather V2 + Asymmetric + Calibration (March 17)
- Overtrading filter, quality score, multi-market types
- Asymmetric hold-to-resolution strategy (unchanged)
- Sigma widening, Brier score, auto-tune framework (disabled by default)
- PnL attribution fix, resolution time visibility

### Position Lifecycle Management (March 17-18)
- **Modes**: OFF, TAG_ONLY (default), SHADOW_EXIT, AUTO_EXIT
- **Exit rules**: Profit capture (2.0x), Negative edge (-100bp), Edge decay (60%), Time inefficiency (18h/300bp)
- **Lifecycle Dashboard**: Summary cards, reason distribution, time buckets, shadow timeline, sold-vs-held comparison
- **Threshold Simulator**: 5 sliders, 3 presets, per-reason performance, decision quality
- **Mode Control**: Segmented UI with confirmation modals, MongoDB persistence

### Standard Weather Entry Quality Tightening (March 18)
- Min quality score (0.35), time-aware edge filter (700bp for >24h), long-hold penalty
- Composite signal ranking with time-to-resolution preference
- Entry quality observability: rejection counters, avg quality/edge/lead

### Slot Rotation / Inventory Cleanup (March 18)
- **New exit reason**: `SLOT_ROTATION` — flags weak long-dated positions blocking better signals
- **Book-level ranking**: All positions scored by composite (edge 40% + profit 35% + time preference 25%)
- **Criteria**: Bottom 30% of book AND >24h to resolution AND <200bp edge AND <1.2x profit
- **Config**: slot_rotation_enabled=true, slot_rotation_bottom_pct=0.30, slot_rotation_min_hours_to_res=24, slot_rotation_max_edge_bps=200, slot_rotation_max_profit_mult=1.2
- **UI**: Slot Rotations count card, Rank column (#rank/total with color coding), EXIT: Slot Rotation badge (cyan)
- **Simulator**: Includes slot rotation in per-reason simulation
- **Asymmetric**: NEVER ranked or flagged for slot rotation

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/positions/by-strategy | GET | Positions with lifecycle + book rank |
| /api/positions/weather/exit-candidates | GET | Exit candidates + config |
| /api/positions/weather/lifecycle | GET | Full lifecycle evals with book ranking |
| /api/positions/weather/lifecycle/dashboard | GET | Dashboard with slot rotation counts |
| /api/positions/weather/lifecycle/simulate | POST | Simulate thresholds + slot rotation |
| /api/strategies/weather/lifecycle/mode | POST | Switch lifecycle mode |
| /api/strategies/weather/entry-quality | GET | Entry quality + rejection metrics |

## Prioritized Backlog
### P0: Observe TAG_ONLY + entry quality + slot rotation flags
### P1: Enable SHADOW_EXIT, evaluate all exit paths
### P2: Copy Trading Skeleton
### P3: Manual Order Entry
### P4: UI toggle for auto-tune sigma multiplier
### P5: Resolution Timeline visualization
### P6: Live Trading Mode Integration
