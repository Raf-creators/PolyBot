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
    global state, bus, engine, ws_broadcast_task

    state = StateManager()
    bus = EventBus()
    engine = TradingEngine(state, bus)

    # Attach Phase 2 components
    engine.market_data = MarketDataFeed()
    engine.price_feeds = PriceFeedManager()
    engine.persistence = PersistenceService(db)

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
