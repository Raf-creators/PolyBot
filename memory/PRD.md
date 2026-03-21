# Polymarket Edge OS — PRD

## Original Problem Statement
Multi-strategy automated trading system for Polymarket prediction markets.

## Current Epoch: EPOCH 4
- **Started**: 2026-03-20 ~23:42 UTC
- **Starting Balance**: $1,000.00

## Core Architecture
- **Backend**: FastAPI + MongoDB
- **Frontend**: React dashboard
- **External Data**: Binance WS, Open-Meteo, Polymarket Gamma + CLOB WS
- **Notifications**: Telegram (hourly streaks, 2h reports, 3h digests, **12h deep analysis**)

## Live Strategies
- **Crypto Sniper**: Dynamic Kelly sizing ($5/$12/$18/$25 by edge, max_signal_size=25), window caps (5m=10, 15m=18, 1h=22), dislocation filter (<3% = rejected), anti-clustering
- **Arb Scanner**: Multi-outcome structural arbitrage (sandbox mode)
- **Weather Trader**: Temperature prediction markets

## Shadow Systems (ALL Shadow-Only)
1. **EV-Gap + Stoikov** — Dual-mode: Unit-Size + Live-Equivalent
2. **MoonDev Short Window** — 5m/15m crypto shadow
3. **Phantom Spread** — YES+NO dislocation + **Gabagool both-sides** arb (100% win rate on 4 pairs)
4. **Whrrari Fair-Value / LMSR** — 3 sizing modes
5. **Marik Latency Execution** — Scaffolded/planned
6. **Argona Macro Event** — Scaffolded/planned

## Telegram Notification Schedule
- **Per trade**: Closed trade alerts with PnL
- **1h**: Hourly win/streak updates
- **2h**: Bihourly full performance reports
- **3h**: System digests with rolling PnL windows
- **12h**: Deep analysis with learnings, suggestions, and relay-ready insights
- **On-demand**: POST /api/telegram/trigger-12h-analysis

## What Has Been Implemented
1-26. (See CHANGELOG.md)
27. **max_signal_size increased to 25** (Mar 21) — Unlocks full Kelly tiers
28. **12h Deep Telegram Analysis** (Mar 21) — Comprehensive trade analysis with insights, suggestions, pattern detection

## Testing Status
- iteration_76: Sanity Check Audit — 50/50
- iteration_77: max_signal_size + 12h Analysis — 23/23

## Backlog
### P1
- Activate Marik Latency Execution shadow
- Activate Argona Macro Event shadow
- Weather strategy focus (user interest)
### P2
- Additional crypto API feeds
- XRP/SOL expansion
### P3
- Trailing stop-loss, regime detection, copy trading
