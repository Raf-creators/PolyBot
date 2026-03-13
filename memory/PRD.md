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
- **Audit fixes**: (1) Momentum drift formula (critical), (2) Hot-path import moved to module level
- **Testing**: 41/42 (97.6%)

### Phase 5B — Crypto Sniper Dashboard (2026-03-13) ✅ TESTED
- Dashboard page/tab for Crypto Sniper (signals, executions, vol display, health metrics)
- 6 stat cards, 4 tabs (Signals, Rejected, Executions, Health). Testing: 38/38 (100%)

### P&L Equity Curve (2026-03-13) ✅ TESTED
- **Backend**: `GET /api/analytics/pnl-history` — cumulative P&L time series with peak/trough/drawdown
- **Frontend**: `PnlChart.jsx` — recharts AreaChart with gradient fill, custom dark tooltip
- Testing: 25/25 (100%)

### Trade Ticker Strip (2026-03-13) ✅ TESTED
- **Backend**: `GET /api/ticker/feed` — unified execution feed combining arb + sniper executions
- **Frontend**: `TradeTicker.jsx` — horizontal scrolling tape, CSS animation, pause on hover
- Mounted globally in AppShell between TopBar and main content
- Reactive updates: watches `stats.total_trades` from WebSocket, re-fetches on change (no polling)
- Format: `[STRATEGY] [ASSET] [SIDE] [SIZE] @ [PRICE] EDGE [bps]`
- Color coding: BUY=green, SELL=red, positive EDGE=green, negative EDGE=red
- Testing: 21/21 (100%)

## Key Files
- `/app/frontend/src/components/TradeTicker.jsx` — Ticker component
- `/app/frontend/src/components/PnlChart.jsx` — P&L chart component
- `/app/frontend/src/components/AppShell.jsx` — Layout shell (mounts ticker)
- `/app/frontend/src/pages/Sniper.jsx` — Sniper dashboard page
- `/app/backend/engine/strategies/crypto_sniper.py` — Sniper strategy
- `/app/backend/engine/strategies/sniper_pricing.py` — Pricing math model

## Prioritized Backlog

### P2 — Phase 6
- Telegram alerts for key trading events
- Rich analytics and historical performance tracking
- Configuration persistence to database (currently in-memory)
- Copy trading skeleton
