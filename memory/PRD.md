# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets.

## Current Epoch: EPOCH 5
- **Started**: 2026-03-21 ~01:52 UTC
- **Starting Balance**: $1,000.00
- **Purpose**: Overnight run — Gabagool live + Kelly unlocked + regime detector

## Core Architecture
- **Backend**: FastAPI + MongoDB
- **Frontend**: React dashboard
- **External Data**: Binance WS, Open-Meteo, Polymarket Gamma + CLOB WS
- **Notifications**: Telegram (hourly streaks, 2h reports, 3h digests, 12h deep analysis)

## Live Strategies
1. **Crypto Sniper** — Dynamic Kelly sizing ($12/$18/$25 by edge, min_edge=400bps, $5 tier killed), window caps (5m=10, 15m=18, 1h=22), dislocation filter, anti-clustering, **regime detector** (auto-doubles min_edge when WR < 30%)
2. **Gabagool Live Arb** — NEW: buys YES+NO when sum < $0.96 for guaranteed structural arb. $10/side, max 6 pairs. Risk-free profit on resolution. Classified as "arb" bucket.
3. **Arb Scanner** — Multi-outcome structural arbitrage (sandbox mode)
4. **Weather Trader** — Temperature markets, sizing pushed to $8, min_edge=300bps, min_confidence=0.40

## Shadow Systems
1. **EV-Gap + Stoikov** — Dual-mode: Unit-Size + Live-Equivalent
2. **MoonDev Short Window** — 5m/15m crypto shadow
3. **Phantom Spread** — YES+NO dislocation + Gabagool both-sides (100% WR on 4 pairs in Epoch 4)
4. **Whrrari Fair-Value / LMSR** — 3 sizing modes
5. **Marik Latency Execution** — Scaffolded/planned
6. **Argona Macro Event** — Scaffolded/planned

## Telegram Notification Schedule
- Per trade, 1h streaks, 2h reports, 3h digests, **12h deep analysis**
- On-demand: POST /api/telegram/trigger-12h-analysis

## Key Risk Config (Epoch 5)
- max_order_size: 25 (was 10 — unblocked Kelly tiers)
- arb_max_exposure: $60 (was $8 — Gabagool capital)
- max_arb_positions: 15 (was 5 — Gabagool pairs need 2 positions each)
- weather_position_size: $8 (was $3)
- weather_reserved_capital: $30

## Testing Status
- iteration_76: Full audit — 50/50
- iteration_77: Kelly + 12h analysis — 23/23
- iteration_78: Gabagool + Kelly unlock + regime + weather — 37/37

## Backlog
### P1
- Activate Marik Latency + Argona Macro shadow engines
- Weather strategy deep-dive (user interest)
- MoonDev investigation: why profitable on same windows as live sniper?
### P2
- Additional crypto API feeds
- XRP/SOL expansion
### P3
- Trailing stop-loss, regime detection expansion, copy trading
