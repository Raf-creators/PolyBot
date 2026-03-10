# Polymarket Edge OS — PRD

## Problem Statement
Build a production-grade 24/7 automated trading platform for Polymarket markets. Priorities: structural arbitrage, fast crypto markets (BTC/ETH 5m/15m), research modules. Latency-sensitive architecture with professional dashboard.

## Architecture
- **Frontend**: React SPA (dark-mode trading dashboard)
- **Backend**: FastAPI (async Python)
- **Database**: MongoDB (via Motor async driver)
- **Trading Engine**: Single-process async Python with StateManager + EventBus
- **Hot/Cold Path Separation**: Trading logic in-memory, dashboard reads via snapshots

## User Personas
- **Quant Trader**: Configures strategies, monitors P&L, manages risk
- **System Operator**: Monitors health, manages kill switch, reviews logs

## Core Requirements
- Structural arbitrage on binary Polymarket markets
- Fast crypto market trading (BTC/ETH 5m/15m)
- Paper / Shadow / Live trading modes
- Risk engine with kill switch, position limits, daily loss limits
- Professional dark-mode dashboard (6 pages)
- Telegram alerts (credentials-ready)
- Polymarket CLOB integration via py-clob-client SDK
- Binance WebSocket for spot price feeds

## What's Been Implemented

### Phase 1 — Backend Skeleton & Engine Scaffolding (2026-03-10)
- `models.py`: All Pydantic models (enums, data models, config, events, API models)
- `engine/state.py`: StateManager — single source of truth, pub/sub, snapshot for dashboard
- `engine/events.py`: EventBus — asyncio.Queue-backed, typed channels, handler registration
- `engine/core.py`: TradingEngine — orchestrator, component lifecycle management
- `engine/risk.py`: RiskEngine — order validation, kill switch, limit enforcement
- `engine/execution.py`: ExecutionEngine — order routing to paper/live adapters
- `engine/paper.py`: PaperAdapter — simulated fills for paper mode
- `engine/strategies/base.py`: BaseStrategy ABC
- `server.py`: FastAPI with 15+ endpoints (status, engine control, config, risk, trades, positions, orders, markets)
- `.env`: All credential placeholders (Polymarket, Telegram, trading mode)
- **Testing**: 23/23 backend tests passed (100%)

## Prioritized Backlog

### P0 — Next (Phase 2) ✅ COMPLETED
- ✅ Market data ingestion (Polymarket Gamma API, 200 markets)
- ✅ Binance WebSocket for BTC/ETH spot prices
- ✅ Risk engine: total exposure check + all limit enforcement
- ✅ Paper execution with latency tracking
- ✅ Async write-behind persistence to MongoDB
- ✅ WebSocket endpoint `/api/ws` for frontend real-time data
- ✅ Health metrics and feed staleness detection
- **Testing**: 17/17 tests passed (100%)

### Phase 2 Implementation Details (2026-03-10)
- `engine/market_data.py`: Gamma API discovery + CLOB midpoint refresh
- `engine/price_feeds.py`: Binance WS with auto-reconnect + staleness monitor
- `services/persistence.py`: 10s flush interval, off the hot path
- `server.py`: WebSocket hub (2s broadcast), /api/markets/summary, /api/health/feeds

### P0 — Next (Phase 3) ✅ COMPLETED
- ✅ Binary complement arbitrage scanner with full edge computation
- ✅ Composable pricing models: fees, slippage, execution penalty, confidence scoring
- ✅ Paired YES+NO paper execution with lifecycle tracking
- ✅ Cooldown deduplication (120s per condition_id)
- ✅ Pre-flight risk checks + kill switch gating
- ✅ Position + trade context (market_question, outcome) populated
- ✅ API: /api/strategies/arb/opportunities, /executions, /health
- ✅ Persistence: arb_opportunities + arb_executions to MongoDB
- **Testing**: 31/32 tests passed (96.9%)

### Phase 3 Implementation Details (2026-03-10)
- `engine/strategies/arb_scanner.py`: Main strategy with scan loop, pair detection, evaluation, execution
- `engine/strategies/arb_models.py`: ArbConfig, ArbOpportunity, ArbExecution, ArbPairStatus
- `engine/strategies/arb_pricing.py`: estimate_fees, estimate_slippage, estimate_execution_penalty, compute_confidence
- `engine/paper.py`: Fixed to populate market_question/outcome on positions and trades
- `server.py`: Arb API endpoints, unique-ID test inject endpoint

### P1 — Next (Phase 4)
- Structural arbitrage strategy (binary complement scanner)
- Arb execution with paired YES+NO orders
- Partial fill protection

### P1 — Phase 4
- Frontend dashboard (6 pages)
- Real-time WebSocket UI integration
- Kill switch in UI

### P2 — Phase 5
- Crypto sniper strategy (BTC/ETH 5m/15m)
- Fair value calculation from spot feeds

### P2 — Phase 6
- Telegram alerts
- Rich analytics
- Config persistence
- Copy trading skeleton
- Weather research placeholder

## Next Tasks
1. Phase 2: Market data + spot feeds + paper execution with real prices
2. Phase 3: Structural arbitrage strategy
3. Phase 4: Frontend dashboard
