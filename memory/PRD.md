# Polymarket Edge OS — PRD

## Problem Statement
Build a production-grade 24/7 automated trading platform for Polymarket markets.

## Architecture
- Frontend: React SPA, zustand, single global WebSocket, dark-mode terminal
- Backend: FastAPI async Python, MongoDB
- Execution: Dual adapter — PaperAdapter (default) + LiveAdapter (py-clob-client)

## Implemented Phases

### Phase 1-3 — Engine, Feeds, Arb Strategy
### Phase 4 — Dashboard (AUDITED)
### Phase 5A — Crypto Sniper Strategy (AUDITED)
### Phase 5B — Sniper Dashboard
### P&L Curve + Trade Ticker
### Phase 6 — Telegram Alerts
### Phase 7 — Config Persistence (MongoDB)
### Phase 8 — Live Polymarket Execution Adapter
### Phase 8A — Order Lifecycle, Partial Fills, Wallet Visibility

### Phase 8B — Final Live Trading Safeguards (2026-03-13)
- **Cancel orders**: POST /api/execution/orders/{id}/cancel — cancels open/partial CLOB orders via API or locally when offline. Persists cancelled_at and cancel_reason.
- **Slippage protection**: Pre-flight check compares order price against market mid_price. Rejects if deviation > max_live_slippage_bps (default 100bps). Configurable via allow_aggressive_live override.
- **Enhanced LiveOrderRecord**: slippage_bps, cancelled_at, cancel_reason, update_source (poll/websocket/manual) fields.
- **Live Orders tab**: New tab in Positions page showing all live order records with cancel buttons, slippage display, status badges, fill tracking columns.
- **Fill updates**: Currently polling every 5s. Architecture structured for future CLOB WebSocket integration.
- Testing: **37/37 (100%)**

## Order Lifecycle States
```
submitted        → Order sent to CLOB, awaiting match
open             → Order live on book
partially_filled → Some shares matched, order still active
filled           → All shares matched, complete
cancelled        → Cancelled (manual, system, or offline)
rejected         → Rejected (preflight, risk, slippage, CLOB error)
expired          → Expired on CLOB
```

## Safety Protections
1. POLYMARKET_PRIVATE_KEY required for live mode
2. Kill switch blocks live mode switch
3. Preflight: auth + mode + kill switch + size cap + slippage
4. Conservative LIVE_DEFAULTS: max_order=2, max_position=5, max_exposure=20
5. Risk engine gates ALL orders
6. Partial fills tracked (never treated as complete)
7. Slippage protection: rejects orders > max_live_slippage_bps
8. Cancel support for open/partial orders
9. Paper fallback if live adapter loses auth
10. Errors tracked and surfaced in health

## Remaining Before Real-Money Launch
- Full CLOB WebSocket fill notifications (currently polling 5s)
- Multi-wallet support
- Rate limit awareness for CLOB API
- Manual order entry (for ad-hoc trades)

## Prioritized Backlog
### P1 — Rich Analytics
- Historical performance, Sharpe ratio, strategy comparison, market heatmap

### P2 — Future
- Copy trading skeleton, CLOB WebSocket fills, manual order entry
