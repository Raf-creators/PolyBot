# Polymarket Edge OS — PRD

## Current Epoch: EPOCH 5 (Analysis Upgrade)
- **Started**: 2026-03-21 ~01:52 UTC | **Balance**: $1,000.00 starting
- **Tier 1+2 Upgrades Applied**: 2026-03-21 ~14:25 UTC

## Live Strategies
1. **Crypto Sniper** — Kelly sizing ($12/$18/$25/$35), min_edge=400bps, regime detector, 30s cooldown
2. **Gabagool Live Arb** — YES+NO when sum < $0.96, $10/side, 20 max pairs, 2% resolution fee accounted
3. **Arb Scanner** — Multi-outcome structural arb (RESTRICTED: $40 cap, 12 positions)
4. **Weather Trader** — $8 sizing, shadow_exit mode, profit_capture at 1.5x

## Key Config (Post-Analysis Upgrade)
- max_position_size: 35 | max_order_size: 35
- crypto_max_exposure: $150 | arb_max_exposure: $40 | arb_reserved: $40
- max_arb_positions: 12 | max_daily_loss: $150
- Gabagool: threshold 0.960, 20 pairs, $10/side
- Crypto cooldown: 30s (from 60s)
- Weather profit_capture: 1.5x (from 2.0x)
- Kelly tiers: $12 (>=400bps), $18 (>=600bps), $25 (>=900bps), $35 (>=1200bps)
- Window caps: 5m=12, 15m=22, 1h=30

## Shadow Systems
EV-Gap/Stoikov, MoonDev, Phantom, Whrrari (active) | Marik, Argona (scaffolded)

## Testing: iterations 76-79 all pass
- iter79: 24/24 backend, 10/10 frontend (Tier 1+2 upgrades verified)

## What Was Implemented (2026-03-21)
- Deep overnight analysis of snapshot-2026-03-21-1333.json (10h runtime, $142.79 PnL)
- Tier 1: crypto_max_exposure 80→150, max_position_size 25→35, arb restricted 250→40, Gabagool threshold 0.985→0.960
- Tier 2: weather profit_capture 2.0→1.5, crypto cooldown 60→30, daily loss limit 100→150
- New $35 Kelly tier for >=1200bps edge signals
- Window caps raised: 5m=12, 15m=22, 1h=30
- Full analysis report saved to /app/memory/EPOCH5_OVERNIGHT_ANALYSIS.md

## Backlog
- P1: Marik + Argona shadow activation
- P1: MoonDev investigation (shadow strategy)
- P2: More crypto APIs (beyond Binance WS), XRP/SOL expansion
- P3: Trailing stop-loss, regime expansion
- P3: Cross-asset correlation strategy (BTC-ETH divergence)
- P3: Volume-weighted signal boost (Polymarket order flow)
- P3: Time-of-day optimization (Asian/EU/US session adjustments)
