# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets. Operates three strategies:
1. **Crypto Sniper** — Primary profit driver. Trades BTC/ETH up/down markets using Binance real-time price feeds.
2. **Weather Trader** — Trades temperature/weather outcome markets using Open-Meteo forecasts.
3. **Arb Scanner** — Multi-outcome arbitrage (minimal sandbox).

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

### Shadow Sniper — Dual Mode (NO LIVE EXECUTION)
Two parallel evaluation modes, both fully isolated:

**Unit-Size Mode:**
- $3/signal, one entry per market, no accumulation
- Clean normalized research comparison
- Useful for signal quality evaluation

**Live-Equivalent Mode:**
- $3/signal, accumulates up to max_position_size (25) per market
- Same sizing/accumulation/cap path as live sniper
- VWAP average entry across multiple fills
- Useful for estimating real portfolio impact

**Shared:**
- EV-gap filter: min_ev_ratio = 0.04 (4%)
- Pseudo-Stoikov: gamma=0.1, inventory_decay=0.8
- Binary resolution (waits for price near 0/1)
- FP/FN computed at resolution time
- API: /api/shadow/report, /evaluations, /positions?mode=unit|le, /closed?mode=unit|le

### PnL Accounting
- Overview PnL chart = ALL-strategy cumulative realized PnL (includes "unknown" trades)
- Strategy pages = Per-strategy attributed PnL only
- Shadow data is fully isolated — does NOT affect live data

## What Has Been Implemented
1-16. (See previous PRD entries)
17. Shadow accounting audit: binary resolution, FP/FN wiring, meaningful agreement rate, size labels (Mar 20)
18. **Dual-mode shadow system**: Unit-Size + Live-Equivalent parallel tracking (Mar 20)
    - LE accumulation with VWAP avg_entry
    - Cap enforcement (max_position_size=25)
    - Tabbed position views (LE Open/Closed, Unit Open/Closed, Evaluations)
    - LE Action column in evaluations (accum/cap_blocked)
    - Dual PnL display on Sniper page shadow summary

## Testing Status
- iteration_68.json: Forensic Rollback — 18/18 (100%)
- iteration_69.json: Shadow + Config Hard-Pin — 26/26 (100%)
- iteration_70.json: Quant Lab UI — 11/11 (100%)
- iteration_71.json: Shadow Correctness Audit — 19/19 (100%)
- iteration_72.json: Dual-Mode Shadow — 27/27 (100%)

## Backlog

### P1 — Active Monitoring
- Monitor dual-mode shadow at /quant-lab as binary resolutions accumulate
- Compare Unit PnL vs LE PnL to assess portfolio-level impact
- Watch FP/FN metrics as they populate

### P2 — Planned
- If LE shadow binary win rate proves better, promote EV-gap + Stoikov to live
- Increase crypto_max_exposure once crypto proves cap-bound
- Add weather observations API
- Add Coinbase WebSocket
- Re-evaluate asymmetric weather mode

### P3 — Future
- XRP/SOL support, trailing stop-loss, regime detection
- Resolution Timeline visualization
- Copy Trading / Manual Order Entry
