# Polymarket Edge OS — PRD

## Original Problem Statement
Build an autonomous trading engine that identifies and exploits pricing inefficiencies on Polymarket across weather, crypto, and arbitrage markets. Paper-trading mode with real market data.

## Core Architecture
- **Backend**: FastAPI + MongoDB + Motor (async)
- **Frontend**: React + Shadcn/UI
- **Strategies**: `weather_trader`, `crypto_sniper`, `arb_scanner` (asymmetric disabled)
- **Services**: market_resolver, auto_resolver, persistence, analytics, telegram_notifier, rolling_pnl

## What's Been Implemented

### Rolling PnL Window System (March 19, 2026)
- **NEW**: `services/rolling_pnl.py` — computes PnL/hour over 1h, 3h, 6h windows from trade timestamps
- Replaced ALL uptime-based PnL/h calculations across entire codebase
- Per-strategy breakdown: crypto, weather, arb, total
- Integrated into: Telegram digest, upgrade tracking messages, `/api/admin/upgrade-tracking`, `/api/debug/ui-snapshot` (portfolio.rolling_pnl)
- Format: `{pnl_per_hour, trades, trades_per_hour}` for each window/strategy combo

### Profitability Upgrade Rollout (March 19, 2026)
- Removed opposite_side_held filter for crypto (+11.7% signals unblocked)
- crypto_max_exposure: $120->$180, max_position_size: 25->40, TTE 8h->12h
- Weather: auto_exit for negative_edge + time_inefficiency, min_edge_bps_long 700->500
- Arb: 28 tiny positions cleaned, staleness 1800->2400s
- Asymmetric strategy disabled
- Telegram baseline/tracking system with periodic 2h updates

### Previous Implementations
- Hybrid staleness-adjusted arb execution
- Critical arb engine rewrite (binary + multi-outcome, all Polymarket categories)
- System upgrade (per-strategy capital, shadow exit, zombie resolver, PnL attribution)

## Key API Endpoints
- `GET /api/admin/upgrade-tracking` — Rolling PnL windows (1h/3h/6h) per strategy + system status
- `GET /api/debug/ui-snapshot` — Full snapshot with portfolio.rolling_pnl
- `GET /api/admin/upgrade-validation` — System validation
- `GET /api/strategies/arb/diagnostics` — Arb raw edges, rejections, dynamic thresholds

## Prioritized Backlog
### P1
- Event-driven Telegram alerts (per-trade for large wins/losses)
- Monitor upgrade impact via 6h final report

### P2
- "Apply These Thresholds" workflow
- Resolution Timeline visualization

### P3
- Copy Trading Skeleton
- Manual Order Entry

## Test Reports
- iteration_67.json: Rolling PnL Windows — 17/17 passed (100%)
- iteration_66.json: Profitability Upgrade — 25/25 passed (100%)
- iteration_65.json: Dynamic Threshold — 25/25 passed (100%)
- iteration_64.json: Arb Engine Rewrite — 30/30 passed (100%)
