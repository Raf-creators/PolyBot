# Polymarket Edge OS — Product Requirements

## Problem Statement
A full-stack Polymarket trading bot (FastAPI + React + MongoDB) that executes paper trades across crypto, weather, and arbitrage strategies with real-time dashboards.

## Architecture
- **Backend**: FastAPI (port 8001), Motor/MongoDB
- **Frontend**: React (port 3000), Shadcn UI
- **DB**: MongoDB (`test_database`)
- **Strategies**: `crypto_sniper`, `weather_trader`, `weather_asymmetric`, `arb_scanner`
- **3rd Party**: Polymarket Gamma/CLOB APIs, Open-Meteo, Telegram

## Completed Work

### Core Infrastructure
- Engine with paper trading adapter, market discovery, price feeds, risk management, Telegram alerts

### Weather V2 + Asymmetric + Calibration
- Overtrading filter, quality score, multi-market types, asymmetric hold-to-resolution
- Sigma widening, Brier score, auto-tune framework (disabled by default)

### Position Lifecycle Management
- **Modes**: OFF, TAG_ONLY (default), SHADOW_EXIT, AUTO_EXIT
- **Exit rules**: Profit capture, Negative edge, Edge decay, Time inefficiency, Slot rotation
- **Lifecycle Dashboard**: Summary cards, reason distribution, shadow timeline, sold-vs-held comparison
- **Threshold Simulator**: 5 sliders, 3 presets, decision quality metrics
- **Mode Control**: Segmented UI with confirmation modals

### Entry Quality Tightening
- Min quality score (0.35), time-aware edge filter, long-hold penalty, signal ranking, observability

### Slot Rotation / Inventory Cleanup
- Book-level ranking, SLOT_ROTATION exit reason, configurable thresholds

### UI Snapshot Export
- Export Snapshot + Copy to Clipboard buttons in Lifecycle Dashboard
- Internal endpoint `/api/debug/ui-snapshot` (no key)
- Keyed endpoint `/api/debug/state-snapshot` (X-Debug-Snapshot-Key)

### Edge & Resolution Data Pipeline Fix (March 18)
- Persistent `_position_meta` dict for entry edge/weather context
- `endDateIso` from Gamma API → MarketSnapshot.end_date
- Bootstrap mechanism from classified markets for legacy positions
- target_date fallback for hours_to_resolution

### Global System Snapshot v2.0 (March 18)
- Restructured from weather-biased flat layout to balanced hierarchy:
  ```
  { freshness, portfolio, strategies: { weather, weather_asymmetric, crypto, arb } }
  ```
- **Portfolio section**: total_capital_deployed, capital_allocation (per-strategy % + counts), pnl_by_strategy (realized, win_rate, sharpe, profit_factor), concentration_risk (HHI, top_3_pct, largest_position)
- **Equal-depth strategy sections**: Each strategy has positions, scan_health, config + strategy-specific data (lifecycle/entry_quality for weather, execution_stats/volatility for crypto, diagnostics for arb)
- **Enriched positions**: All positions now include invested, current_value, profit_multiple. Crypto positions have strategy_meta (asset, time_window). Arb positions have strategy_meta (market_type)

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/positions/by-strategy | GET | Positions with lifecycle + book rank |
| /api/positions/weather/exit-candidates | GET | Exit candidates + config |
| /api/positions/weather/lifecycle | GET | Full lifecycle evals |
| /api/positions/weather/lifecycle/dashboard | GET | Dashboard data |
| /api/positions/weather/lifecycle/simulate | POST | Simulate thresholds |
| /api/strategies/weather/lifecycle/mode | POST | Switch lifecycle mode |
| /api/strategies/weather/entry-quality | GET | Entry quality metrics |
| /api/debug/ui-snapshot | GET | Global system snapshot v2 (no key) |
| /api/debug/state-snapshot | GET | Global system snapshot v2 (keyed) |

## Prioritized Backlog
### P0: VALIDATION PHASE — observe TAG_ONLY with working edge/resolution data
### P1: Enable SHADOW_EXIT, evaluate all exit paths with real data
### P2: Resolution Timeline visualization
### P3: Copy Trading Skeleton
### P4: Manual Order Entry
### P5: UI toggle for auto-tune sigma multiplier
### P6: Live Trading Mode Integration

## Audit Findings (from live snapshot March 18)
- 4/5 lifecycle exit rules now active (edge_decay inert for legacy positions)
- 10 exit candidates correctly identified across 3 rules
- March 17 zombie positions (6 weather + 6 arb) not resolving — blocks capital recycling
- Quality floor (0.35) too lenient — 0 rejections
- Consider adding "market_collapse" exit rule for positions at <5% entry value
- Singapore profit_capture may be premature when remaining edge is high
