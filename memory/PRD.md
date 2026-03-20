# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets. Operates three strategies:
1. **Crypto Sniper** — Primary profit driver. Trades BTC/ETH up/down markets on 5min-4h windows using Binance real-time price feeds.
2. **Weather Trader** — Trades temperature/weather outcome markets using Open-Meteo forecasts.
3. **Arb Scanner** — Multi-outcome arbitrage across weather and other markets.

## Core Architecture
- **Backend**: FastAPI + MongoDB, manages engine state, strategies, risk, positions
- **Frontend**: React dashboard for monitoring and configuration
- **External Data**: Binance WebSocket (BTC/ETH), Open-Meteo (weather), Polymarket Gamma API + CLOB WebSocket
- **Notifications**: Telegram bot for trade alerts, performance reports

## Current Configuration (Post Live Patch, Mar 20 2026)

### Risk Config (Hard-pinned at startup)
- max_position_size: 25
- crypto_max_exposure: $250 (unchanged)
- arb_max_exposure: $8 (minimal sandbox)
- arb_reserved_capital: $8
- weather_reserved_capital: $15 (guaranteed allocation floor)
- max_arb_positions: 5
- weather_max_exposure: $120
- max_market_exposure: $360

### Shadow Sniper (NO LIVE EXECUTION)
- EV-gap filter: min_ev_ratio = 0.04 (4%)
- Pseudo-Stoikov reservation price: gamma=0.1, inventory_decay=0.8
- Fully isolated — zero live fills
- API: /api/shadow/report, /evaluations, /positions, /closed

## Frontend Pages
1. **Overview** — PnL chart (1H/6H/1D/All), strategy summaries, trade ticker
2. **Arbitrage** — PnL summary header, arb positions/executions
3. **Sniper** — Live crypto positions, signals, health + compact shadow summary card
4. **Weather** — Weather signals, positions, lifecycle management
5. **Quant Lab** — Full shadow monitoring dashboard (NEW Mar 20)
6. **Positions** — Cross-strategy position view
7. **Analytics** — Strategy-level analytics
8. **Global Analytics** — Cross-strategy analytics
9. **Risk** — Risk config and exposure monitoring
10. **Markets** — Market browser
11. **Settings** — Engine configuration

## What Has Been Implemented
1. Complete multi-strategy trading engine (crypto, weather, arb)
2. Rolling PnL window system (1h, 3h, 6h)
3. Comprehensive Telegram notification system
4. Risk engine with per-strategy exposure caps, position limits, allocation floors
5. Market resolver service with auto-resolution
6. Weather calibration system
7. Forensic rollback configuration (Mar 19)
8. Stale arb position cleanup cron (2h/24h)
9. Arbitrage page PnL summary header
10. Overview PnL chart with state persistence fix
11. Weather allocation floor (weather_reserved_capital=$15)
12. Shadow Crypto Sniper with EV-gap + pseudo-Stoikov (Mar 20)
13. Slot rotation auto-exit fix + log dedup (Mar 20)
14. Hard-pinned startup config migration (Mar 20)
15. **Quant Lab page** — Full shadow monitoring dashboard (Mar 20)
16. **Sniper page shadow summary** — Compact card with agreement rate, counts, PnL (Mar 20)

## Testing Status
- iteration_68.json: Forensic Rollback — 18/18 passed (100%)
- iteration_69.json: Shadow Sniper + Config Hard-Pin — 26/26 passed (100%)
- iteration_70.json: Quant Lab UI + Shadow Summary — 100% passed (all 11 features)

## Backlog

### P1 — Active Monitoring
- Monitor shadow vs live via Quant Lab page
- Watch Telegram 2h/6h reports for crypto PnL recovery
- Confirm legacy oversized positions resolve naturally

### P2 — Planned
- If shadow data promising, promote EV-gap + Stoikov to live
- Increase crypto_max_exposure once crypto proves cap-bound
- Add weather observations API
- Add Coinbase WebSocket as second crypto feed
- Re-evaluate asymmetric weather mode

### P3 — Future
- Add XRP/SOL price feeds
- Trailing stop-loss
- Regime detection model
- Resolution Timeline visualization
- Copy Trading / Manual Order Entry skeleton
