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
- Simplified Black-Scholes digital pricing, 5-stage scan loop, 14-step filter chain
- Audit fixes: momentum drift formula, hot-path import. Testing: 41/42 (97.6%)

### Phase 5B — Crypto Sniper Dashboard (2026-03-13) ✅ TESTED
- Sniper dashboard page: 6 stat cards, 4 tabs. Testing: 38/38 (100%)

### P&L Equity Curve (2026-03-13) ✅ TESTED
- `GET /api/analytics/pnl-history`, recharts AreaChart with gradient fill. Testing: 25/25 (100%)

### Trade Ticker Strip (2026-03-13) ✅ TESTED
- `GET /api/ticker/feed`, horizontal scrolling tape in AppShell. Testing: 21/21 (100%)

### Phase 6 — Telegram Alerts (2026-03-13) ✅ TESTED
- **Service**: `services/telegram_notifier.py` — async, fire-and-forget, rate-limited (20 msg/min)
- **Events**: Subscribes to ORDER_UPDATE (fills), RISK_ALERT (rejections, kill switch), SYSTEM_EVENT (engine start/stop), SIGNAL (strategy signals)
- **Strategies**: Added SIGNAL event emissions to ArbScanner and CryptoSniper (minimal change)
- **Config**: `telegram_enabled`, `telegram_signals_enabled` toggles via PUT /api/config
- **API**: GET /api/alerts/test, GET /api/alerts/status
- **Frontend**: Telegram Alerts section in Settings page with toggle buttons and test alert
- **Graceful degradation**: Runs without credentials, reports configured=false
- Testing: 22/22 (100%)

## Key Files
- `/app/backend/services/telegram_notifier.py` — Telegram notification service
- `/app/frontend/src/components/TradeTicker.jsx` — Trade ticker strip
- `/app/frontend/src/components/PnlChart.jsx` — P&L equity curve chart
- `/app/frontend/src/pages/Sniper.jsx` — Sniper dashboard page
- `/app/backend/engine/strategies/crypto_sniper.py` — Sniper strategy
- `/app/backend/engine/strategies/arb_scanner.py` — Arb strategy

## Example Telegram Message Formats
```
[TRADE EXECUTED]
Strategy: CRYPTO SNIPER
Market: Will BTC be above $97,000 at 14:30 UTC?
Side: BUY
Price: 0.4500
Size: 3.0
Latency: 1.2ms

[SIGNAL]
Strategy: SNIPER
Asset: BTC
Strike: 97000
Fair: 0.6200
Market: 0.4500
Edge: 640bps
Side: buy_yes

[RISK]
Order rejected
Reason: kill switch active

[ENGINE]
STARTED
Mode: paper
```

## Prioritized Backlog

### P2 — Phase 6 Remaining
- Rich analytics and historical performance tracking
- Configuration persistence to database (currently in-memory)
- Copy trading skeleton
