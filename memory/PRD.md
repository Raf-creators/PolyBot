# Polymarket Edge OS — Product Requirements Document

## Original Problem Statement
A full-stack trading bot dashboard (FastAPI + React + MongoDB) for Polymarket paper trading with 3 strategies: crypto_sniper, weather_trader, arb_scanner. The user requested:
1. Per-strategy analytics with realized/unrealized PnL tracking
2. Strategy comparison UI
3. Live-readiness controls (kill switch, max loss, max exposure)
4. Dashboard upgrade to show open positions prominently
5. Weather strategy upgrade (V2) for stronger alpha generation
6. Stricter trade filtering for higher-quality weather trades

## Architecture
```
/app
├── backend/
│   ├── engine/
│   │   ├── risk.py
│   │   ├── state.py
│   │   └── strategies/
│   │       ├── arb_scanner.py
│   │       ├── crypto_sniper.py
│   │       ├── sniper_models.py
│   │       ├── weather_trader.py  # MODIFIED: edge-sorted execution, position cap check
│   │       ├── weather_feeds.py
│   │       ├── weather_parser.py
│   │       ├── weather_pricing.py
│   │       └── weather_models.py  # MODIFIED: stricter thresholds, max_weather_positions
│   ├── models.py
│   ├── services/
│   │   ├── strategy_tracker.py
│   │   └── telegram_notifier.py
│   └── server.py                  # MODIFIED: positions/by-strategy endpoint, question parsers
└── frontend/
    └── src/
        ├── hooks/useApi.js        # MODIFIED: fetchStrategyPositions
        ├── state/dashboardStore.js # MODIFIED: strategyPositions slice
        └── pages/
            ├── Weather.jsx        # REWRITTEN: open positions + cleaner layout
            ├── Sniper.jsx         # REWRITTEN: open positions + cleaner layout
            └── Analytics.jsx      # MODIFIED: merged PnL data, 3 strategy cards
```

## Key Config (Weather Strategy)
- min_edge_bps: 500 (5% minimum edge, was 300/3%)
- min_confidence: 0.55 (55% floor, was 0.40)
- max_weather_positions: 25 (hard cap, new)
- max_concurrent_signals: 8
- Signal execution: sorted by edge descending (highest quality first)

## What's Been Implemented

### Phase 1-4 (Prior sessions)
- Core trading engine, WebSocket, Telegram, strategy isolation, attribution, live-readiness controls

### Phase 5 — Open Positions & Dashboard (2026-03-17)
- New endpoint GET /api/positions/by-strategy with enriched metadata
- Weather/Sniper pages rewritten with Open Positions as primary tab
- Analytics strategy comparison updated with merged mark-to-market data

### Phase 6 — Overtrading Filter (2026-03-17)
- min_edge_bps raised 300→500 (71 rejections at 500bps threshold in first scan)
- min_confidence raised 0.40→0.55
- max_weather_positions=25 hard cap (blocks new trades when 54 positions open)
- Signals sorted by edge descending before execution (highest quality first)
- Persisted to MongoDB config, visible in Health tab UI

## Prioritized Backlog

### P0 — Weather Strategy V2 (incremental)
1. Expand parser for precipitation/snow/wind contracts
2. Multi-source weather feeds (OpenWeatherMap secondary)
3. Improved probability modeling for non-temperature contracts
4. Self-improvement loop via calibration integration
5. Explanation layer on every signal/execution

### P1 — Future
- Copy Trading skeleton
- Manual Order Entry
- Live trading mode integration
- Position force-close for stale positions
- Advanced portfolio rebalancing
