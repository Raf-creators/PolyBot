# Polymarket Edge OS — PRD

## Original Problem Statement
Build an autonomous trading engine that identifies and exploits pricing inefficiencies on Polymarket across weather, crypto, and arbitrage markets. The system operates in paper-trading mode with real market data.

## Core Architecture
- **Backend**: FastAPI + MongoDB + Motor (async)
- **Frontend**: React + Shadcn/UI
- **Strategies**: `weather_trader`, `weather_asymmetric`, `crypto_sniper`, `arb_scanner`
- **Services**: market_resolver, auto_resolver, persistence, analytics, telegram_notifier

## Key Config Model
- `RiskConfig`: Global + per-strategy exposure caps ($120 each), arb reserved capital ($120)
- `WeatherTradingConfig`: Lifecycle management (shadow_exit), exit rules, model parameters
- `ArbScannerConfig`: Universal market scanning, dynamic staleness-adjusted thresholds
- `SniperConfig`: Signal classification, opposite-side prevention

## What's Been Implemented

### Hybrid Staleness-Adjusted Execution (March 2026)
1. Dynamic min-edge threshold based on data staleness: fresher data = lower bar
   - Formula: `staleness_bps = base(15) + (age_s / 60) * per_minute(5)`
2. Dynamic liquidity buffer: thinner liquidity = higher edge requirement
   - Tiers: deep(>$2000)=+0bps, mid($500-2000)=+7.5bps, thin(<$500)=+15bps
3. Hard reject for very stale quotes (>1800s) regardless of edge
4. Hard reject for thin liquidity (<$200) regardless of edge
5. Absolute floor: min_net_edge_bps=15 (never trade below this)
6. Enhanced rejection logging: raw_edge, net_edge, stale_age_s, liquidity, dynamic_min_edge_bps, reason
7. Raw edges diagnostics include stale_age_s and liquidity
8. Dynamic threshold sample table in diagnostics endpoint
9. First successful multi-outcome arb execution (London weather, 345bps realized)
10. Startup migration enforces new dynamic threshold params

### Critical Arbitrage Execution Upgrade (March 2026)
1. Rewrote arb_scanner.py with binary vs. multi-outcome prioritized pipelines
2. True arbitrage condition: sum_of_asks < 1.0 after fees
3. Simultaneous multi-leg execution
4. Expanded to ALL Polymarket categories (1,800+ markets, 500 binary pairs)
5. Edge-based position sizing
6. Safety kill-switch on consecutive failures
7. Performance tracking endpoints

### Critical System Upgrade Phase 1 (March 2026)
1. Global capital: max_total_exposure=360, per-strategy caps=120 each
2. Reserved capital for arb: arb_reserved_capital=120, exclusive pool
3. Per-strategy risk checks in risk.py (hierarchical capital management)
4. SELL order fast-path (exits never blocked by risk)
5. Crypto opposite-side prevention + cleanup
6. Market collapse exit rule (threshold=0.05)
7. Shadow exit mode with selective auto-exit for market_collapse + profit_capture
8. PnL attribution fix (startup migration re-attributes "resolver" trades)

### Critical Expansion Phase 2 (March 2026)
1. Position limits expanded: max_arb=40, max_concurrent=85
2. Zombie resolver: infers expiry from market question text
3. Universal arb scanner: ALL Polymarket categories
4. Telegram periodic digest (every 3h)
5. Validation endpoint: /api/admin/upgrade-validation

### Earlier Work
- Position Lifecycle Management system
- UI Dashboard, Simulator, Debug Snapshot v2.0
- Edge & Resolution data pipeline fix

## Confirmed Findings
- **Binary markets are efficiently priced**: YES_ask + NO_ask >= 1.0 across all 500 binary pairs. No binary arb exists.
- **Multi-outcome weather markets have thin arbs**: Edges of 30-300+ bps exist but are often stale.
- **Asymmetric strategy is NON-VIABLE**: Model assigns 0-3% probability to all low-priced weather contracts.
- **Dynamic thresholds validated**: First arb executed with 345bps realized edge (target 187bps).

## Prioritized Backlog

### P0 — None (all P0 items resolved)

### P1 — Next Up
- **Event-driven Telegram alerts**: Per-trade alerts for large wins/losses and arb executions
- **Enable full AUTO_EXIT**: Switch time_inefficiency + negative_edge to auto_exit
- **Disable asymmetric strategy**: Mark as non-viable, free up compute
- **"Apply These Thresholds" Workflow**: Push simulator thresholds to live config

### P2
- Resolution Timeline visualization
- UI toggle for auto-tune sigma
- Expand Telegram alerts (per-trade notifications)

### P3
- Copy Trading Skeleton
- Manual Order Entry

## Key API Endpoints
- `GET /api/admin/upgrade-validation` — Full system validation summary
- `GET /api/strategies/arb/diagnostics` — Raw edges, rejections, dynamic threshold samples
- `GET /api/strategies/arb/performance` — Capital efficiency metrics
- `GET /api/strategies/arb/opportunities` — Tradable/rejected opportunities
- `GET /api/strategies/arb/executions` — Active/completed executions
- `GET /api/controls` — Risk controls with per-strategy exposure data
- `GET /api/positions/weather/lifecycle` — Lifecycle status & config
- `PATCH /api/config` — Update configuration

## 3rd Party Integrations
- Polymarket Gamma API
- Polymarket CLOB WebSocket
- Open-Meteo API
- Telegram

## Test Reports
- iteration_65.json: Hybrid Dynamic Threshold — 25/25 passed (100%)
- iteration_64.json: Critical Arb Upgrade — 30/30 passed (100%)
- iteration_63.json: Critical Expansion — 33/33 passed (100%)
- iteration_62.json: Critical System Upgrade — 28/28 passed (100%)
