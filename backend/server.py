from fastapi import FastAPI, APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
import asyncio
import os
import logging
from pathlib import Path
from typing import Optional, Set

from models import (
    TradingMode, ConfigUpdateRequest, Event, EventType,
    OrderRecord, OrderSide,
)
from engine.state import StateManager
from engine.events import EventBus
from engine.core import TradingEngine
from engine.market_data import MarketDataFeed
from engine.price_feeds import PriceFeedManager
from engine.strategies.arb_scanner import ArbScanner
from engine.strategies.crypto_sniper import CryptoSniper
from services.persistence import PersistenceService

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ['DB_NAME']]

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Engine globals
state: Optional[StateManager] = None
bus: Optional[EventBus] = None
engine: Optional[TradingEngine] = None
arb_scanner_ref: Optional[ArbScanner] = None
crypto_sniper_ref: Optional[CryptoSniper] = None
ws_clients: Set[WebSocket] = set()
ws_broadcast_task: Optional[asyncio.Task] = None


async def _ws_broadcast_loop():
    """Push state snapshots to all connected WebSocket clients every 2 seconds."""
    while True:
        try:
            if ws_clients and state:
                snapshot = state.snapshot()
                dead = set()
                for ws in ws_clients.copy():
                    try:
                        await ws.send_json(snapshot)
                    except Exception:
                        dead.add(ws)
                ws_clients.difference_update(dead)
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global state, bus, engine, arb_scanner_ref, crypto_sniper_ref, ws_broadcast_task

    state = StateManager()
    bus = EventBus()
    engine = TradingEngine(state, bus)

    # Phase 2 components
    engine.market_data = MarketDataFeed()
    engine.price_feeds = PriceFeedManager()
    engine.persistence = PersistenceService(db)

    # Phase 3: register arb strategy (enabled by default)
    arb = ArbScanner()
    engine.register_strategy(arb)
    state.strategies["arb_scanner"].enabled = True
    arb_scanner_ref = arb

    # Phase 5: register crypto sniper strategy (enabled by default)
    sniper = CryptoSniper()
    engine.register_strategy(sniper)
    state.strategies["crypto_sniper"].enabled = True
    crypto_sniper_ref = sniper

    # Trading mode from env
    mode_str = os.environ.get("TRADING_MODE", "paper")
    valid_modes = [m.value for m in TradingMode]
    state.trading_mode = TradingMode(mode_str) if mode_str in valid_modes else TradingMode.PAPER

    # Force paper if no credentials
    if not os.environ.get("POLYMARKET_PRIVATE_KEY"):
        state.trading_mode = TradingMode.PAPER
        logger.info("No Polymarket credentials. Paper mode enforced.")

    # Start WebSocket broadcast
    ws_broadcast_task = asyncio.create_task(_ws_broadcast_loop())

    logger.info(f"Polymarket Edge OS initialized [{state.trading_mode.value}]")

    yield

    # Shutdown
    if ws_broadcast_task:
        ws_broadcast_task.cancel()
        try:
            await ws_broadcast_task
        except asyncio.CancelledError:
            pass
    if engine and engine.is_running:
        await engine.stop()
    mongo_client.close()


app = FastAPI(title="Polymarket Edge OS", version="0.1.0", lifespan=lifespan)
api_router = APIRouter(prefix="/api")


# ---- Health & Status ----

@api_router.get("/")
async def root():
    return {"name": "Polymarket Edge OS", "version": "0.1.0", "status": "online"}


@api_router.get("/health")
async def health():
    return {
        "status": "healthy",
        "engine": state.engine_status.value if state else "uninitialized",
        "mode": state.trading_mode.value if state else "unknown",
    }


@api_router.get("/status")
async def get_status():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return state.snapshot()


# ---- Engine Control ----

@api_router.post("/engine/start")
async def start_engine():
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    if engine.is_running:
        raise HTTPException(400, "Engine already running")
    await engine.start()
    return {"status": "started", "mode": state.trading_mode.value}


@api_router.post("/engine/stop")
async def stop_engine():
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    if not engine.is_running:
        raise HTTPException(400, "Engine not running")
    await engine.stop()
    return {"status": "stopped"}


# ---- Config ----

@api_router.get("/config")
async def get_config():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return {
        "trading_mode": state.trading_mode.value,
        "risk": state.risk_config.model_dump(),
        "strategies": {k: v.model_dump() for k, v in state.strategies.items()},
        "credentials_present": {
            "polymarket": bool(os.environ.get("POLYMARKET_PRIVATE_KEY")),
            "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        },
    }


@api_router.put("/config")
async def update_config(body: ConfigUpdateRequest):
    if not state:
        raise HTTPException(500, "Engine not initialized")
    if body.trading_mode is not None:
        if body.trading_mode != TradingMode.PAPER and not os.environ.get("POLYMARKET_PRIVATE_KEY"):
            raise HTTPException(400, "Cannot switch to live/shadow without Polymarket credentials")
        state.trading_mode = body.trading_mode
    if body.risk is not None:
        state.risk_config = body.risk
    return {"status": "updated"}


# ---- Risk Controls ----

@api_router.post("/risk/kill-switch/activate")
async def activate_kill_switch():
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    await engine.risk_engine.activate_kill_switch(reason="manual_api")
    return {"status": "kill_switch_activated"}


@api_router.post("/risk/kill-switch/deactivate")
async def deactivate_kill_switch():
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    await engine.risk_engine.deactivate_kill_switch()
    return {"status": "kill_switch_deactivated"}


# ---- Positions / Orders / Trades ----

@api_router.get("/positions")
async def get_positions():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return [p.model_dump() for p in state.positions.values()]


@api_router.get("/orders")
async def get_orders():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return [o.model_dump() for o in list(state.orders.values())[-100:]]


@api_router.get("/trades")
async def get_trades():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return [t.model_dump() for t in state.trades[-100:]]


# ---- Markets ----

@api_router.get("/markets")
async def get_markets():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    markets = list(state.markets.values())
    return [m.model_dump() for m in sorted(markets, key=lambda x: x.volume_24h, reverse=True)[:200]]


@api_router.get("/markets/summary")
async def get_markets_summary():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return {
        "total_markets": len(state.markets),
        "top_by_volume": [
            {"question": m.question, "outcome": m.outcome, "mid_price": m.mid_price, "volume_24h": m.volume_24h}
            for m in sorted(state.markets.values(), key=lambda x: x.volume_24h, reverse=True)[:10]
        ],
    }


# ---- Health metrics ----

@api_router.get("/health/feeds")
async def get_feed_health():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return state.health


# ---- Arb Strategy ----

@api_router.get("/strategies/arb/opportunities")
async def get_arb_opportunities(limit: int = 50):
    if not arb_scanner_ref:
        raise HTTPException(500, "Arb scanner not initialized")
    opps = arb_scanner_ref.get_opportunities(limit=limit)
    tradable = [o for o in opps if o.get("is_tradable")]
    rejected = [o for o in opps if not o.get("is_tradable")]
    return {
        "tradable": tradable,
        "rejected": rejected[:limit],
        "total_tradable": len(tradable),
        "total_rejected": len(rejected),
    }


@api_router.get("/strategies/arb/executions")
async def get_arb_executions():
    if not arb_scanner_ref:
        raise HTTPException(500, "Arb scanner not initialized")
    return {
        "active": arb_scanner_ref.get_active_executions(),
        "completed": arb_scanner_ref.get_completed_executions(limit=50),
    }


@api_router.get("/strategies/arb/health")
async def get_arb_health():
    if not arb_scanner_ref:
        raise HTTPException(500, "Arb scanner not initialized")
    return arb_scanner_ref.get_health()


# ---- Crypto Sniper Strategy ----

@api_router.get("/strategies/sniper/signals")
async def get_sniper_signals(limit: int = 50):
    if not crypto_sniper_ref:
        raise HTTPException(500, "Crypto sniper not initialized")
    sigs = crypto_sniper_ref.get_signals(limit=limit)
    tradable = [s for s in sigs if s.get("is_tradable")]
    rejected = [s for s in sigs if not s.get("is_tradable")]
    return {
        "tradable": tradable,
        "rejected": rejected[:limit],
        "total_tradable": len(tradable),
        "total_rejected": len(rejected),
    }


@api_router.get("/strategies/sniper/executions")
async def get_sniper_executions():
    if not crypto_sniper_ref:
        raise HTTPException(500, "Crypto sniper not initialized")
    return {
        "active": crypto_sniper_ref.get_active_executions(),
        "completed": crypto_sniper_ref.get_completed_executions(limit=50),
    }


@api_router.get("/strategies/sniper/health")
async def get_sniper_health():
    if not crypto_sniper_ref:
        raise HTTPException(500, "Crypto sniper not initialized")
    return crypto_sniper_ref.get_health()


@api_router.post("/test/inject-crypto-market")
async def test_inject_crypto_market():
    """Inject a synthetic BTC crypto market pair for testing the sniper pipeline."""
    if not engine or not engine.is_running:
        raise HTTPException(400, "Engine must be running")

    from models import MarketSnapshot
    from datetime import datetime, timezone, timedelta
    import uuid

    uid = uuid.uuid4().hex[:8]
    condition_id = f"test-sniper-{uid}"
    yes_tid = f"test-sniper-yes-{uid}"
    no_tid = f"test-sniper-no-{uid}"

    # Current BTC spot price (if available)
    btc_spot = state.spot_prices.get("BTC", 97000)
    # Set strike slightly below spot so model predicts >50% for Yes
    strike = round(btc_spot * 0.998, 0)
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    time_str = expiry.strftime("%H:%M")

    question = f"Will BTC be above ${strike:,.0f} at {time_str} UTC?"

    state.update_market(yes_tid, MarketSnapshot(
        token_id=yes_tid,
        condition_id=condition_id,
        question=question,
        outcome="Yes",
        complement_token_id=no_tid,
        mid_price=0.45,
        last_price=0.45,
        volume_24h=30000,
        liquidity=3000,
    ))
    state.update_market(no_tid, MarketSnapshot(
        token_id=no_tid,
        condition_id=condition_id,
        question=question,
        outcome="No",
        complement_token_id=yes_tid,
        mid_price=0.55,
        last_price=0.55,
        volume_24h=30000,
        liquidity=3000,
    ))

    return {
        "status": "injected",
        "condition_id": condition_id,
        "question": question,
        "yes_token_id": yes_tid,
        "no_token_id": no_tid,
        "yes_price": 0.45,
        "no_price": 0.55,
        "btc_spot": btc_spot,
        "strike": strike,
        "expiry": expiry.isoformat(),
        "note": "Sniper will detect on next classification refresh (~30s) then evaluate on next scan (~5s)",
    }


# ---- Analytics ----

@api_router.get("/analytics/pnl-history")
async def get_pnl_history():
    """Return cumulative P&L time series from trade history."""
    if not state:
        raise HTTPException(500, "Engine not initialized")

    trades = state.trades[-500:]
    points = []
    cumulative = 0.0
    peak = 0.0
    trough = 0.0

    for t in trades:
        cumulative += t.pnl
        cumulative_r = round(cumulative, 4)
        peak = max(peak, cumulative_r)
        trough = min(trough, cumulative_r)
        points.append({
            "timestamp": t.timestamp,
            "cumulative_pnl": cumulative_r,
            "trade_pnl": round(t.pnl, 4),
            "strategy": t.strategy_id,
        })

    return {
        "points": points,
        "current_pnl": round(cumulative, 4),
        "peak_pnl": round(peak, 4),
        "trough_pnl": round(trough, 4),
        "max_drawdown": round(peak - trough, 4) if peak > trough else 0.0,
        "total_trades": len(trades),
    }


# ---- Test endpoint (paper order through full pipeline) ----

@api_router.post("/test/paper-order")
async def test_paper_order():
    """Submit a test paper order through risk -> execution -> paper adapter."""
    if not engine or not engine.is_running:
        raise HTTPException(400, "Engine must be running")
    if state.trading_mode != TradingMode.PAPER:
        raise HTTPException(400, "Test orders only in paper mode")

    # Check kill switch before proceeding
    if state.risk_config.kill_switch_active:
        raise HTTPException(400, "Kill switch active - orders blocked")

    order = OrderRecord(
        token_id="test-token-001",
        side=OrderSide.BUY,
        price=0.50,
        size=5.0,
        strategy_id="test",
    )

    # Check order through risk engine
    approved, reason = engine.risk_engine.check_order(order)
    if not approved:
        raise HTTPException(400, f"Order rejected by risk engine: {reason}")

    await bus.emit(Event(
        type=EventType.ORDER_REQUEST,
        source="test_api",
        data=order.model_dump(),
    ))

    return {"status": "submitted", "order_id": order.id}


@api_router.post("/test/inject-arb-opportunity")
async def test_inject_arb_opportunity():
    """Inject a synthetic market pair with sub-1.0 pricing to test arb pipeline."""
    if not engine or not engine.is_running:
        raise HTTPException(400, "Engine must be running")

    from models import MarketSnapshot
    import uuid
    uid = uuid.uuid4().hex[:8]
    condition_id = f"test-arb-{uid}"
    yes_tid = f"test-arb-yes-{uid}"
    no_tid = f"test-arb-no-{uid}"

    state.update_market(yes_tid, MarketSnapshot(
        token_id=yes_tid,
        condition_id=condition_id,
        question=f"[TEST] Synthetic arb opportunity {uid}",
        outcome="Yes",
        complement_token_id=no_tid,
        mid_price=0.45,
        last_price=0.45,
        volume_24h=50000,
        liquidity=5000,
    ))
    state.update_market(no_tid, MarketSnapshot(
        token_id=no_tid,
        condition_id=condition_id,
        question=f"[TEST] Synthetic arb opportunity {uid}",
        outcome="No",
        complement_token_id=yes_tid,
        mid_price=0.48,
        last_price=0.48,
        volume_24h=50000,
        liquidity=5000,
    ))

    return {
        "status": "injected",
        "condition_id": condition_id,
        "yes_token_id": yes_tid,
        "no_token_id": no_tid,
        "yes_price": 0.45,
        "no_price": 0.48,
        "gross_edge_bps": 700,
        "note": "Scanner will detect on next scan cycle (~10s)",
    }


# ---- WebSocket ----

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)


# ---- Wire up ----

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
