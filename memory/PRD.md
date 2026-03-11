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
- `server.py`: FastAPI with 15+ endpoints (status, engine control, config, risk, trades, positions, orders, markets)
- `.env`: All credential placeholders (Polymarket, Telegram, trading mode)
- **Testing**: 23/23 backend tests passed (100%)

### Phase 2 — Market Data & Feeds (2026-03-10)
- `engine/market_data.py`: Gamma API discovery + CLOB midpoint refresh
- `engine/price_feeds.py`: Binance WS with auto-reconnect + staleness monitor
- `services/persistence.py`: 10s flush interval, off the hot path
- `server.py`: WebSocket hub (2s broadcast), /api/markets/summary, /api/health/feeds
- **Testing**: 17/17 tests passed (100%)

### Phase 3 — Arbitrage Strategy (2026-03-10)
- `engine/strategies/arb_scanner.py`: Main strategy with scan loop, pair detection, evaluation, execution
- `engine/strategies/arb_models.py`: ArbConfig, ArbOpportunity, ArbExecution, ArbPairStatus
- `engine/strategies/arb_pricing.py`: Pricing models (fees, slippage, execution penalty, confidence)
- `engine/paper.py`: Fixed to populate market_question/outcome on positions and trades
- `server.py`: Arb API endpoints, unique-ID test inject endpoint
- **Testing**: 31/32 tests passed (96.9%)

### Phase 4 — Frontend Dashboard (2026-03-11) ✅ COMPLETED
- **Architecture**: React SPA with zustand state store, single global WebSocket, REST hydration
- **Components**:
  - `AppShell.jsx`: Main layout with Sidebar + TopBar + Outlet
  - `Sidebar.jsx`: Navigation with 6 links, engine status indicator, WS connection status
  - `TopBar.jsx`: Engine status, mode, uptime, kill switch indicator, Start/Stop button
  - `StatCard.jsx`, `SectionCard.jsx`, `EmptyState.jsx`, `HealthBadge.jsx`, `DataTable.jsx`: Reusable shared components
- **State**: `dashboardStore.js` — zustand store with WS snapshot + REST-hydrated data
- **Hooks**: `useWebSocket.js` (single global WS), `useApi.js` (REST helpers)
- **Utils**: `formatters.js`, `constants.js`
- **Pages**:
  1. **Overview**: 6 stat cards, System Status, Active Strategies, Feed Health, Recent Trades
  2. **Arbitrage**: 4 tabs (Opportunities, Rejected, Executions, Health), sortable tables, scanner metrics/config
  3. **Positions**: 3 tabs (Positions, Trades, Orders), exposure/PnL stats, sortable tables
  4. **Risk**: Kill switch toggle + banner, risk gauges (exposure, positions, daily loss), alerts, config, component/strategy health
  5. **Markets**: 200-market table with search/filter, volume/liquidity stats, sortable columns
  6. **Settings**: Trading mode toggle, credentials status, risk config form with save, strategy config display
- **Design**: Dark trading terminal theme (Inter + JetBrains Mono), custom scrollbars, professional color palette
- **Testing**: 23/23 backend + 26/26 frontend (100%)

## Frontend Structure
```
src/
  pages/
    Overview.jsx, Arbitrage.jsx, Positions.jsx, Risk.jsx, Markets.jsx, Settings.jsx
  components/
    AppShell.jsx, Sidebar.jsx, TopBar.jsx, StatCard.jsx, SectionCard.jsx,
    DataTable.jsx, EmptyState.jsx, HealthBadge.jsx
    ui/ (shadcn components)
  hooks/
    useWebSocket.js, useApi.js
  state/
    dashboardStore.js
  utils/
    formatters.js, constants.js
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
- Weather research placeholder

## API Endpoints
- GET /api/ — Root info
- GET /api/health — Health check
- GET /api/status — Full state snapshot
- GET /api/config — Config + credentials
- PUT /api/config — Update config (mode, risk)
- POST /api/engine/start — Start engine
- POST /api/engine/stop — Stop engine
- POST /api/risk/kill-switch/activate
- POST /api/risk/kill-switch/deactivate
- GET /api/positions
- GET /api/orders
- GET /api/trades
- GET /api/markets
- GET /api/markets/summary
- GET /api/health/feeds
- GET /api/strategies/arb/opportunities
- GET /api/strategies/arb/executions
- GET /api/strategies/arb/health
- WS /api/ws — Real-time state broadcast (2s)
