# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets.

## Current Epoch: EPOCH 3
- **Started**: 2026-03-20 ~19:34 UTC
- **Starting Balance**: $1,000.00
- **Previous Epochs**: Epoch 1 archived (7,444 trades), Epoch 2 archived (405 trades, 307 orders)

## Core Architecture
- **Backend**: FastAPI + MongoDB, engine state, strategies, risk, positions
- **Frontend**: React dashboard for monitoring and configuration
- **External Data**: Binance WS, Open-Meteo, Polymarket Gamma + CLOB WS
- **Notifications**: Telegram

## Live Configuration (Unchanged)
- max_position_size: 25, crypto_max_exposure: $250
- arb_max_exposure: $8, weather_reserved_capital: $15
- Crypto sniper: max_tte=8h, min_edge=200bps, anti-clustering active
- Weather: min_edge=350bps, asymmetric=off, lifecycle=shadow_exit

## Shadow Systems (ALL Shadow-Only)

### Wave 0: EV-Gap + Stoikov Shadow
- Dual-mode: Unit-Size + Live-Equivalent
- API: /api/shadow/*

### Wave 1: Active Experiments
1. **MoonDev Short Window** — 5m/15m crypto shadow, dual-mode
   - API: /api/experiments/moondev/*
2. **Phantom Spread** — YES+NO dislocation scanner, unit-size
   - API: /api/experiments/phantom/*
3. **Whrrari Fair-Value / LMSR** — Multi-outcome fair-value model, **3 sizing modes**
   - **Unit-Size**: Flat $3/signal, normalized research comparison
   - **Sandbox Notional**: Edge-tiered bands ($3 at 300-599bps, $8 at 600-899bps, $15 at 900+bps) — PRIMARY PROMOTION METRIC
   - **Crypto-Mirrored**: $3/signal accumulating to $25 cap — STRESS TEST ONLY
   - API: /api/experiments/whrrari/* (positions/closed accept ?mode=unit|sandbox|crypto)

### Wave 2: Scaffolded / Planned
4. **Marik Latency Execution** — Requires sub-second polling
5. **Argona Macro Event** — Requires external event API

### Master Registry: GET /api/experiments/registry

## What Has Been Implemented
1-20. (See CHANGELOG)
21. Quant Lab Incubator — Wave 1 + Wave 2 Scaffold (Mar 20)
22. **Whrrari 3 Sizing Modes** (Mar 20)
    - Unit-Size (normalized), Sandbox Notional (edge-tiered $3/$8/$15), Crypto-Mirrored (stress test)
    - Sandbox Notional designated as primary promotion metric
    - 7 data sub-tabs in UI (per-mode open/closed + evaluations)

## Testing Status
- iteration_74: Quant Lab Incubator — 32/32
- iteration_75: Whrrari 3 Sizing Modes — 30/30 (16 backend + 14 frontend)

## Backlog

### P1 — Active Monitoring
- Watch MoonDev vs live divergence, Phantom detection rate, Whrrari group coverage
- Compare Sandbox Notional performance as primary evaluation metric

### P1 — Proposed
- Weather asymmetric as shadow-only telemetry

### P2 — Planned
- Wave 2 activation (Marik, Argona)
- Promote best shadow if data supports

### P3 — Future
- XRP/SOL, trailing stop-loss, regime detection, resolution timeline, copy trading
