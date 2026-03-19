# Polymarket Edge OS — PRD

## Original Problem Statement
Build an autonomous trading engine that identifies and exploits pricing inefficiencies on Polymarket across weather, crypto, and arbitrage markets. The system operates in paper-trading mode with real market data.

## Core Architecture
- **Backend**: FastAPI + MongoDB + Motor (async)
- **Frontend**: React + Shadcn/UI
- **Strategies**: `weather_trader`, `crypto_sniper`, `arb_scanner` (asymmetric disabled)
- **Services**: market_resolver, auto_resolver, persistence, analytics, telegram_notifier

## Key Config Model
- `RiskConfig`: Global $360 cap, crypto $180, weather $120, arb $120 reserved
- `WeatherTradingConfig`: Lifecycle management (shadow_exit + selective auto_exit), min_edge_bps_long=500
- `ArbScannerConfig`: Dynamic staleness-adjusted thresholds, hard_max_stale=2400s
- `SniperConfig`: max_position_size=40, max_tte=43200 (12h), opposite_side filter removed

## What's Been Implemented

### Profitability Upgrade Rollout (March 19, 2026)
**Crypto Throughput Maximization:**
1. Removed `opposite_side_held` filter for crypto_sniper (was blocking 11.7% of signals)
2. Raised crypto_max_exposure: $120 -> $180
3. Raised max_position_size: 25 -> 40 shares
4. Expanded max_tte_seconds: 8h -> 12h

**Weather Capital Recycling:**
5. Enabled auto_exit for `negative_edge` + `time_inefficiency` (in shadow_exit mode)
6. Lowered min_edge_bps_long: 700 -> 500bps

**Arbitrage Cleanup:**
7. Force-resolved 28 tiny arb positions (<$0.50) to free slots
8. Relaxed hard_max_stale: 1800s -> 2400s, staleness_per_min: 5 -> 6 bps/min

**Dead Weight Removal:**
9. Disabled asymmetric strategy (asymmetric_enabled=False)

**Telegram Before/After Tracking:**
10. Baseline capture at deploy (pre-upgrade rates from audit)
11. Deployment notification with all changes listed
12. Periodic 2h comparison updates (crypto PnL/h, trades/h, exec rate, cap util)
13. Final 6h impact report with verdict (improved/declined)
14. New endpoint: `GET /api/admin/upgrade-tracking`

### Previous: Hybrid Staleness-Adjusted Execution (March 2026)
- Dynamic min-edge threshold: `base(15bps) + (age_s/60) * per_min(6bps) + liquidity_buffer`
- Liquidity tiers: deep(>$2000)+0, mid($500-2000)+7.5, thin(<$500)+15 bps
- Hard reject >2400s or liquidity <$200
- First arb executed: 345bps realized edge

### Previous: Critical Arb Engine Rewrite (March 2026)
- Binary vs multi-outcome prioritized pipelines
- True arbitrage condition: sum_of_asks < 1.0 after fees
- All Polymarket categories (2000+ markets, 500+ binary pairs)

### Previous: System Upgrade Phase 1+2 (March 2026)
- Per-strategy capital allocation with reserved pools
- SELL order fast-path, crypto opposite-side cleanup
- Shadow exit system with selective auto-exit
- Zombie resolver, PnL attribution fix
- Telegram periodic digest

## Confirmed Findings
- Binary markets are efficiently priced (no binary arb exists)
- Multi-outcome weather arbs exist but are sparse and stale
- Asymmetric strategy is non-viable (model gives 0-3% prob to all candidates)
- Crypto is 99.6% of all profit — maximizing throughput is the key lever

## Prioritized Backlog

### P0 — None (all critical items resolved)

### P1 — Next Up
- **Event-driven Telegram alerts**: Per-trade alerts for large wins/losses and arb executions
- **Monitor upgrade impact**: Review 6h final report to validate changes

### P2
- "Apply These Thresholds" workflow (simulator -> live config)
- Resolution Timeline visualization
- UI toggle for auto-tune sigma

### P3
- Copy Trading Skeleton
- Manual Order Entry

## Key API Endpoints
- `GET /api/admin/upgrade-tracking` — Live before/after comparison
- `GET /api/admin/upgrade-validation` — Full system validation
- `GET /api/strategies/arb/diagnostics` — Raw edges, rejections, dynamic thresholds
- `GET /api/strategies/arb/performance` — Capital efficiency
- `GET /api/controls` — Risk controls
- `GET /api/positions/weather/lifecycle` — Lifecycle & exits

## Test Reports
- iteration_66.json: Profitability Upgrade — 25/25 passed (100%)
- iteration_65.json: Dynamic Threshold — 25/25 passed (100%)
- iteration_64.json: Arb Engine Rewrite — 30/30 passed (100%)
- iteration_63.json: Critical Expansion — 33/33 passed (100%)
- iteration_62.json: System Upgrade — 28/28 passed (100%)
