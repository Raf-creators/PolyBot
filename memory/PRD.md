# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets. Operates three strategies:
1. **Crypto Sniper** — Primary profit driver. Trades BTC/ETH up/down markets using Binance real-time price feeds.
2. **Weather Trader** — Trades temperature/weather outcome markets using Open-Meteo forecasts.
3. **Arb Scanner** — Multi-outcome arbitrage across weather and other markets.

## Core Architecture
- **Backend**: FastAPI + MongoDB, manages engine state, strategies, risk, positions
- **Frontend**: React dashboard for monitoring and configuration
- **External Data**: Binance WebSocket (BTC/ETH), Open-Meteo (weather), Polymarket Gamma API + CLOB WebSocket
- **Notifications**: Telegram bot for trade alerts, performance reports

## Current Configuration (Post Live Patch + Audit, Mar 20 2026)

### Risk Config (Hard-pinned at startup)
- max_position_size: 25
- crypto_max_exposure: $250
- arb_max_exposure: $8 (minimal sandbox)
- arb_reserved_capital: $8
- weather_reserved_capital: $15 (guaranteed allocation floor)
- max_arb_positions: 5
- weather_max_exposure: $120
- max_market_exposure: $360

### Shadow Sniper (NO LIVE EXECUTION)
- Unit-size: $3/signal, no accumulation, NOT live-equivalent
- EV-gap filter: min_ev_ratio = 0.04 (4%)
- Pseudo-Stoikov: gamma=0.1, inventory_decay=0.8
- Resolution: Waits for binary outcome (price near 0 or 1), NOT mark-to-market
- FP/FN: Computed at resolution time based on shadow-vs-live disagreement
- Agreement rate: Meaningful-only (excludes trivial both-skip evaluations)
- API: /api/shadow/report, /evaluations, /positions, /closed

### PnL Accounting (Audited Mar 20 2026)
- Overview PnL chart = ALL-strategy cumulative realized PnL (includes "unknown" trades)
- Strategy pages = Per-strategy attributed PnL only
- Difference = orphaned "unknown" trades (not attributable to any named strategy)
- Shadow data is fully isolated — does NOT affect live Overview, PnL, or positions

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
15. Quant Lab page — Full shadow monitoring dashboard (Mar 20)
16. Sniper page shadow summary (Mar 20)
17. Shadow accounting audit fixes (Mar 20):
    - Binary resolution (waits for 0/1, not mid-market)
    - FP/FN wired up correctly
    - Meaningful agreement rate split
    - Size/Notional columns added
    - Unit-size labeling throughout UI

## Testing Status
- iteration_68.json: Forensic Rollback — 18/18 (100%)
- iteration_69.json: Shadow Sniper + Config Hard-Pin — 26/26 (100%)
- iteration_70.json: Quant Lab UI + Shadow Summary — 11/11 (100%)
- iteration_71.json: Shadow Correctness Audit — 19/19 (100%)

## Backlog

### P1 — Active Monitoring
- Monitor shadow vs live at /quant-lab as binary resolutions accumulate
- Watch Telegram 2h/6h reports for crypto PnL recovery
- Observe FP/FN metrics as they populate

### P2 — Planned
- If shadow binary win rate proves better, promote EV-gap + Stoikov to live
- Increase crypto_max_exposure once crypto proves cap-bound
- Add weather observations API
- Add Coinbase WebSocket
- Re-evaluate asymmetric weather mode

### P3 — Future
- XRP/SOL support
- Trailing stop-loss
- Regime detection
- Resolution Timeline visualization
- Copy Trading / Manual Order Entry
