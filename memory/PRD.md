# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets.

## Current Epoch: EPOCH 2
- **Started**: 2026-03-20T15:24:47 UTC
- **Starting Balance**: $1,000.00
- **Previous Epoch**: 7,444 trades archived to `trades_archive_epoch1`

## Core Architecture
- **Backend**: FastAPI + MongoDB, engine state, strategies, risk, positions
- **Frontend**: React dashboard for monitoring and configuration
- **External Data**: Binance WS, Open-Meteo, Polymarket Gamma + CLOB WS
- **Notifications**: Telegram (2h full report, 1h win/streak, per-trade)

## Configuration (Unchanged)
- max_position_size: 25, crypto_max_exposure: $250
- arb_max_exposure: $8 (sandbox), weather_reserved_capital: $15
- Crypto sniper: max_tte=8h, opposite_side_held=active, min_edge=200bps
- Weather: min_edge=350bps, min_confidence=0.45, lifecycle=shadow_exit
- Stale arb cleanup: 2h interval, 24h threshold

## Shadow Sniper — Dual Mode (NO LIVE EXECUTION)
- **Unit-Size**: $3/signal, no accumulation
- **Live-Equivalent**: $3/signal, accumulates to max 25 shares
- EV-gap (4%), pseudo-Stoikov (gamma=0.1), binary resolution
- API: /api/shadow/report, /evaluations, /positions?mode=unit|le, /closed?mode=unit|le

## What Has Been Implemented
1-18. (See CHANGELOG for full history)
19. **Paper Performance Reset / Epoch 2** (Mar 20 2026)
    - Archived 7,444 trades, 6,032 orders, 1 position snapshot to `*_archive_epoch1`
    - Cleared live collections, reset in-memory state
    - Epoch marker in MongoDB (idempotent — runs once only)
    - Fixed paperBalance computation: uses `pnlHistory.current_pnl` (survives restarts)
    - Bot continues under same configuration with clean $1,000 baseline
20. **Anti-Clustering Fix for Crypto Sniper** (Mar 20 2026)
    - Added position-cap pre-check in `_evaluate_signal()`: skips markets where YES or NO token already at max_position_size - 1
    - Prevents wasted scan cycles sending doomed orders to risk engine
    - New `position_capped` metric exposed in `/api/strategies/sniper/health`
    - Confirmed active: metric incrementing in production

## Testing Status
- iteration_68: Forensic Rollback — 18/18
- iteration_69: Shadow + Config — 26/26
- iteration_70: Quant Lab UI — 11/11
- iteration_71: Shadow Audit — 19/19
- iteration_72: Dual-Mode Shadow — 27/27
- iteration_73: Epoch Reset — 25/25 (14 backend + 11 frontend)

## Backlog

### P0 — Completed
- Anti-clustering fix for crypto sniper (position_capped pre-check)

### P1 — Active Monitoring (Epoch 2)
- Monitor crypto PnL/h recovery under clean baseline with anti-clustering active
- Compare dual-mode shadow (Unit vs LE) as positions binary-resolve
- Watch FP/FN metrics populate
- Arb legacy positions draining naturally (no force-close needed)

### P1 — Proposed (User Approval Needed)
- Weather asymmetric as shadow-only / telemetry-only (hypothetical signal count + PnL, no live orders)

### P2 — Planned
- Promote EV-gap + Stoikov if shadow proves superior
- Increase crypto_max_exposure once cap-bound proven
- Weather observations API, Coinbase WebSocket
- Re-evaluate asymmetric weather for live after shadow data collected

### P3 — Future
- XRP/SOL, trailing stop-loss, regime detection
- Resolution Timeline visualization
- Copy Trading / Manual Order Entry
