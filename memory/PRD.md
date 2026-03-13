# Polymarket Edge OS — PRD

## Problem Statement
Build a production-grade 24/7 automated trading platform for Polymarket markets.

## Architecture
- **Frontend**: React SPA, zustand, single global WebSocket, dark-mode terminal
- **Backend**: FastAPI async Python, MongoDB
- **Execution**: Dual adapter — PaperAdapter (default) + LiveAdapter (py-clob-client)

## Implemented Phases

### Phase 1-3 — Engine, Feeds, Arb Strategy
### Phase 4 — Dashboard (AUDITED)
### Phase 5A — Crypto Sniper Strategy (AUDITED)
### Phase 5B — Sniper Dashboard
### P&L Curve + Trade Ticker
### Phase 6 — Telegram Alerts
### Phase 7 — Config Persistence (MongoDB)

### Phase 8 — Live Polymarket Execution Adapter
- py-clob-client v0.34.6, asyncio.to_thread wrapper
- 5 safety layers, conservative LIVE_DEFAULTS

### Phase 8A — Live Execution Hardening (2026-03-13)
- **Order Lifecycle**: submitted → open → partially_filled → filled / cancelled / expired
- **Partial Fill Handling**: Tracks filled_size vs requested_size. Positions/PnL update on actual fill delta only. Never treats partial as complete.
- **Persistence**: `live_orders` MongoDB collection stores LiveOrderRecord docs (order_id, exchange_order_id, strategy_id, token_id, side, requested_size, filled_size, remaining_size, avg_fill_price, status, timestamps)
- **Background Polling**: 5s interval checks open/partial orders via CLOB get_order()
- **Wallet Endpoint**: GET /api/execution/wallet — balance, auth status, warnings
- **Live Orders Endpoint**: GET /api/execution/orders — recent live order records
- **Health**: open_orders, partial_orders, last_api_call, last_status_refresh, recent_errors
- **TopBar**: Mode color coding (paper=zinc, shadow=amber, live=red+pulse), wallet widget
- Testing: **47/47 (100%)**

## Live Order Lifecycle States
```
submitted  → Order sent to CLOB, awaiting match
open       → Order live on book, not yet matched
partially_filled → Some shares matched, order still active
filled     → All shares matched, order complete
cancelled  → Order cancelled (by user or system)
rejected   → Order rejected (preflight/risk/CLOB error)
expired    → Order expired on CLOB
```

## Safety Protections for Live Trading
1. POLYMARKET_PRIVATE_KEY must be set (hard requirement)
2. Kill switch blocks mode switch to live
3. Preflight checks on every order: auth, mode, kill switch, size cap
4. Conservative LIVE_DEFAULTS: max_order=2, max_position=5, max_exposure=20
5. Risk engine gates ALL orders (never bypassed)
6. Partial fills tracked — never silently treated as complete
7. Paper fallback if live adapter loses authentication
8. Recent errors tracked and surfaced in health

## Pre-Launch Checklist
1. Set POLYMARKET_PRIVATE_KEY in backend .env
2. Fund wallet with USDC on Polygon
3. Verify GET /api/execution/status → authenticated=true
4. Verify GET /api/execution/wallet → balance_usdc > 0
5. Run in SHADOW mode first (validate signals)
6. Switch to LIVE only after shadow validation
7. Monitor Telegram + dashboard for fills
8. Keep kill switch accessible

## Still Missing Before Real Money
- Full CLOB WebSocket fill notifications (currently polling)
- Cancel order endpoint (manual intervention)
- Slippage protection (market vs limit)
- Multi-wallet support

## Prioritized Backlog
### P1 — Rich Analytics
- Historical performance, Sharpe ratio, strategy comparison, market heatmap

### P2 — Future
- Copy trading skeleton, cancel order endpoint, CLOB WebSocket fills
