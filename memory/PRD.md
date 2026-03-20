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

### Risk Config (Hard-pinned at startup — cannot be silently undone)
- max_position_size: 25
- crypto_max_exposure: $250 (unchanged this pass)
- arb_max_exposure: $8 (REDUCED from $25 → minimal sandbox)
- arb_reserved_capital: $8 (REDUCED from $25)
- weather_reserved_capital: $15 (NEW — guaranteed allocation floor)
- max_arb_positions: 5 (REDUCED from 10)
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
- SLOT_ROTATION now auto-exits in shadow_exit mode (was logging spam before)
- Slot rotation log deduped to 10-min cooldown per position

### Stale Arb Cleanup Cron
- Runs every 2 hours (was 4h)
- Closes arb positions older than 24h (was 48h) with negative/zero unrealized PnL

### Shadow Sniper (NO LIVE EXECUTION)
- EV-gap filter: min_ev_ratio = 0.04 (4% minimum EV/risk ratio)
- Pseudo-Stoikov reservation price: gamma=0.1, inventory_decay=0.8
- Evaluates same BTC/ETH opportunities as live sniper
- Tracks hypothetical positions and resolved PnL
- API endpoints: /api/shadow/report, /evaluations, /positions, /closed

### Telegram Monitoring
- Bihourly full performance report
- Hourly win/streak report
- Trade-by-trade notifications

## What Has Been Implemented
1. Complete multi-strategy trading engine (crypto, weather, arb)
2. Rolling PnL window system (1h, 3h, 6h)
3. Comprehensive Telegram notification system
4. Risk engine with per-strategy exposure caps, position limits, and allocation floors
5. Market resolver service with auto-resolution
6. Weather calibration system
7. Forensic rollback configuration (Mar 19 2026)
8. Stale arb position cleanup cron (tightened to 2h/24h Mar 20)
9. Arbitrage page PnL summary header
10. Overview PnL chart with time range selector (1H/6H/1D/All) + state persistence fix
11. Weather allocation floor (weather_reserved_capital=$15)
12. Shadow Crypto Sniper with EV-gap + pseudo-Stoikov (Mar 20 2026)
13. Slot rotation auto-exit fix + log dedup (Mar 20 2026)
14. Hard-pinned startup config migration (Mar 20 2026)

## Testing Status
- iteration_68.json: Forensic Rollback — 18/18 passed (100%)
- iteration_69.json: Shadow Sniper + Config Hard-Pin — 26/26 passed (100%)
- PnL chart view-mode persistence bug: Verified fixed (Mar 19)

## Backlog

### P1 — Active Monitoring
- Monitor 2h and 6h Telegram reports for crypto PnL/h recovery
- Monitor shadow sniper vs live sniper comparison at /api/shadow/report
- Confirm all legacy oversized positions resolve naturally

### P2 — Planned (DO NOT IMPLEMENT YET)
- If shadow data is promising, promote EV-gap + Stoikov to live
- Increase crypto_max_exposure (pending proof crypto is truly cap-bound)
- Add real-time weather observations API
- Add Coinbase WebSocket as second crypto feed
- Re-evaluate asymmetric weather mode
- Regime detection system

### P3 — Future
- Add XRP/SOL price feeds for alt-coin markets
- Trailing stop-loss for large crypto positions
- Resolution Timeline visualization
- Copy Trading / Manual Order Entry skeleton
