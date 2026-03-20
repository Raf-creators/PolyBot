# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets.

## Current Epoch: EPOCH 3
- **Started**: 2026-03-20 ~19:34 UTC
- **Starting Balance**: $1,000.00
- **Previous Epochs**: Epoch 1 archived (7,444 trades), Epoch 2 archived (405 trades, 307 orders)
- **Purpose**: Clean baseline for Quant Lab incubator launch

## Core Architecture
- **Backend**: FastAPI + MongoDB, engine state, strategies, risk, positions
- **Frontend**: React dashboard for monitoring and configuration
- **External Data**: Binance WS, Open-Meteo, Polymarket Gamma + CLOB WS
- **Notifications**: Telegram (2h full report, 1h win/streak, per-trade)

## Live Configuration (Unchanged)
- max_position_size: 25, crypto_max_exposure: $250
- arb_max_exposure: $8 (sandbox), weather_reserved_capital: $15
- Crypto sniper: max_tte=8h, opposite_side_held=active, min_edge=200bps, anti-clustering (position_capped pre-check)
- Weather: min_edge=350bps, min_confidence=0.45, lifecycle=shadow_exit, asymmetric=off
- Stale arb cleanup: 2h interval, 24h threshold

## Shadow Systems (ALL Shadow-Only, NO Live Execution)

### Wave 0: EV-Gap + Stoikov Shadow (Original)
- Dual-mode: Unit-Size ($3/signal) + Live-Equivalent (up to 25 shares)
- EV-gap (4%), pseudo-Stoikov (gamma=0.1), binary resolution
- API: /api/shadow/report, /evaluations, /positions?mode=unit|le, /closed?mode=unit|le

### Wave 1: Active Experiments (NEW — Epoch 3)
1. **MoonDev Short Window** — Shadow sniper restricted to 5m/15m windows only
   - Receives same signal feed as main shadow, filters by window
   - Dual-mode (unit + LE), 150bps min edge
   - API: /api/experiments/moondev/report|evaluations|positions|closed

2. **Phantom Spread** — YES+NO pricing dislocation detection
   - Independent scan loop (15s interval), min 80bps spread
   - Unit-size only, 120s cooldown per condition
   - API: /api/experiments/phantom/report|evaluations|positions|closed

3. **Whrrari Fair-Value / LMSR** — Multi-outcome fair-value heuristic
   - LMSR-inspired softmax probability model (b=2.0)
   - Flags deviations ≥300bps from model, min 3 outcomes
   - API: /api/experiments/whrrari/report|evaluations|positions|closed

### Wave 2: Scaffolded / Planned (NOT YET ACTIVE)
4. **Marik Latency Execution** — Requires sub-second polling infrastructure
5. **Argona Macro Event** — Requires external macro event calendar API

### Master Registry
- GET /api/experiments/registry — Returns all experiments with status

## What Has Been Implemented
1-18. (See CHANGELOG for full history)
19. Paper Performance Reset / Epoch 2 (Mar 20)
20. Anti-Clustering Fix for Crypto Sniper (Mar 20) — position_capped pre-check
21. **Quant Lab Incubator — Wave 1 + Wave 2 Scaffold** (Mar 20)
    - 3 active shadow experiments: MoonDev, Phantom, Whrrari
    - 2 planned placeholders: Marik, Argona
    - Epoch 3 reset (archived epoch 2 data, $1000 baseline)
    - Tabbed QuantLab.jsx UI with per-experiment metrics, positions, evaluations
    - All experiments 100% in-memory, fully isolated from live

## Testing Status
- iteration_68-73: Previous features (all passed)
- iteration_74: Quant Lab Incubator — 32/32 (23 backend + 9 frontend)

## Backlog

### P0 — Complete
- Anti-clustering fix, Quant Lab Wave 1 + Wave 2 scaffold

### P1 — Active Monitoring
- Watch MoonDev vs live sniper performance divergence
- Monitor Phantom spread detection rate as market pairs accumulate
- Monitor Whrrari multi-outcome group coverage
- Compare all shadow experiments against live

### P1 — Proposed (User Approval Needed)
- Weather asymmetric as shadow-only telemetry (hypothetical signals + PnL, no live)

### P2 — Planned
- Wave 2 activation: Marik Latency (requires polling infra), Argona Macro (requires event API)
- Promote best-performing shadow to live if data supports
- Increase crypto_max_exposure once cap-bound proven
- Weather observations API, Coinbase WebSocket

### P3 — Future
- XRP/SOL, trailing stop-loss, regime detection
- Resolution Timeline visualization
- Copy Trading / Manual Order Entry
