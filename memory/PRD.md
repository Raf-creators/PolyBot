# Polymarket Edge OS — Product Requirements Document

## Original Problem Statement
Build a full-stack trading application (FastAPI + React + MongoDB) that runs on Railway as a Polymarket trading bot. The bot executes multiple trading strategies:
- **Crypto Sniper**: Trades BTC/ETH crypto price prediction markets
- **Weather Trader**: Trades weather temperature markets using forecast edge
- **Arb Scanner**: Scans for structural arbitrage across all markets
- **Market Resolver**: Closes positions at market resolution

The user's primary focus is production-grade reliability, real-time dashboard updates, and comprehensive diagnostics for debugging and monitoring the live bot.

## Core Requirements
1. **Dashboard Auto-Refresh**: Near real-time UI updates when trades close (WebSocket + polling)
2. **Position Slot Segmentation**: Per-strategy position limits (weather: 25, non-weather: 25, global: 55)
3. **Market Freshness Filter**: Skip stale markets with no recent price movement
4. **Liquidity/Fill Quality Checks**: Pre-trade bid/ask spread and depth validation
5. **Strategy-Level Performance Tracking**: PnL, win rate, trade counts per strategy
6. **Signal Rejection Diagnostics**: Track and display why signals are rejected
7. **Discovery Watchdog**: Telegram alerts when no new markets/trades detected
8. **Duration Prioritization**: Prefer shorter-duration markets
9. **Capital Allocation**: Different position sizing per strategy

## Architecture
```
/app
├── backend/
│   ├── engine/
│   │   ├── risk.py              # Per-strategy position limits, market freshness filter
│   │   ├── state.py             # In-memory state manager
│   │   ├── paper.py             # Paper trading adapter (sets strategy_id on Position)
│   │   └── strategies/
│   │       ├── crypto_sniper.py # BTC/ETH crypto trading
│   │       ├── weather_trader.py# Global weather market trading
│   │       ├── weather_parser.py# Dynamic global station discovery (40+ cities)
│   │       ├── weather_feeds.py # Gamma API + Open-Meteo global weather discovery
│   │       ├── arb_scanner.py   # Binary + multi-outcome + cross-market arb detection
│   │       └── arb_models.py    # Arb data models
│   ├── services/
│   │   ├── strategy_tracker.py  # Per-strategy performance + watchdog + rejection diagnostics
│   │   ├── telegram_notifier.py # All-strategy trade close notifications
│   │   ├── market_resolver_service.py # Position resolution at market close
│   │   └── persistence.py       # MongoDB state persistence
│   ├── server.py                # FastAPI app with all endpoints
│   └── models.py                # Pydantic models (Position has strategy_id)
└── frontend/
    └── src/
        ├── hooks/
        │   ├── useApi.js        # API hooks (arb diagnostics, signal quality, watchdog, tracker)
        │   └── useWebSocket.js  # WS trade_closed event listener
        ├── state/
        │   └── dashboardStore.js# Zustand store with arbDiagnostics, signalQuality, watchdog
        └── pages/
            ├── Overview.jsx     # Dashboard with auto-refresh
            ├── Arbitrage.jsx    # Arb scanner diagnostics (raw edges, rejection log)
            ├── Analytics.jsx    # Signal Quality + Watchdog tabs
            ├── Sniper.jsx       # Crypto sniper signals
            └── Weather.jsx      # Weather strategy signals
```

## What's Been Implemented (as of 2026-03-17)

### Session 1-3: Core Platform
- Full-stack FastAPI + React + MongoDB architecture
- Multiple trading strategies (Crypto Sniper, Weather Trader, Arb Scanner)
- Paper trading engine with position management
- Real-time WebSocket data streaming
- PnL tracking and analytics pipeline
- Telegram notifications for trade alerts

### Session 4: Analytics Pipeline Fix
- Fixed test data injection, state persistence across restarts
- Fixed market data availability for resolver
- Deployment diagnostics endpoint (/api/diagnostics)

### Session 5: Production Optimizations (CURRENT)
1. **Position Slot Segmentation**: max_weather=25, max_nonweather=25, max_global=55
   - Position model now has strategy_id field
   - Paper adapter sets strategy_id on new positions
   - Risk engine classifies positions by strategy_id or keyword fallback
   - Diagnostics: headroom, by_strategy, blocked_by_position_limit counts
2. **Dashboard Auto-Refresh**: 5s polling + WebSocket trade_closed push
   - No-cache middleware prevents stale API responses
3. **Arb Scanner Debug + Expansion**:
   - Root cause: Binary YES/NO arb doesn't exist (market makers too efficient)
   - Added multi-outcome weather event detection (67 groups found)
   - Added cross-market duplicate detection
   - Comprehensive diagnostics: raw_edges, rejection_log, per-scan metrics
   - Found 575+ raw edges across 45+ scans, 99 eligible (blocked by risk - global limit)
4. **Weather Strategy Global Expansion**:
   - Dynamic station discovery: 40+ cities globally
   - Auto-creates StationInfo for London, Tokyo, Seoul, Hong Kong, Paris, etc.
   - Celsius support for international markets
   - Broad Gamma API search beyond hardcoded slugs
5. **Telegram All-Strategy Fix**:
   - Sends formatted trade close for ALL strategies (crypto, weather, arb, resolver)
   - Includes strategy name, market, side, entry/exit, PnL, ROI, timestamp
6. **Signal Quality + Rejection Visibility**:
   - New API: /api/analytics/signal-quality with per-strategy rejection reasons
   - UI: Analytics > Signal Quality tab with rejection breakdown
   - UI: Position Slots section with headroom and blocked counts
7. **Market Freshness Filter**:
   - Risk engine checks min_market_freshness_seconds (120s default)
   - Bid/ask spread check (max_spread_bps: 500)
   - Liquidity ratio check (max_size_to_liquidity_ratio: 0.25)
8. **Discovery Watchdog**:
   - Background task checks every 5 min for activity gaps
   - Telegram alerts if no markets (30min), trades opened (60min), trades closed (120min)
   - UI: Analytics > Watchdog tab with timestamps and thresholds

## Key API Endpoints
- `GET /api/diagnostics` — Environment + build info
- `GET /api/analytics/strategy-tracker` — Full diagnostics (performance, slots, rejections, watchdog)
- `GET /api/analytics/signal-quality` — Per-strategy signal generation/rejection
- `GET /api/analytics/watchdog` — Discovery watchdog timestamps
- `GET /api/strategies/arb/diagnostics` — Arb scanner raw edges, rejection log, multi-outcome groups
- `GET /api/strategies/arb/health` — Arb scanner metrics
- `GET /api/strategies/weather/health` — Weather classification stats + global coverage
- `POST /api/config/update` — Live risk config modification

## Database Schema
- **trades**: Closed trade records with strategy_id, pnl, timestamps
- **configs**: Risk configuration (per-strategy limits persisted)
- **snapshots**: Open positions with strategy_id, market data cache

## P0 Remaining Tasks
None — all requested features implemented and tested.

## P1 Backlog
- Duration Prioritization: Prefer shorter-duration markets
- Capital Allocation per strategy: Configurable position sizing
- Fix "stopped" strategy status display on Overview page
- Improve weather market classification (reduce 26 failures from global expansion)

## P2 Future Tasks
- Copy Trading skeleton: Backend models + API endpoints
- Manual Order Entry: UI + API for manual trade execution
- Live trading mode integration (currently paper-only in preview)

## Testing Status
- Backend: 29/29 tests passed (iteration_42)
- Frontend: All UI features verified
- No known regressions
