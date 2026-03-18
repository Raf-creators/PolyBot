# Polymarket Edge OS — PRD

## Original Problem Statement
Build an autonomous trading engine that identifies and exploits pricing inefficiencies on Polymarket across weather, crypto, and arbitrage markets. The system operates in paper-trading mode with real market data.

## Core Architecture
- **Backend**: FastAPI + MongoDB + Motor (async)
- **Frontend**: React + Shadcn/UI
- **Strategies**: `weather_trader`, `weather_asymmetric`, `crypto_sniper`, `arb_scanner`
- **Services**: market_resolver, auto_resolver, persistence, analytics, telegram_notifier

## Key Config Model
- `RiskConfig`: Global + per-strategy exposure caps, arb reserved capital
- `WeatherTradingConfig`: Lifecycle management, exit rules, model parameters
- `ArbScannerConfig`: Staleness, spread, edge thresholds
- `SniperConfig`: Signal classification, execution parameters

## What's Been Implemented

### Phase 1-4: Critical System Upgrade (March 2026)
1. **Global Capital Configuration**: max_total_exposure=360, per-strategy caps=120 each
2. **Reserved Capital for Arbitrage**: arb_reserved_capital=120, exclusive pool
3. **Per-Strategy Risk Checks**: Refactored risk.py with hierarchical capital management
4. **Crypto Opposite-Side Prevention**: Blocks opening both YES+NO on same market
5. **Force Zombie Resolution**: Auto-resolves positions past end_date + 6h grace
6. **Arb Pipeline Unblocked**: max_stale_age_seconds=300 (was 180)
7. **Weather Asymmetric Fix**: min_model_prob=0.20 (was 0.40)
8. **Market Collapse Exit Rule**: Triggers when position_value/entry_value < 0.05
9. **Shadow Exit Mode**: Lifecycle in shadow_exit, tracking exit candidates
10. **PnL Attribution Fix**: All trades attributed to originating strategy
11. **Validation Endpoint**: /api/admin/upgrade-validation for system health

### Earlier Work
- Position Lifecycle Management system (shadow_exit, tag_only, auto_exit modes)
- UI Dashboard with Weather.jsx
- Lifecycle simulator
- Debug snapshot v2.0 (balanced, all-strategy)
- Edge & Resolution data pipeline fix
- Snapshot export (Export/Copy buttons)

## Prioritized Backlog

### P0 — None (all P0 items resolved)

### P1 — Next Up
- **Enable AUTO_EXIT**: After validating shadow exit results with live data, switch weather lifecycle to auto_exit for profit_capture, negative_edge, time_inefficiency
- **"Apply These Thresholds" Workflow**: Push validated simulator thresholds to live config

### P2
- Resolution Timeline visualization
- UI toggle for auto-tune sigma multiplier

### P3
- Copy Trading Skeleton
- Manual Order Entry

## Key API Endpoints
- `GET /api/admin/upgrade-validation` — System upgrade validation summary
- `GET /api/controls` — Risk controls with exposure data
- `GET /api/positions/weather/lifecycle` — Lifecycle status & config
- `GET /api/positions/weather/exit-candidates` — Exit candidate analysis
- `GET /api/debug/ui-snapshot` — Full system snapshot
- `PATCH /api/config` — Update configuration

## 3rd Party Integrations
- Polymarket Gamma API
- Polymarket CLOB WebSocket
- Open-Meteo API
- Telegram notifications

## Test Reports
- iteration_62.json: Critical System Upgrade — 28/28 passed (100%)
- iteration_61.json: Snapshot v2.0 — all passed
- iteration_60.json: Data Pipeline Fix — all passed
