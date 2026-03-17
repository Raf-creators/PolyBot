# Polymarket Edge OS — Product Requirements Document

## Original Problem Statement
A full-stack trading bot dashboard (FastAPI + React + MongoDB) for Polymarket paper trading with 3 strategies: crypto_sniper, weather_trader, arb_scanner. The user requested:
1. Per-strategy analytics with realized/unrealized PnL tracking
2. Strategy comparison UI
3. Live-readiness controls (kill switch, max loss, max exposure)
4. Dashboard upgrade to show open positions prominently
5. Weather strategy upgrade (V2) for stronger alpha generation

## Architecture
```
/app
├── backend/
│   ├── engine/
│   │   ├── risk.py           # Per-strategy position slots, live-readiness controls
│   │   ├── state.py          # Global application state
│   │   └── strategies/
│   │       ├── arb_scanner.py    # Arbitrage strategy
│   │       ├── crypto_sniper.py  # Crypto binary option sniper
│   │       ├── sniper_models.py  # Sniper data models
│   │       ├── weather_trader.py # Weather strategy
│   │       ├── weather_feeds.py  # Weather data feeds
│   │       ├── weather_parser.py # Market classification
│   │       ├── weather_pricing.py # Probability modeling
│   │       └── weather_models.py  # Weather data models
│   ├── models.py             # Core data models
│   ├── services/
│   │   ├── strategy_tracker.py # Performance tracking + attribution
│   │   └── telegram_notifier.py
│   └── server.py             # FastAPI endpoints
└── frontend/
    └── src/
        ├── hooks/useApi.js
        ├── state/dashboardStore.js
        └── pages/
            ├── Weather.jsx   # Weather trading console
            ├── Sniper.jsx    # Crypto sniper console
            └── Analytics.jsx # Strategy comparison + controls
```

## Key API Endpoints
- `GET /api/positions/by-strategy` — Strategy-filtered positions with enriched metadata, summaries
- `GET /api/analytics/strategy-attribution` — Per-strategy PnL attribution
- `GET /api/controls` — Live-readiness controls (kill switch, limits)
- `GET /api/diagnostics` — Runtime diagnostics
- `GET /api/config/strategies` — Strategy config/status

## What's Been Implemented

### Phase 1-4 (Prior sessions)
- Core trading engine with 3 strategies
- WebSocket real-time updates
- Telegram notifications
- Strategy isolation with reserved position slots
- Per-strategy analytics (attribution endpoint)
- Live-readiness controls (max daily loss, exposure, kill switch)
- PAPER MODE indicator

### Phase 5 — Open Positions Visibility (Current session, 2026-03-17)
- **NEW endpoint** `GET /api/positions/by-strategy` — returns positions grouped by weather/crypto/arb with:
  - Market enrichment (current mark, hours to resolution, unrealized PnL %)
  - Weather enrichment (city, bucket parsed from market question)
  - Sniper enrichment (asset, direction, side parsed from market question)
  - Strategy summaries with realized/unrealized/total PnL
- **Weather page rewrite** — Open Positions (54) as primary tab with city, bucket, entry, mark, unrealized PnL. PnL summary bar. Tabs: Positions > Signals > Executions > Rejected > Forecasts > Calibration > Health
- **Sniper page rewrite** — Open Positions (11) as primary tab with asset, side, entry, mark, unrealized PnL. Same PnL bar. Tabs: Positions > Signals > Rejected > Executions > Health
- **Analytics update** — Strategy Comparison cards show Total/Realized/Unrealized breakdown using live mark-to-market data. Removed RESOLVER bucket, shows CRYPTO/WEATHER/ARB only
- **Dashboard cleanup** — Focused stat cards (Open Positions, Tradable Signals, Executed, Filled, Coverage, Latency). De-emphasized low-value metrics into Health tab

## Prioritized Backlog

### P0 — Weather Strategy V2 (Phase 3, incremental)
1. Expand parser for precipitation/snow/wind contracts
2. Multi-source weather feeds (OpenWeatherMap secondary)
3. Improved probability modeling for non-temperature contracts
4. Better signal filtering with configurable thresholds
5. Self-improvement loop via calibration integration
6. Explanation layer on every signal/execution

### P1 — Future
- Copy Trading skeleton
- Manual Order Entry
- Live trading mode integration
- Position force-close for stale positions
- Advanced portfolio rebalancing
