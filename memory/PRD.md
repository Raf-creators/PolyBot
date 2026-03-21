# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets.

## Current Epoch: EPOCH 4
- **Started**: 2026-03-20 ~23:42 UTC
- **Starting Balance**: $1,000.00
- **Previous Epochs**: Epoch 1 (7,444 trades), Epoch 2 (405 trades), Epoch 3 (archived for Phase 1+2 baseline)

## Core Architecture
- **Backend**: FastAPI + MongoDB, engine state, strategies, risk, positions
- **Frontend**: React dashboard for monitoring and configuration
- **External Data**: Binance WS, Open-Meteo, Polymarket Gamma + CLOB WS
- **Notifications**: Telegram

## Live Strategies
- **Crypto Sniper**: Dynamic Kelly-inspired sizing ($5/$8/$12/$18/$25 tiers by edge, capped by max_signal_size=8 per order), window-aware caps (5m=10, 15m=18, 1h=22), dislocation filter (< 3% = coin-flip rejection), anti-clustering
- **Arb Scanner**: Multi-outcome structural arbitrage
- **Weather Trader**: Temperature prediction markets

## Shadow Systems (ALL Shadow-Only)

### Wave 0: EV-Gap + Stoikov Shadow
- Dual-mode: Unit-Size + Live-Equivalent
- API: /api/shadow/*

### Wave 1: Active Experiments
1. **MoonDev Short Window** — 5m/15m crypto shadow, dual-mode (API: /api/experiments/moondev/*)
2. **Phantom Spread** — YES+NO dislocation + **Gabagool both-sides** structural arb (buy YES+NO when sum < $0.96)
   - One-Side: Directional dislocation
   - Gabagool: Guaranteed structural arb — 100% win rate on 4 closed pairs
   - API: /api/experiments/phantom/* (positions/closed accept ?mode=unit|gabagool)
3. **Whrrari Fair-Value / LMSR** — Multi-outcome model, 3 sizing modes (unit/sandbox/crypto)
   - API: /api/experiments/whrrari/* (positions/closed accept ?mode=unit|sandbox|crypto)

### Wave 2: Scaffolded / Planned
4. **Marik Latency Execution** — Requires sub-second polling
5. **Argona Macro Event** — Requires external event API

### Master Registry: GET /api/experiments/registry

## What Has Been Implemented
1-22. (See previous PRD entries)
23. **Phase 1: Dynamic Sizing** (Mar 20) — Kelly-inspired tiers, window caps, dislocation filter
24. **Phase 2: Phantom Gabagool** (Mar 20) — Both-sides structural arb mode in Phantom
25. **Epoch 4 Reset** (Mar 20) — Clean $1000 baseline for Phase 1+2 evaluation
26. **Gabagool UI Fix** (Mar 21) — Added missing gabagoolOpenCols/gabagoolClosedCols in QuantLab.jsx

## Testing Status
- iteration_74: Quant Lab Incubator — 32/32
- iteration_75: Whrrari 3 Sizing Modes — 30/30
- iteration_76: Sanity Check Audit — 50/50 (33 backend + 17 frontend)

## Backlog

### P1 — Active Monitoring
- Watch dynamic sizing performance vs flat sizing
- Gabagool structural arb: track resolution times and edge persistence
- Shadow Sniper LE outperforming live (+$24 vs negative) — investigate divergence

### P1 — Upcoming
- Activate Marik Latency Execution
- Activate Argona Macro Event

### P2 — Config Tuning
- Consider increasing max_signal_size from 8 to allow upper dynamic tiers to activate
- Window detection only works for slug-format markets; question-text markets default to global cap

### P3 — Future
- XRP/SOL, trailing stop-loss, regime detection, resolution timeline, copy trading
