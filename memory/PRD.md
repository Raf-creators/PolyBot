# Polymarket Edge OS — PRD

## Problem Statement
Build a production-grade 24/7 automated trading platform for Polymarket markets. Priorities: structural arbitrage, fast crypto markets (BTC/ETH 5m/15m), research modules. Latency-sensitive architecture with professional dashboard.

## Architecture
- **Frontend**: React SPA (dark-mode trading dashboard, zustand state, single global WebSocket)
- **Backend**: FastAPI (async Python)
- **Database**: MongoDB (via Motor async driver)
- **Trading Engine**: Single-process async Python with StateManager + EventBus
- **Hot/Cold Path Separation**: Trading logic in-memory, dashboard reads via snapshots

## User Personas
- **Quant Trader**: Configures strategies, monitors P&L, manages risk
- **System Operator**: Monitors health, manages kill switch, reviews logs

## Core Requirements
- Structural arbitrage on binary Polymarket markets
- Fast crypto market trading (BTC/ETH 5m/15m)
- Paper / Shadow / Live trading modes
- Risk engine with kill switch, position limits, daily loss limits
- Professional dark-mode dashboard (6 pages)
- Telegram alerts (credentials-ready)
- Polymarket CLOB integration via py-clob-client SDK
- Binance WebSocket for spot price feeds

## What's Been Implemented

### Phase 1 — Backend Skeleton & Engine Scaffolding (2026-03-10)
- `models.py`: All Pydantic models (enums, data models, config, events, API models)
- `engine/state.py`: StateManager — single source of truth, pub/sub, snapshot for dashboard
- `engine/events.py`: EventBus — asyncio.Queue-backed, typed channels, handler registration
- `engine/core.py`: TradingEngine — orchestrator, component lifecycle management
- `engine/risk.py`: RiskEngine — order validation, kill switch, limit enforcement
- `engine/execution.py`: ExecutionEngine — order routing to paper/live adapters
- `engine/paper.py`: PaperAdapter — simulated fills for paper mode
- `engine/strategies/base.py`: BaseStrategy ABC
- `server.py`: FastAPI with 15+ endpoints
- **Testing**: 23/23 backend tests passed (100%)

### Phase 2 — Market Data & Feeds (2026-03-10)
- `engine/market_data.py`: Gamma API discovery + CLOB midpoint refresh
- `engine/price_feeds.py`: Binance WS with auto-reconnect + staleness monitor
- `services/persistence.py`: 10s flush interval, off the hot path
- `server.py`: WebSocket hub (2s broadcast), /api/markets/summary, /api/health/feeds
- **Testing**: 17/17 tests passed (100%)

### Phase 3 — Arbitrage Strategy (2026-03-10)
- `engine/strategies/arb_scanner.py`: Binary complement arb scanner
- `engine/strategies/arb_models.py`: ArbConfig, ArbOpportunity, ArbExecution
- `engine/strategies/arb_pricing.py`: Pricing models (fees, slippage, execution penalty, confidence)
- **Testing**: 31/32 tests passed (96.9%)

### Phase 4 — Frontend Dashboard (2026-03-11) ✅ COMPLETED + AUDITED
- **Architecture**: Single global WS, zustand store, REST hydration, selector subscriptions
- **Layout**: AppShell, Sidebar (6 nav links + WS indicator), TopBar (engine controls)
- **Shared Components**: StatCard, SectionCard, DataTable (sortable), EmptyState, HealthBadge
- **Pages**: Overview, Arbitrage (4 tabs), Positions (3 tabs), Risk (kill switch + gauges), Markets (search), Settings (config forms)
- **Design**: Dark terminal theme (Inter + JetBrains Mono), custom scrollbars
- **Testing**: 23/23 backend + 26/26 frontend (100%)
- **Audit (2026-03-11)**: All 10 audit points passed. Fixed: useApi store subscription bug (critical), StatCard PnL coloring (important), unused imports (low). Zero backend changes.

## Frontend Structure
```
src/
  state/dashboardStore.js          — zustand central store
  hooks/useWebSocket.js            — single global WS
  hooks/useApi.js                  — REST helpers (stable selector refs)
  utils/formatters.js, constants.js
  components/AppShell, Sidebar, TopBar, StatCard, SectionCard, DataTable, EmptyState, HealthBadge
  pages/Overview, Arbitrage, Positions, Risk, Markets, Settings
```

## Prioritized Backlog

### P1 — Phase 5
- Crypto sniper strategy (BTC/ETH 5m/15m)
- Fair value calculation from spot feeds

### P2 — Phase 6
- Telegram alerts
- Rich analytics
- Config persistence
- Copy trading skeleton
