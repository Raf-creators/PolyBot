# Polymarket Edge OS — Product Requirements Document

## Original Problem Statement
A full-stack trading bot dashboard (FastAPI + React + MongoDB) for Polymarket paper trading with 3 strategies: crypto_sniper, weather_trader, arb_scanner. Ongoing incremental upgrades to weather strategy alpha quality, market coverage, and dashboard observability.

## Architecture
```
/app
├── backend/
│   ├── engine/strategies/
│   │   ├── weather_trader.py   # Quality-score-sorted execution, position cap, market type routing
│   │   ├── weather_models.py   # WeatherMarketType enum, explanation/quality_score on signals
│   │   ├── weather_parser.py   # Expanded: precipitation/snow/wind patterns, negative Celsius
│   │   ├── weather_pricing.py  # compute_amount_bucket_probability for non-temp types
│   │   ├── weather_feeds.py    # Fetches precip/snow/wind from Open-Meteo
│   │   ├── crypto_sniper.py, sniper_models.py, arb_scanner.py
│   ├── server.py               # /positions/by-strategy, /positions/weather/breakdown
│   └── services/
└── frontend/src/pages/
    ├── Weather.jsx   # Open Positions + type breakdown + best signal + explanations
    ├── Sniper.jsx    # Open Positions + PnL bar
    └── Analytics.jsx # Strategy comparison with merged mark-to-market data
```

## Key Weather Config
- min_edge_bps: 500 (5% minimum)
- min_confidence: 0.55
- max_weather_positions: 25 hard cap
- Signal execution: sorted by quality_score descending
- Supported market types: temperature, precipitation, snowfall, wind

## What's Been Implemented

### Phase 1-6 (Prior work)
- Core engine, WebSocket, Telegram, strategy isolation, attribution, live-readiness controls
- Open positions visibility, dashboard cleanup, overtrading filter
- Explanation layer, quality score, best signal tracking, position breakdown

### Phase 7 — Multi-Market Type Support (2026-03-17)
- **WeatherMarketType enum**: TEMPERATURE, PRECIPITATION, SNOWFALL, WIND
- **Parser expansion**: Supports precipitation ("X inches or more of rain"), snowfall ("X inches of snow"), wind ("exceed X mph") patterns. Fixed negative Celsius parsing for Toronto/global markets.
- **Probability models**: Normal CDF for all types with type-specific sigma tables (precip 0.3-1.5in, snow 1.0-5.0in, wind 3.0-12.0mph)
- **Weather feeds**: Open-Meteo now fetches precipitation, snowfall, wind_speed_10m hourly data
- **Market type tracking**: by_market_type breakdown in health endpoint (classified/signals/executed/rejected per type)
- **Market discovery**: Gamma tag search expanded to rain, snow, precipitation, wind
- **UI**: "By Market Type" card in Health tab (color-coded: temp=amber, precip=blue, snow=cyan, wind=teal). Type column in signals table.
- **Coverage**: 69 markets classified (up from 65, Toronto Celsius fix). Currently 100% temperature — precip/snow/wind infrastructure ready for when markets appear.

## Prioritized Backlog

### P0 — Weather Strategy V2 (next steps)
1. Self-improvement loop: use resolved outcomes to adjust source weighting and sigma
2. Additional data source integration (OpenWeatherMap as secondary)
3. Hourly forecast mode near resolution (sub-daily precision)

### P1 — Future
- Copy Trading skeleton
- Manual Order Entry
- Live trading mode integration
- Position force-close for stale positions
