# Polymarket Edge OS — PRD

## Current Epoch: EPOCH 5
- **Started**: 2026-03-21 ~01:52 UTC | **Balance**: $1,000.00 starting

## Live Strategies
1. **Crypto Sniper** — Kelly sizing ($12/$18/$25), min_edge=400bps, regime detector
2. **Gabagool Live Arb** — YES+NO when sum < $0.96, $10/side, 20 max pairs, 2% resolution fee accounted
3. **Arb Scanner** — Multi-outcome structural arb
4. **Weather Trader** — $8 sizing, PF=6.47

## Key Config (Epoch 5 Final)
- max_order_size: 25 | arb_max_exposure: $250 | max_arb_positions: 45
- Gabagool: 20 pairs, $10/side, 0.96 threshold, fee-realistic PnL
- Regime detector: doubles min_edge when WR < 30%

## Shadow Systems
EV-Gap/Stoikov, MoonDev, Phantom, Whrrari (active) | Marik, Argona (scaffolded)

## Testing: iterations 76-78 all pass (50/50, 23/23, 37/37)

## Backlog
- P1: Marik + Argona activation, weather deep-dive, MoonDev investigation
- P2: More crypto APIs, XRP/SOL | P3: Trailing stop, regime expansion
