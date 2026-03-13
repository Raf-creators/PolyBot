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

### Phase 1 — Backend Skeleton (2026-03-10)
- Pydantic models, StateManager, EventBus, TradingEngine, RiskEngine, ExecutionEngine, PaperAdapter
- 15+ API endpoints, MongoDB persistence. Testing: 23/23 (100%)

### Phase 2 — Market Data & Feeds (2026-03-10)
- Polymarket Gamma API + CLOB midpoint, Binance WS BTC/ETH, persistence. Testing: 17/17 (100%)

### Phase 3 — Arbitrage Strategy (2026-03-10)
- ArbScanner complement arb detection, pricing models, paper execution. Testing: 31/32 (96.9%)

### Phase 4 — Frontend Dashboard (2026-03-11) AUDITED
- 6 pages, single global WebSocket, zustand store. Testing: 49/49 (100%)

### Phase 5A — Crypto Sniper Strategy (2026-03-13) AUDITED
- Simplified Black-Scholes digital pricing, 5-stage scan loop, 14-step filter chain
- Audit fixes: momentum drift formula, hot-path import. Testing: 41/42 (97.6%)

### Phase 5B — Crypto Sniper Dashboard (2026-03-13)
- Sniper dashboard page: 6 stat cards, 4 tabs. Testing: 38/38 (100%)

### P&L Equity Curve (2026-03-13)
- GET /api/analytics/pnl-history, recharts AreaChart with gradient fill. Testing: 25/25 (100%)

### Trade Ticker Strip (2026-03-13)
- GET /api/ticker/feed, horizontal scrolling tape in AppShell. Testing: 21/21 (100%)

### Phase 6 — Telegram Alerts (2026-03-13)
- services/telegram_notifier.py — async, fire-and-forget, rate-limited (20 msg/min)
- Events: ORDER_UPDATE (fills), RISK_ALERT (rejections), SYSTEM_EVENT (start/stop), SIGNAL
- Config toggles: telegram_enabled, telegram_signals_enabled
- API: GET /api/alerts/test, GET /api/alerts/status
- Frontend: Telegram Alerts section in Settings page. Testing: 22/22 (100%)

### Phase 7 — Configuration Persistence (2026-03-13)
- **Service**: services/config_service.py — MongoDB configs collection, single document upsert
- **Boot**: Loads persisted config on startup, creates defaults if none exists
- **Save**: Persists on every PUT/POST config update + on shutdown
- **Apply**: Applies loaded config to state, strategies, telegram on startup
- **API**: GET /api/config (now includes strategy_configs, persisted, last_saved), GET /api/config/strategies, POST /api/config/update (granular strategy param updates)
- **Frontend**: Settings page with editable strategy parameters (click to edit, Enter to save), persistence badge
- **Verified**: Config survives backend restart. Testing: 32/32 (100%)

## Key Files
- /app/backend/services/config_service.py — Config persistence service
- /app/backend/services/telegram_notifier.py — Telegram notification service
- /app/frontend/src/components/TradeTicker.jsx — Trade ticker strip
- /app/frontend/src/components/PnlChart.jsx — P&L equity curve chart
- /app/frontend/src/pages/Sniper.jsx — Sniper dashboard page
- /app/backend/engine/strategies/crypto_sniper.py — Sniper strategy
- /app/backend/engine/strategies/arb_scanner.py — Arb strategy

## Database Schema
### configs collection
```json
{
  "_id": "engine_config",
  "trading_mode": "paper",
  "telegram_enabled": false,
  "telegram_signals_enabled": false,
  "risk": { "max_daily_loss": 100, ... },
  "strategies": {
    "arb_scanner": { "enabled": true, "min_net_edge_bps": 30, ... },
    "crypto_sniper": { "enabled": true, "min_edge_bps": 200, ... }
  },
  "updated_at": "2026-03-13T14:30:45Z"
}
```

## Prioritized Backlog

### P1 — Rich Analytics
- Historical performance tracking, Sharpe ratio, win streaks, strategy comparison
- Multi-timeframe market heatmap

### P2 — Future
- Copy trading skeleton
- Multi-user support
