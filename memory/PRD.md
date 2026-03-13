# Polymarket Edge OS — PRD

## Problem Statement
Build a production-grade 24/7 automated trading platform for Polymarket markets. Priorities: structural arbitrage, fast crypto markets (BTC/ETH 5m/15m), research modules. Latency-sensitive architecture with professional dashboard.

## Architecture
- **Frontend**: React SPA (dark-mode trading dashboard, zustand state, single global WebSocket)
- **Backend**: FastAPI (async Python)
- **Database**: MongoDB (via Motor async driver)
- **Trading Engine**: Single-process async Python with StateManager + EventBus
- **Execution**: Dual-adapter system (PaperAdapter + LiveAdapter via py-clob-client)

## What's Been Implemented

### Phase 1-3 — Backend Foundation
- Engine skeleton, market data feeds, arbitrage strategy. Testing: 96%+

### Phase 4 — Frontend Dashboard (AUDITED)
- 7-page dark-mode trading terminal. Testing: 49/49 (100%)

### Phase 5A — Crypto Sniper Strategy (AUDITED)
- Simplified Black-Scholes pricing, 5-stage scan loop. Testing: 41/42 (97.6%)

### Phase 5B — Crypto Sniper Dashboard
- Sniper page: 6 stat cards, 4 tabs. Testing: 38/38 (100%)

### P&L Equity Curve + Trade Ticker
- GET /api/analytics/pnl-history, recharts AreaChart, horizontal scrolling trade tape. Testing: 46/46 (100%)

### Phase 6 — Telegram Alerts
- Async fire-and-forget notifications via EventBus. Testing: 22/22 (100%)

### Phase 7 — Configuration Persistence
- MongoDB configs collection, single-document upsert, survives restarts. Testing: 32/32 (100%)

### Phase 8 — Live Polymarket Execution Adapter (2026-03-13)
- **File**: `engine/live_adapter.py` — wraps `py-clob-client` v0.34.6
- **Authentication**: Private key + optional API creds (derive from key if not set)
- **Execution**: `asyncio.to_thread` for non-blocking CLOB calls
- **Modes**: paper (default), shadow (paper + live logging), live (real money)
- **Safety**:
  - Live mode requires POLYMARKET_PRIVATE_KEY set
  - Kill switch blocks live mode switch
  - Preflight checks: mode verification, auth check, kill switch, order size cap
  - Conservative LIVE_DEFAULTS auto-applied on live switch: max_order=2, max_position=5, max_exposure=20, max_positions=3, max_daily_loss=10
  - Falls back to paper if live adapter not authenticated
- **API**: GET /api/execution/mode, POST /api/execution/mode, GET /api/execution/status
- **Frontend**: Execution Mode section with mode buttons, Credentials & Adapters status
- Testing: **41/41 (100%)**

## Environment Variables
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
POLYMARKET_PRIVATE_KEY=      # Required for live trading
POLYMARKET_API_KEY=           # Optional (derived from key if empty)
POLYMARKET_API_SECRET=        # Optional
POLYMARKET_PASSPHRASE=        # Optional
POLYMARKET_FUNDER_ADDRESS=    # Optional (for proxy/email accounts)
TELEGRAM_BOT_TOKEN=           # For alerts
TELEGRAM_CHAT_ID=             # For alerts
TRADING_MODE=paper
```

## Safety Checklist Before Real Money
1. Set POLYMARKET_PRIVATE_KEY in backend .env
2. Fund the wallet with USDC on Polygon
3. Verify live adapter authenticates: GET /api/execution/status → authenticated=true
4. Start with SHADOW mode first to validate signal quality
5. Switch to LIVE only after verifying shadow logs look correct
6. Keep kill switch accessible — activate at first sign of issues
7. Monitor Telegram alerts for trade confirmations
8. Start with minimum sizes (LIVE_DEFAULTS enforced automatically)

## Prioritized Backlog
### P1 — Rich Analytics
- Historical performance, Sharpe ratio, strategy comparison, market heatmap

### P2 — Future
- Copy trading skeleton, multi-user support, order fill tracking (partial fills)
