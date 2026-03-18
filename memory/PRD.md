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

### Weather V2 + Asymmetric + Calibration (March 17)
- Overtrading filter, quality score, multi-market types
- Asymmetric hold-to-resolution strategy (unchanged)
- Sigma widening, Brier score, auto-tune framework (disabled by default)
- PnL attribution fix, resolution time visibility

### Position Lifecycle Management (March 17-18)
- **Modes**: OFF, TAG_ONLY (default), SHADOW_EXIT, AUTO_EXIT
- **Exit rules**: Profit capture (2.0x), Negative edge (-100bp), Edge decay (60%), Time inefficiency (18h/300bp)
- **Lifecycle Dashboard**: Summary cards, reason distribution, time buckets, shadow timeline, sold-vs-held comparison
- **Threshold Simulator**: 5 sliders, 3 presets, per-reason performance, decision quality
- **Mode Control**: Segmented UI with confirmation modals, MongoDB persistence

### Standard Weather Entry Quality Tightening (March 18)
- Min quality score (0.35), time-aware edge filter (700bp for >24h), long-hold penalty
- Composite signal ranking with time-to-resolution preference
- Entry quality observability: rejection counters, avg quality/edge/lead

### Slot Rotation / Inventory Cleanup (March 18)
- **New exit reason**: `SLOT_ROTATION` — flags weak long-dated positions blocking better signals
- **Book-level ranking**: All positions scored by composite (edge 40% + profit 35% + time preference 25%)
- **UI**: Slot Rotations count card, Rank column, EXIT: Slot Rotation badge (cyan)
- **Asymmetric**: NEVER ranked or flagged for slot rotation

### UI Snapshot Export (March 18)
- **Export Snapshot button** in Lifecycle Dashboard — downloads `snapshot-YYYY-MM-DD-HHMM.json`
- **Copy to Clipboard button** for quick sharing
- **Internal endpoint** `/api/debug/ui-snapshot` (no key required)
- **Keyed endpoint** `/api/debug/state-snapshot` preserved for external access

### Edge & Resolution Data Pipeline Fix (March 18) — CRITICAL BUG FIX
- **Root cause**: Position metadata (edge, resolution time, weather context) was stored only in transient signal/execution lists that get evicted after ~300 items. All lifecycle exit rules except profit_capture were effectively disabled.
- **Fix 1**: Persistent `_position_meta` dict stores edge_at_entry, condition_id, station_id, target_date when signals execute — survives signal list eviction
- **Fix 2**: `endDateIso` from Gamma API now passed through to `MarketSnapshot.end_date`
- **Fix 3**: Bootstrap mechanism rebuilds `_position_meta` from `_classified` market data for pre-existing positions
- **Fix 4**: `target_date` fallback derives `hours_to_resolution` when `market.end_date` unavailable
- **Result**: 39/54 positions now have real edge + resolution data. Exit candidates went from 2 (profit_capture only) to 26 (22 time_inefficiency + 2 negative_edge + 2 profit_capture)

## Key Endpoints
| Endpoint | Method | Description |
|---|---|---|
| /api/positions/by-strategy | GET | Positions with lifecycle + book rank |
| /api/positions/weather/exit-candidates | GET | Exit candidates + config |
| /api/positions/weather/lifecycle | GET | Full lifecycle evals with book ranking |
| /api/positions/weather/lifecycle/dashboard | GET | Dashboard with slot rotation counts |
| /api/positions/weather/lifecycle/simulate | POST | Simulate thresholds + slot rotation |
| /api/strategies/weather/lifecycle/mode | POST | Switch lifecycle mode |
| /api/strategies/weather/entry-quality | GET | Entry quality + rejection metrics |
| /api/debug/ui-snapshot | GET | UI-facing state snapshot (no key) |
| /api/debug/state-snapshot | GET | Keyed state snapshot (X-Debug-Snapshot-Key) |

## Prioritized Backlog
### P0: VALIDATION PHASE — observe TAG_ONLY with working edge/resolution data
### P1: Enable SHADOW_EXIT, evaluate all exit paths with real data
### P2: Resolution Timeline visualization (useful for validation)
### P3: Copy Trading Skeleton
### P4: Manual Order Entry
### P5: UI toggle for auto-tune sigma multiplier
### P6: Live Trading Mode Integration
