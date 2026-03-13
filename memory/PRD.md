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
- 15+ API endpoints, MongoDB persistence
- Testing: 23/23 (100%)

### Phase 2 — Market Data & Feeds (2026-03-10) ✅
- Polymarket Gamma API + CLOB midpoint, Binance WS BTC/ETH, persistence service
- Testing: 17/17 (100%)

### Phase 3 — Arbitrage Strategy (2026-03-10) ✅
- ArbScanner with complement arb detection, pricing models, paper execution
- Testing: 31/32 (96.9%)

### Phase 4 — Frontend Dashboard (2026-03-11) ✅ AUDITED
- 6 pages: Overview, Arbitrage, Positions, Risk, Markets, Settings
- Single global WebSocket, zustand store, shared components
- Audit: 3 fixes (useApi store subscription, StatCard coloring, unused imports)
- Testing: 23/23 backend + 26/26 frontend (100%)

### Phase 5A — Crypto Sniper Strategy (2026-03-13) ✅
- **New files**: sniper_models.py, sniper_pricing.py, crypto_sniper.py
- **Models**: SniperConfig, CryptoMarketClassification, SniperSignal, SniperExecution
- **Pricing**: Lightweight Black-Scholes digital option via math.erf (no scipy)
  - compute_fair_probability, compute_realized_volatility, compute_momentum, compute_signal_confidence
- **Strategy**: 5-stage scan loop (sample → classify → evaluate → filter → execute)
  - Classification cache refreshed every 30s, not per scan
  - Ring buffer price history (deque) for vol estimation
  - Pre-computed vol + momentum per asset (not per market)
  - 12-step filter chain with bucketed rejection reasons
  - Full execution lifecycle: signal → risk check → order → fill tracking
- **API**: 4 new endpoints (signals, executions, health, test-inject)
- **Performance**: 0.87ms per scan cycle
- **Testing**: 41/42 (97.6%), full pipeline manually verified (inject → classify → signal → execute → fill)

## API Endpoints
### Core
- GET /api/, /api/health, /api/status, /api/config
- PUT /api/config
- POST /api/engine/start, /api/engine/stop
- POST /api/risk/kill-switch/activate, /api/risk/kill-switch/deactivate
- GET /api/positions, /api/orders, /api/trades, /api/markets, /api/markets/summary
- GET /api/health/feeds
- WS /api/ws

### Arb Scanner
- GET /api/strategies/arb/opportunities, /api/strategies/arb/executions, /api/strategies/arb/health

### Crypto Sniper (Phase 5A)
- GET /api/strategies/sniper/signals, /api/strategies/sniper/executions, /api/strategies/sniper/health
- POST /api/test/inject-crypto-market

## Prioritized Backlog

### P1 — Phase 5B
- Dashboard page/tab for Crypto Sniper (signals, executions, vol display, health metrics)

### P2 — Phase 6
- Telegram alerts
- Rich analytics
- Config persistence
- Copy trading skeleton
