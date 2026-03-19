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
- `ArbScannerConfig`: Universal market scanning, staleness=300s, liquidity=200
- `SniperConfig`: Signal classification, opposite-side prevention

## What's Been Implemented

### Critical System Upgrade Phase 1 (March 2026)
1. Global capital: max_total_exposure=360, per-strategy caps=120 each
2. Reserved capital for arb: arb_reserved_capital=120, exclusive pool
3. Per-strategy risk checks in risk.py (hierarchical capital management)
4. SELL order fast-path (exits never blocked by risk)
5. Crypto opposite-side prevention (new trades) + cleanup (existing positions)
6. Market collapse exit rule (threshold=0.05)
7. Shadow exit mode with selective auto-exit for market_collapse + profit_capture
8. PnL attribution fix (startup migration re-attributes "resolver" trades)

### Critical Expansion Phase 2 (March 2026)
1. Position limits expanded: max_arb=40, max_concurrent=85
2. Zombie resolver: infers expiry from market question text (no end_date dependency)
3. Force-resolved 32+ zombie positions across sessions
4. Universal arb scanner: ALL Polymarket categories (1,800+ markets, 500 binary pairs)
5. Multi-outcome detection for weather + universal markets
6. Arb min_liquidity lowered 500→200
7. Arb max_stale_age_seconds 180→300
8. Weather asymmetric: min_model_prob 0.40→0.20 (CONFIRMED NON-VIABLE)
9. Asymmetric diagnostic logging (candidates_scanned, rejection breakdowns)
10. Telegram periodic digest (every 3h with full PnL/exposure/arb stats)
11. Validation endpoint: /api/admin/upgrade-validation

### Earlier Work
- Position Lifecycle Management system
- UI Dashboard, Simulator, Debug Snapshot v2.0
- Edge & Resolution data pipeline fix

## Confirmed Findings
- **Asymmetric strategy is NON-VIABLE**: Model assigns 0-3% probability to all low-priced weather contracts. 86% of candidates killed by model_prob filter. The strategy's premise (model disagrees with market) doesn't hold for weather multi-outcome markets.
- **Arb slot limit was the real bottleneck**: Not capital. 20 tiny positions ($1 total) blocked $120 of reserved capital.
- **Zombie resolver needs date parsing**: Markets on Polymarket don't consistently provide end_date in API responses.

## Prioritized Backlog

### P0 — None (all P0 items resolved)

### P1 — Next Up
- **Enable full AUTO_EXIT**: After sufficient shadow data, switch time_inefficiency + negative_edge to auto_exit
- **"Apply These Thresholds" Workflow**: Push simulator thresholds to live config
- **Disable asymmetric strategy**: Mark as non-viable, free up compute
- **Monitor arb execution rate**: Track whether 40 slots + 200 liquidity actually produces consistent trades

### P2
- Resolution Timeline visualization
- UI toggle for auto-tune sigma
- Expand Telegram alerts (per-trade notifications for large wins/losses)

### P3
- Copy Trading Skeleton
- Manual Order Entry

## Key API Endpoints
- `GET /api/admin/upgrade-validation` — Full system validation summary
- `GET /api/controls` — Risk controls with per-strategy exposure data
- `GET /api/positions/weather/lifecycle` — Lifecycle status & config
- `GET /api/positions/weather/exit-candidates` — Exit candidate analysis
- `GET /api/debug/ui-snapshot` — Full system snapshot
- `PATCH /api/config` — Update configuration

## 3rd Party Integrations
- Polymarket Gamma API
- Polymarket CLOB WebSocket
- Open-Meteo API
- Telegram

## Test Reports
- iteration_63.json: Critical Expansion — 33/33 passed (100%)
- iteration_62.json: Critical System Upgrade — 28/28 passed (100%)
