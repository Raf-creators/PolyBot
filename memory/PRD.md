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

## Current Configuration (Post Forensic Rollback, Mar 19 2026)

### Risk Config
- max_position_size: 25 (REVERTED from 40)
- crypto_max_exposure: $250 (increased from $180)
- arb_max_exposure: $25 (REDUCED from $120)
- arb_reserved_capital: $25 (REDUCED from $120)
- max_arb_positions: 10 (REDUCED from 40)
- weather_max_exposure: $120
- max_market_exposure: $360

### Crypto Sniper
- max_tte_seconds: 28800 (8h, REVERTED from 12h)
- opposite_side_held filter: RE-ACTIVATED
- min_edge_bps: 200
- Entry prices naturally cluster near 0.50 (structural to binary up/down markets)
- Scans ALL available future time windows, not just nearest

### Weather Trader
- min_edge_bps: 350 (reduced from 500)
- min_confidence: 0.45 (reduced from 0.55)
- default_size: 5.0 (increased from 3.0)
- max_signal_size: 12.0 (increased from 8.0)
- lifecycle_mode: shadow_exit
- asymmetric_enabled: False

### Telegram Monitoring
- Bihourly full performance report
- Hourly win/streak report
- Trade-by-trade notifications
- Upgrade tracking

### Stale Arb Cleanup Cron
- Runs every 4 hours
- Closes arb positions older than 48h with negative/zero unrealized PnL

## What Has Been Implemented
1. Complete multi-strategy trading engine (crypto, weather, arb)
2. Rolling PnL window system (1h, 3h, 6h)
3. Comprehensive Telegram notification system
4. Risk engine with per-strategy exposure caps and position limits
5. Market resolver service with auto-resolution
6. Weather calibration system
7. Forensic rollback configuration (Mar 19 2026)
8. Stale arb position cleanup cron
9. Arbitrage page PnL summary header (Mar 19 2026)
10. Overview PnL chart with brush zoom/pan + Recent/All toggle (Mar 19 2026)

## Testing Status
- iteration_68.json: Forensic Rollback — 18/18 passed (100%)
- Frontend: Arb PnL header and PnL chart UX verified via screenshots
- Legacy size-39 positions confirmed as pre-rollback, will resolve naturally

## Backlog

### P1 — Active Monitoring
- Monitor 2h and 6h Telegram reports for crypto PnL/h recovery
- Confirm all legacy size-39 positions resolve naturally

### P2 — Planned (DO NOT IMPLEMENT YET)
- Add real-time weather observations API
- Add Coinbase WebSocket as second crypto feed
- Add second forecast source for weather cross-validation
- Re-evaluate asymmetric weather mode
- Regime detection system

### P3 — Future
- Add XRP/SOL price feeds for alt-coin markets
- Trailing stop-loss for large crypto positions
- Resolution Timeline visualization
- Copy Trading / Manual Order Entry skeleton
