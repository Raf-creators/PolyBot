# Polymarket Edge OS — Product Requirements Document

## Original Problem Statement
Full-stack Polymarket trading bot (FastAPI + React + MongoDB) on Railway with multiple strategies: Crypto Sniper, Weather Trader, Arb Scanner, Market Resolver.

## Architecture
```
/app/backend/
├── engine/
│   ├── risk.py              # Per-strategy reserved slots (weather/crypto/arb)
│   ├── core.py              # Engine core — fixed strategy status after start()
│   ├── state.py             # In-memory state with strategy_id on positions
│   ├── paper.py             # Paper adapter sets strategy_id
│   └── strategies/
│       ├── crypto_sniper.py # BTC/ETH crypto trading
│       ├── weather_trader.py# Global weather trading (40+ cities)
│       ├── weather_parser.py# Dynamic station discovery + Celsius support
│       ├── weather_feeds.py # Gamma API global discovery
│       ├── arb_scanner.py   # Multi-outcome + binary + cross-market arb
│       └── arb_models.py
├── services/
│   ├── strategy_tracker.py  # Performance + watchdog (fixed 9999 bug)
│   ├── telegram_notifier.py # [CRYPTO]/[WEATHER]/[ARB] format
│   ├── market_resolver_service.py
│   └── persistence.py
├── server.py                # All endpoints
└── models.py                # RiskConfig with per-strategy limits + sizing
/app/frontend/src/
├── pages/ (Overview, Arbitrage, Analytics, Sniper, Weather, etc.)
├── hooks/ (useApi with arb diagnostics, signal quality, watchdog)
├── state/ (dashboardStore with all diagnostic slices)
└── components/ (HealthBadge supports 'active' status)
```

## What's Implemented

### Phase 1 (Sessions 1-4): Core Platform
- Full trading engine with paper adapter
- Multiple strategies, PnL tracking, analytics pipeline
- WebSocket real-time data, Telegram notifications
- Deployment diagnostics, state persistence

### Phase 2 (Session 5): Production Optimizations
1. Dashboard auto-refresh (5s polling + WS trade_closed)
2. Arb scanner: multi-outcome detection (67 groups, 575+ raw edges)
3. Weather global expansion (40+ cities: London, Tokyo, Seoul, Paris, etc.)
4. Signal quality + rejection visibility API + UI
5. Market freshness filter (120s staleness, 500bps spread, 25% liquidity)
6. Discovery watchdog with Telegram alerts

### Phase 3 (Session 6): Strategy Isolation & Refinement
1. **Per-strategy reserved slots**: weather=25, crypto=20, arb=20, global=65
   - Each strategy has RESERVED capacity
   - Arb bypasses global limit when it has headroom
   - No strategy can block another
2. **Duration prioritization**: estimate_time_to_resolution() scoring
   - Short-duration markets preferred for faster capital turnover
3. **Capital allocation per strategy**: crypto=$5, weather=$3, arb=$2
   - Configurable via risk config, exposed in API + UI
4. **Telegram format fix**: [CRYPTO]/[WEATHER]/[ARB] labels
   - Consistent format: Market, Side, Entry, Exit, PnL, ROI, Time
5. **Watchdog bug fix**: No more 9999 values
   - None for unrecorded events, per-condition dedup, uptime tracking
6. **Arb priority execution**: Reserved 20 slots
   - Arb headroom=15 while global headroom=0 (confirmed working)
7. **Overview status fix**: Strategies show "active" not "stopped"

## Key API Endpoints
- `GET /api/status` — Engine + strategy status (active/stopped)
- `GET /api/analytics/strategy-tracker` — Full diagnostics
- `GET /api/analytics/signal-quality` — Per-strategy rejection breakdown
- `GET /api/analytics/watchdog` — Activity timestamps + uptime
- `GET /api/strategies/arb/diagnostics` — Raw edges, rejection log, multi-outcome
- `GET /api/strategies/weather/health` — Global classification stats
- `PUT /api/config` — Live risk config modification

## Risk Config (Current Production)
```json
{
  "max_concurrent_positions": 65,
  "max_weather_positions": 25,
  "max_crypto_positions": 20,
  "max_arb_positions": 20,
  "crypto_position_size": 5.0,
  "weather_position_size": 3.0,
  "arb_position_size": 2.0,
  "min_market_freshness_seconds": 120,
  "max_spread_bps": 500,
  "max_size_to_liquidity_ratio": 0.25
}
```

## Testing Status
- iteration_42: 29/29 backend, all frontend — 100%
- iteration_43: 17/17 backend, all frontend — 100%

## P1 Backlog
- Reduce weather classification failures (26 remaining global markets)
- Advanced duration scoring integration with signal selection
- Copy Trading skeleton (backend models + API)
- Manual Order Entry (UI + API)

## P2 Future
- Live trading mode integration
- Position force-close feature for stale positions
- Advanced portfolio rebalancing
