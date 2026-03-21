# Polymarket Edge OS — PRD

## Current Epoch: EPOCH 5 (Analysis + Shadow Expansion)
- **Started**: 2026-03-21 ~01:52 UTC | **Balance**: $1,000.00 starting
- **Tier 1+2 Upgrades Applied**: 2026-03-21 ~14:25 UTC
- **Wave 2 Shadows Deployed**: 2026-03-21 ~19:28 UTC
- **Current Balance**: $1,318.10 (+$318.10 PnL)

## Live Strategies
1. **Crypto Sniper** — Kelly sizing ($12/$18/$25/$35), min_edge=400bps, regime detector, 30s cooldown
2. **Gabagool Live Arb** — YES+NO when sum < $0.96, $10/side, risk bypass for arb caps
3. **Arb Scanner** — Multi-outcome structural arb (RESTRICTED: $40 cap, 12 positions)
4. **Weather Trader** — $8 sizing, shadow_exit mode, profit_capture at 1.5x

## Key Config
- max_position_size: 35 | max_order_size: 35
- crypto_max_exposure: $150 | arb_max_exposure: $40
- max_arb_positions: 12 | max_daily_loss: $150
- Gabagool: threshold 0.960, bypasses arb position/exposure caps
- Kelly tiers: $12 (>=400bps), $18 (>=600bps), $25 (>=900bps), $35 (>=1200bps)
- Window caps: 5m=12, 15m=22, 1h=30
- Crypto cooldown: 30s | Weather profit_capture: 1.5x

## Shadow Strategies (Quant Lab)
### Wave 1 (Active)
- EV-Gap + Stoikov (comparison engine)
- MoonDev 5m/15m (short-window shadow)
- Phantom Spread (spread analysis + shadow Gabagool)
- Whrrari LMSR (market-maker model)

### Wave 2 (NEW — Active, Collecting Data)
- **Smart Exit** — Trailing profit capture (1.5x activation, 75% of peak floor). Compares vs hold-to-resolution.
- **Altcoin Sniper (SOL/XRP)** — Independent shadow tracking for SOL and XRP markets. Binance WS feeds live.
- **Adaptive Edge** — Vol-scaled min_edge (high vol=350bps, med=400bps, low=500bps) + Dynamic Gabagool thresholds by window (5m=0.975, 15m=0.970, 1h=0.965, 4h=0.960)

### Wave 3 (Planned)
- Marik Latency Execution (scaffolded)
- Argona Macro Event (scaffolded)

## Price Feeds
- Binance WS: BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT (all live)
- Polymarket: CLOB WebSocket + Gamma API
- Open-Meteo: Weather forecasts

## Testing: iterations 76-80 all pass
- iter80: 33/33 backend, 8/8 frontend (Wave 2 shadows verified)

## What Was Implemented (2026-03-21)
### Phase 1: Tier 1+2 Profit Upgrades
- Deep overnight analysis of snapshot (10h, $142.79 PnL)
- crypto_max_exposure 80→150, max_position_size 25→35, arb restricted 250→40
- Gabagool threshold 0.985→0.960
- Weather profit_capture 2.0→1.5, crypto cooldown 60→30, daily loss limit 100→150
- New $35 Kelly tier for >=1200bps edge

### Phase 2: Shadow Strategy Expansion
- Smart Exit trailing stop shadow (1.5x activation, 75% floor)
- SOL/XRP Binance WS price feeds + Altcoin shadow sniper
- Adaptive Edge vol-scaled min_edge shadow
- Dynamic Gabagool threshold shadow (per-window thresholds)
- Gabagool risk bypass (bypasses arb position/exposure caps)
- Fixed Gabagool approve_order→check_order method name
- Updated Quant Lab UI with 3 new tab components
- Asset classifier expanded: SOL/Solana, XRP/Ripple patterns
- All regex patterns updated for 4-asset support

## Backlog
- P1: Promote Smart Exit to live (once data proves trailing > hold)
- P1: Promote SOL/XRP to live (once market surface area confirmed)
- P1: Promote Adaptive Edge to live (once vol-scaling shows improvement)
- P2: Marik + Argona shadow activation
- P2: Cross-asset correlation strategy (BTC-ETH divergence)
- P2: Volume-weighted signal boost (Polymarket order flow)
- P3: Time-of-day optimization (Asian/EU/US sessions)
- P3: Trailing stop for live positions (if Smart Exit shadow proves it)
