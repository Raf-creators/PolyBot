# Polymarket Edge OS — PRD

## Problem Statement
Build a production-grade 24/7 automated trading platform for Polymarket markets. Priorities: structural arbitrage, fast crypto markets (BTC/ETH 5m/15m), research modules. Latency-sensitive architecture with professional dashboard.

## Architecture
- **Frontend**: React SPA (dark-mode trading dashboard, zustand state, single global WebSocket)
- **Backend**: FastAPI (async Python)
- **Database**: MongoDB (via Motor async driver)
- **Trading Engine**: Single-process async Python with StateManager + EventBus
- **Hot/Cold Path Separation**: Trading logic in-memory, dashboard reads via snapshots

## What's Been Implemented

### Phase 1 — Backend Skeleton (2026-03-10) ✅
- Pydantic models, StateManager, EventBus, TradingEngine, RiskEngine, ExecutionEngine, PaperAdapter
- 15+ API endpoints, MongoDB persistence. Testing: 23/23 (100%)

### Phase 2 — Market Data & Feeds (2026-03-10) ✅
- Polymarket Gamma API + CLOB midpoint, Binance WS BTC/ETH, persistence. Testing: 17/17 (100%)

### Phase 3 — Arbitrage Strategy (2026-03-10) ✅
- ArbScanner complement arb detection, pricing models, paper execution. Testing: 31/32 (96.9%)

### Phase 4 — Frontend Dashboard (2026-03-11) ✅ AUDITED
- 6 pages, single global WebSocket, zustand store. Testing: 49/49 (100%)

### Phase 5A — Crypto Sniper Strategy (2026-03-13) ✅ AUDITED
- **Files**: sniper_models.py, sniper_pricing.py, crypto_sniper.py
- **Math model**: Simplified Black-Scholes digital via math.erf (no scipy)
- **Strategy**: 5-stage scan loop (sample→classify→evaluate→filter→execute)
- **Classification**: Regex with cache refresh every 30s, 6 rejection reason categories
- **Filters**: 14-step chain (spot/market freshness, TTE, vol, liquidity, spread, edge, confidence, kill switch, concurrency, cooldown)
- **Performance**: 0.87ms/scan cycle, ring buffer price history, pre-computed vol/momentum per asset
- **Audit fixes**: (1) Momentum drift formula (critical), (2) Hot-path import moved to module level
- **Testing**: 41/42 (97.6%, 1 skipped = warm-up time). Full pipeline manually verified.

## Prioritized Backlog

### P1 — Phase 5B
- Dashboard page/tab for Crypto Sniper (signals, executions, vol display, health metrics)

### P2 — Phase 6
- Telegram alerts, rich analytics, config persistence, copy trading skeleton
