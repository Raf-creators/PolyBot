# Polymarket Edge OS — Product Requirements Document

## Original Problem Statement
A full-stack trading bot dashboard (FastAPI + React + MongoDB) for Polymarket paper trading with 3 strategies: crypto_sniper, weather_trader, arb_scanner. Ongoing incremental upgrades to improve weather strategy alpha quality and dashboard observability for paper testing.

## Architecture
```
/app
├── backend/
│   ├── engine/
│   │   ├── risk.py
│   │   ├── state.py
│   │   └── strategies/
│   │       ├── weather_trader.py  # Signal sorting by quality_score, position cap, thesis builder
│   │       ├── weather_models.py  # WeatherSignal: explanation dict, quality_score float
│   │       ├── weather_feeds.py, weather_parser.py, weather_pricing.py
│   │       ├── crypto_sniper.py, sniper_models.py
│   │       └── arb_scanner.py
│   ├── models.py
│   ├── services/ (strategy_tracker.py, telegram_notifier.py, config_service.py)
│   └── server.py               # /positions/by-strategy, /positions/weather/breakdown
└── frontend/src/
    ├── hooks/useApi.js, state/dashboardStore.js
    └── pages/ (Weather.jsx, Sniper.jsx, Analytics.jsx)
```

## Key Config (Weather Strategy)
- min_edge_bps: 500 (5% minimum edge)
- min_confidence: 0.55 (55% floor)
- max_weather_positions: 25 (hard cap)
- Signal execution: sorted by quality_score descending

## What's Been Implemented

### Phase 1-4 (Prior sessions)
- Core trading engine, WebSocket, Telegram, strategy isolation, attribution, live-readiness controls

### Phase 5 — Open Positions & Dashboard (2026-03-17)
- GET /api/positions/by-strategy with enriched metadata (city, bucket, asset, side parsing)
- Weather/Sniper pages rewritten with Open Positions as primary tab, PnL bars
- Analytics strategy comparison with merged mark-to-market data

### Phase 6 — Overtrading Filter (2026-03-17)
- Raised min_edge 300→500, min_confidence 0.40→0.55
- max_weather_positions=25 hard cap
- Signals sorted by quality_score descending (highest quality first)

### Phase 7 — Explanation Layer & Quality Score (2026-03-17)
- **Explanation layer**: Every signal (tradable + rejected) carries structured explanation dict:
  - market, location, contract_type, bucket, forecast_summary, model_probability, market_price, edge, confidence, liquidity_score, quality_score, thesis (tradable), rejection_reason (rejected)
- **Signal Quality Score**: Composite 0-1 metric = edge(50%) + confidence(30%) + liquidity(20%)
- **Best Signal per Scan**: Tracked in health endpoint with station, date, bucket, edge, quality, thesis
- **Thesis Builder**: Human-readable explanation of why a contract is mispriced
- **Position Breakdown**: GET /api/positions/weather/breakdown — by resolution date, biggest winners/losers, oldest open, stale positions
- **UI**: BEST SIGNAL banner on Signals tab, Quality/Thesis columns, color-coded rejection reasons, Context column, Position Breakdown section

## Prioritized Backlog

### P0 — Weather Strategy V2 (incremental, next steps)
1. Expand parser for precipitation/snow/wind contracts
2. Improve probability modeling for non-temperature contracts
3. Self-improvement loop: use resolved outcomes to adjust source weighting and sigma
4. Multi-source weather feeds (OpenWeatherMap as secondary)

### P1 — Future
- Copy Trading skeleton
- Manual Order Entry
- Live trading mode integration
- Position force-close for stale positions
- Advanced portfolio rebalancing
