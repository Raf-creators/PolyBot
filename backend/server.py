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
    OrderRecord, OrderSide, utc_now, TradeRecord,
)
from engine.state import StateManager
from engine.events import EventBus
from engine.core import TradingEngine
from engine.market_data import MarketDataFeed
from engine.price_feeds import PriceFeedManager
from engine.strategies.arb_scanner import ArbScanner
from engine.strategies.crypto_sniper import CryptoSniper
from engine.strategies.weather_trader import WeatherTrader
from services.persistence import PersistenceService
from services.telegram_notifier import TelegramNotifier
from services.config_service import ConfigService
from services.live_order_service import LiveOrderService

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

from engine.clob_ws import ClobWebSocketClient
from engine.clob_fill_ws import ClobFillWsClient
from services.forecast_accuracy_service import ForecastAccuracyService
from services.calibration_service import CalibrationService
from services.weather_alert_service import WeatherAlertService
from services.rolling_calibration_service import RollingCalibrationService
from services.liquidity_service import LiquidityService
from services.auto_resolver_service import AutoResolverService

# Engine globals
state: Optional[StateManager] = None
bus: Optional[EventBus] = None
engine: Optional[TradingEngine] = None
arb_scanner_ref: Optional[ArbScanner] = None
crypto_sniper_ref: Optional[CryptoSniper] = None
weather_trader_ref: Optional[WeatherTrader] = None
telegram_notifier: Optional[TelegramNotifier] = None
config_service: Optional[ConfigService] = None
live_order_service: Optional[LiveOrderService] = None
forecast_accuracy_service: Optional[ForecastAccuracyService] = None
calibration_service: Optional[CalibrationService] = None
clob_ws_client: Optional[ClobWebSocketClient] = None
clob_fill_ws_client: Optional[ClobFillWsClient] = None
weather_alert_service: Optional[WeatherAlertService] = None
rolling_calibration_service: Optional[RollingCalibrationService] = None
auto_resolver_service: Optional[AutoResolverService] = None
ws_clients: Set[WebSocket] = set()
ws_broadcast_task: Optional[asyncio.Task] = None


async def _ws_broadcast_loop():
    """Push state snapshots to all connected WebSocket clients every 2 seconds."""
    while True:
        try:
            if ws_clients and state:
                snapshot = state.snapshot()
                # Inject fill WS + execution health (same as /api/status)
                if clob_fill_ws_client:
                    snapshot["stats"]["health"]["fill_ws_connected"] = clob_fill_ws_client._connected
                    snapshot["stats"]["health"]["fill_ws_has_credentials"] = clob_fill_ws_client.has_credentials
                    snapshot["stats"]["health"]["fill_ws_health"] = clob_fill_ws_client.health
                if engine and engine.execution_engine:
                    exec_status = engine.execution_engine.live_adapter_status
                    snapshot["stats"]["health"]["fill_update_method"] = exec_status.get("fill_update_method", "polling")
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
    global state, bus, engine, arb_scanner_ref, crypto_sniper_ref, weather_trader_ref, telegram_notifier, config_service, live_order_service, forecast_accuracy_service, calibration_service, clob_ws_client, clob_fill_ws_client, weather_alert_service, rolling_calibration_service, auto_resolver_service, ws_broadcast_task

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

    # Phase 10: register weather trader strategy (enabled by default)
    weather = WeatherTrader()
    engine.register_strategy(weather)
    state.strategies["weather_trader"].enabled = True
    weather_trader_ref = weather

    # Forecast accuracy tracking
    forecast_accuracy_service = ForecastAccuracyService(db)
    await forecast_accuracy_service.ensure_indexes()
    weather_trader_ref.set_accuracy_service(forecast_accuracy_service)

    # Historical calibration service
    calibration_service = CalibrationService(db)
    await calibration_service.ensure_indexes()
    weather_trader_ref.set_calibration_service(calibration_service)

    # CLOB WebSocket client for real-time market data
    clob_ws_client = ClobWebSocketClient()
    clob_ws_client.set_state(state)
    clob_ws_client.set_bus(bus)
    await clob_ws_client.start()
    weather_trader_ref.set_clob_ws(clob_ws_client)

    # CLOB fill WebSocket (user channel for trade/fill events)
    # Credentials may or may not be present (graceful degradation)
    api_key = os.environ.get("POLY_API_KEY", "")
    api_secret = os.environ.get("POLY_API_SECRET", "")
    passphrase = os.environ.get("POLY_PASSPHRASE", "")
    clob_fill_ws_client = ClobFillWsClient(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
    )
    # Store reference for deferred wiring (adapter created on engine.start())
    await clob_fill_ws_client.start()

    # Phase 6: Telegram notifier (non-blocking, fails gracefully)
    telegram_notifier = TelegramNotifier()
    telegram_notifier.configure(enabled=False, signals_enabled=False)
    await telegram_notifier.start(state, bus)

    # Weather alert service
    weather_alert_service = WeatherAlertService()
    weather_alert_service.set_telegram(telegram_notifier)
    weather_alert_service.set_config(weather_trader_ref.config)
    weather_trader_ref.set_alert_service(weather_alert_service)

    # Rolling calibration service
    rolling_calibration_service = RollingCalibrationService(db)
    await rolling_calibration_service.ensure_indexes()
    rolling_calibration_service.set_config(weather_trader_ref.config)
    weather_trader_ref.set_rolling_calibration_service(rolling_calibration_service)

    # Auto-resolver service — resolves pending forecast_accuracy records
    auto_resolver_service = AutoResolverService(
        db=db,
        forecast_accuracy_service=forecast_accuracy_service,
        rolling_calibration_service=rolling_calibration_service,
        interval_hours=float(os.environ.get("AUTO_RESOLVER_INTERVAL_HOURS", "6")),
    )
    await auto_resolver_service.start()

    # Phase 7: Config persistence — load from MongoDB and apply
    config_service = ConfigService(db)
    persisted = await config_service.load()
    if persisted:
        config_service.apply_to_engine(persisted, state, telegram_notifier, arb_scanner_ref, crypto_sniper_ref, weather_trader_ref)
        # Re-sync alert service with loaded config
        if weather_alert_service and weather_trader_ref:
            weather_alert_service.set_config(weather_trader_ref.config)
        # Re-sync rolling calibration service with loaded config
        if rolling_calibration_service and weather_trader_ref:
            rolling_calibration_service.set_config(weather_trader_ref.config)
        logger.info("Persisted configuration applied")
    else:
        # Save defaults on first boot
        snapshot = config_service.build_snapshot(state, telegram_notifier, arb_scanner_ref, crypto_sniper_ref, weather_trader_ref)
        await config_service.save(snapshot)
        logger.info("Default configuration persisted")

    # Trading mode from env (override persisted if env is explicitly set)
    mode_str = os.environ.get("TRADING_MODE", "paper")
    valid_modes = [m.value for m in TradingMode]
    if not persisted or not persisted.get("trading_mode"):
        state.trading_mode = TradingMode(mode_str) if mode_str in valid_modes else TradingMode.PAPER

    # Force paper if no credentials
    if not os.environ.get("POLYMARKET_PRIVATE_KEY"):
        state.trading_mode = TradingMode.PAPER
        logger.info("No Polymarket credentials. Paper mode enforced.")

    # Start WebSocket broadcast
    ws_broadcast_task = asyncio.create_task(_ws_broadcast_loop())

    # Phase 8A: Live order persistence & polling
    live_order_service = LiveOrderService(db)
    await live_order_service.load_active()
    engine.execution_engine.set_live_order_service(live_order_service)
    if engine.execution_engine._live_adapter and engine.execution_engine._live_adapter._authenticated:
        await engine.execution_engine.start_live_polling()

    logger.info(f"Polymarket Edge OS initialized [{state.trading_mode.value}]")

    yield

    # Shutdown — persist config before stopping
    if config_service and state:
        try:
            snapshot = config_service.build_snapshot(state, telegram_notifier, arb_scanner_ref, crypto_sniper_ref, weather_trader_ref)
            await config_service.save(snapshot)
        except Exception as e:
            logger.error(f"Config persist on shutdown error: {e}")
    if telegram_notifier:
        await telegram_notifier.stop()
    if ws_broadcast_task:
        ws_broadcast_task.cancel()
        try:
            await ws_broadcast_task
        except asyncio.CancelledError:
            pass
    if engine and engine.is_running:
        await engine.stop()
    if clob_ws_client:
        await clob_ws_client.stop()
    if clob_fill_ws_client:
        await clob_fill_ws_client.stop()
    if auto_resolver_service:
        await auto_resolver_service.stop()
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
    snap = state.snapshot()
    # Inject fill WS health into stats.health
    if clob_fill_ws_client:
        snap["stats"]["health"]["fill_ws_connected"] = clob_fill_ws_client._connected
        snap["stats"]["health"]["fill_ws_has_credentials"] = clob_fill_ws_client.has_credentials
        snap["stats"]["health"]["fill_ws_health"] = clob_fill_ws_client.health
    # Inject execution fill_update_method
    if engine and engine.execution_engine:
        exec_status = engine.execution_engine.live_adapter_status
        snap["stats"]["health"]["fill_update_method"] = exec_status.get("fill_update_method", "polling")
    return snap


# ---- Engine Control ----

@api_router.post("/engine/start")
async def start_engine():
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    if engine.is_running:
        raise HTTPException(400, "Engine already running")
    await engine.start()
    # Wire fill WS to live adapter (now available after engine.start())
    if clob_fill_ws_client and engine.execution_engine._live_adapter:
        adapter = engine.execution_engine._live_adapter
        adapter.set_fill_ws(clob_fill_ws_client)
        clob_fill_ws_client._fill_callback = adapter.on_ws_fill
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
        "strategy_configs": {
            "arb_scanner": arb_scanner_ref.config.model_dump() if arb_scanner_ref else {},
            "crypto_sniper": crypto_sniper_ref.config.model_dump() if crypto_sniper_ref else {},
            "weather_trader": weather_trader_ref.config.model_dump() if weather_trader_ref else {},
        },
        "credentials_present": {
            "polymarket": bool(os.environ.get("POLYMARKET_PRIVATE_KEY")),
            "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        },
        "telegram": telegram_notifier.stats if telegram_notifier else {},
        "persisted": bool(config_service and config_service.cached),
        "last_saved": config_service.cached.get("updated_at") if config_service else None,
    }


@api_router.get("/config/strategies")
async def get_strategy_configs():
    """Get detailed strategy configuration parameters."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    result = {}
    if arb_scanner_ref:
        result["arb_scanner"] = {
            "enabled": state.strategies.get("arb_scanner") and state.strategies["arb_scanner"].enabled,
            **arb_scanner_ref.config.model_dump(),
        }
    if crypto_sniper_ref:
        result["crypto_sniper"] = {
            "enabled": state.strategies.get("crypto_sniper") and state.strategies["crypto_sniper"].enabled,
            **crypto_sniper_ref.config.model_dump(),
        }
    if weather_trader_ref:
        result["weather_trader"] = {
            "enabled": state.strategies.get("weather_trader") and state.strategies["weather_trader"].enabled,
            **weather_trader_ref.config.model_dump(),
        }
    return result


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
    if telegram_notifier and (body.telegram_enabled is not None or body.telegram_signals_enabled is not None):
        new_enabled = body.telegram_enabled if body.telegram_enabled is not None else telegram_notifier._enabled
        new_signals = body.telegram_signals_enabled if body.telegram_signals_enabled is not None else telegram_notifier._signals_enabled
        telegram_notifier.configure(enabled=new_enabled, signals_enabled=new_signals)

    # Persist to MongoDB
    if config_service:
        snapshot = config_service.build_snapshot(state, telegram_notifier, arb_scanner_ref, crypto_sniper_ref, weather_trader_ref)
        await config_service.save(snapshot)

    return {"status": "updated", "persisted": True}


@api_router.post("/config/update")
async def update_config_granular(body: dict):
    """Granular config update — accepts partial strategy/risk/telegram changes."""
    if not state:
        raise HTTPException(500, "Engine not initialized")

    changes = {}

    # Risk config
    if "risk" in body and isinstance(body["risk"], dict):
        try:
            from models import RiskConfig
            merged = {**state.risk_config.model_dump(), **body["risk"]}
            state.risk_config = RiskConfig(**merged)
            changes["risk"] = "updated"
        except Exception as e:
            raise HTTPException(400, f"Invalid risk config: {e}")

    # Telegram toggles
    if "telegram_enabled" in body and telegram_notifier:
        telegram_notifier.configure(
            enabled=bool(body["telegram_enabled"]),
            signals_enabled=telegram_notifier._signals_enabled,
        )
        changes["telegram_enabled"] = body["telegram_enabled"]
    if "telegram_signals_enabled" in body and telegram_notifier:
        telegram_notifier.configure(
            enabled=telegram_notifier._enabled,
            signals_enabled=bool(body["telegram_signals_enabled"]),
        )
        changes["telegram_signals_enabled"] = body["telegram_signals_enabled"]

    # Strategy configs
    if "strategies" in body and isinstance(body["strategies"], dict):
        for strat_id, params in body["strategies"].items():
            if not isinstance(params, dict):
                continue

            if strat_id == "arb_scanner" and arb_scanner_ref:
                enabled = params.pop("enabled", None)
                if enabled is not None and "arb_scanner" in state.strategies:
                    state.strategies["arb_scanner"].enabled = bool(enabled)
                if params:
                    try:
                        from engine.strategies.arb_models import ArbConfig
                        known = set(ArbConfig.model_fields.keys())
                        filtered = {k: v for k, v in params.items() if k in known}
                        merged = {**arb_scanner_ref.config.model_dump(), **filtered}
                        arb_scanner_ref.config = ArbConfig(**merged)
                    except Exception as e:
                        raise HTTPException(400, f"Invalid arb config: {e}")
                changes["arb_scanner"] = "updated"

            elif strat_id == "crypto_sniper" and crypto_sniper_ref:
                enabled = params.pop("enabled", None)
                if enabled is not None and "crypto_sniper" in state.strategies:
                    state.strategies["crypto_sniper"].enabled = bool(enabled)
                if params:
                    try:
                        from engine.strategies.sniper_models import SniperConfig
                        known = set(SniperConfig.model_fields.keys())
                        filtered = {k: v for k, v in params.items() if k in known}
                        merged = {**crypto_sniper_ref.config.model_dump(), **filtered}
                        crypto_sniper_ref.config = SniperConfig(**merged)
                    except Exception as e:
                        raise HTTPException(400, f"Invalid sniper config: {e}")
                changes["crypto_sniper"] = "updated"

            elif strat_id == "weather_trader" and weather_trader_ref:
                enabled = params.pop("enabled", None)
                if enabled is not None and "weather_trader" in state.strategies:
                    state.strategies["weather_trader"].enabled = bool(enabled)
                if params:
                    try:
                        from engine.strategies.weather_models import WeatherConfig
                        known = set(WeatherConfig.model_fields.keys())
                        filtered = {k: v for k, v in params.items() if k in known}
                        merged = {**weather_trader_ref.config.model_dump(), **filtered}
                        weather_trader_ref.config = WeatherConfig(**merged)
                        # Sync alert service config
                        if weather_alert_service:
                            weather_alert_service.set_config(weather_trader_ref.config)
                        # Sync rolling calibration config
                        if rolling_calibration_service:
                            rolling_calibration_service.set_config(weather_trader_ref.config)
                    except Exception as e:
                        raise HTTPException(400, f"Invalid weather config: {e}")
                changes["weather_trader"] = "updated"

    # Persist
    if config_service:
        snapshot = config_service.build_snapshot(state, telegram_notifier, arb_scanner_ref, crypto_sniper_ref, weather_trader_ref)
        await config_service.save(snapshot)

    return {"status": "updated", "changes": changes, "persisted": True}


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


# ---- Execution Mode ----

@api_router.get("/execution/mode")
async def get_execution_mode():
    """Get current execution mode and adapter status."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    from engine.live_adapter import LiveAdapter
    creds = LiveAdapter.credentials_present()
    live_status = engine.execution_engine.live_adapter_status if engine else {}
    return {
        "mode": state.trading_mode.value,
        "live_adapter_authenticated": live_status.get("authenticated", False),
        "credentials": creds,
        "live_enabled": state.trading_mode.value == "live",
        "safe_to_switch_live": creds["ready"] and not state.risk_config.kill_switch_active,
    }


@api_router.post("/execution/mode")
async def set_execution_mode(body: dict):
    """Switch execution mode with safety checks."""
    if not state:
        raise HTTPException(500, "Engine not initialized")

    new_mode = body.get("mode", "").lower()
    if new_mode not in ("paper", "live", "shadow"):
        raise HTTPException(400, f"Invalid mode: {new_mode}. Must be paper/live/shadow")

    if new_mode == "live":
        from engine.live_adapter import LiveAdapter
        creds = LiveAdapter.credentials_present()
        if not creds["ready"]:
            raise HTTPException(400, "Cannot switch to live: POLYMARKET_PRIVATE_KEY not set")
        if state.risk_config.kill_switch_active:
            raise HTTPException(400, "Cannot switch to live: kill switch is active")

        # Apply conservative live defaults
        from engine.live_adapter import LIVE_DEFAULTS
        state.risk_config.max_order_size = min(state.risk_config.max_order_size, LIVE_DEFAULTS["max_order_size"])
        state.risk_config.max_position_size = min(state.risk_config.max_position_size, LIVE_DEFAULTS["max_position_size"])
        state.risk_config.max_market_exposure = min(state.risk_config.max_market_exposure, LIVE_DEFAULTS["max_market_exposure"])
        state.risk_config.max_concurrent_positions = min(state.risk_config.max_concurrent_positions, LIVE_DEFAULTS["max_concurrent_positions"])
        state.risk_config.max_daily_loss = min(state.risk_config.max_daily_loss, LIVE_DEFAULTS["max_daily_loss"])

        # Ensure live adapter is initialized
        live = engine.execution_engine._live_adapter
        if live and not live._authenticated:
            await live.initialize()

    state.trading_mode = TradingMode(new_mode)

    # Persist
    if config_service:
        snapshot = config_service.build_snapshot(state, telegram_notifier, arb_scanner_ref, crypto_sniper_ref, weather_trader_ref)
        await config_service.save(snapshot)

    return {
        "status": "mode_changed",
        "mode": new_mode,
        "risk_limits": state.risk_config.model_dump(),
        "persisted": True,
    }


@api_router.get("/execution/status")
async def get_execution_status():
    """Get detailed execution adapter status including slippage config."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    live_status = engine.execution_engine.live_adapter_status if engine else {}
    return {
        "mode": state.trading_mode.value,
        "paper_adapter": "always_available",
        "live_adapter": live_status,
        "risk_config": state.risk_config.model_dump(),
        "slippage_protection": {
            "max_live_slippage_bps": state.risk_config.max_live_slippage_bps,
            "allow_aggressive_live": state.risk_config.allow_aggressive_live,
        },
        "engine_running": engine.is_running if engine else False,
    }


@api_router.get("/execution/wallet")
async def get_wallet_status():
    """Get live wallet balance and readiness."""
    if not state:
        raise HTTPException(500, "Engine not initialized")

    live_adapter = engine.execution_engine._live_adapter if engine else None
    authenticated = live_adapter._authenticated if live_adapter else False
    balance = None

    if authenticated:
        balance = await live_adapter.get_balance()

    return {
        "mode": state.trading_mode.value,
        "authenticated": authenticated,
        "balance_usdc": balance,
        "live_ready": authenticated and balance is not None and balance > 0,
        "warnings": _wallet_warnings(authenticated, balance, state),
    }


def _wallet_warnings(authenticated, balance, state) -> list:
    warnings = []
    if state.trading_mode.value == "live" and not authenticated:
        warnings.append("LIVE mode enabled but adapter not authenticated")
    if state.trading_mode.value == "live" and authenticated and (balance is None or balance <= 0):
        warnings.append("LIVE mode enabled but wallet has no balance")
    if state.risk_config.kill_switch_active:
        warnings.append("Kill switch is active — no orders will be sent")
    return warnings


@api_router.get("/execution/orders")
async def get_live_orders(limit: int = 50):
    """Get recent live order records with fill tracking."""
    if not live_order_service:
        return []
    return await live_order_service.get_recent(limit=limit)


@api_router.post("/execution/orders/{order_id}/cancel")
async def cancel_live_order(order_id: str):
    """Cancel an open/partial live order."""
    # Try via live adapter if available
    if engine and engine.execution_engine._live_adapter:
        result = await engine.execution_engine._live_adapter.cancel_order(order_id)
    elif live_order_service:
        # Fallback: cancel directly in DB if engine not running
        rec = live_order_service.active_orders.get(order_id)
        if not rec:
            doc = await live_order_service.get_by_id(order_id)
            if doc and doc.get("status") in ("filled", "cancelled", "rejected", "expired"):
                raise HTTPException(400, f"order already in terminal state: {doc['status']}")
            raise HTTPException(404, "order not found")
        await live_order_service.update_status(
            order_id, status="cancelled", cancelled_at=utc_now(), cancel_reason="manual_cancel_engine_stopped",
        )
        result = {"success": True, "method": "local_db", "filled_size": rec.filled_size, "remaining_size": rec.remaining_size}
    else:
        raise HTTPException(500, "No order service available")

    if result.get("success"):
        return {
            "status": "cancelled",
            "order_id": order_id,
            "method": result.get("method"),
            "filled_size": result.get("filled_size", 0),
            "remaining_size": result.get("remaining_size", 0),
        }
    else:
        reason = result.get("reason", "cancel failed")
        # Return 404 for not found, 400 for other errors
        if "not found" in reason.lower():
            raise HTTPException(404, reason)
        raise HTTPException(400, reason)


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


@api_router.get("/markets/liquidity-heatmap")
async def get_liquidity_heatmap():
    """Return liquidity heatmap tiles for weather markets with per-bucket scores."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    svc = LiquidityService(state)
    classifications = weather_trader_ref._classified if weather_trader_ref else {}
    return svc.get_heatmap(weather_classifications=classifications)


@api_router.get("/markets/liquidity-scores")
async def get_liquidity_scores():
    """Return per-token liquidity scores for all markets."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    svc = LiquidityService(state)
    return svc.get_token_scores()


# ---- Health metrics ----

@api_router.get("/health/feeds")
async def get_feed_health():
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return state.health


@api_router.get("/health/clob-ws")
async def get_clob_ws_health():
    if not clob_ws_client:
        return {"connected": False, "note": "not_configured"}
    return clob_ws_client.health


@api_router.get("/health/fill-ws")
async def get_fill_ws_health():
    if not clob_fill_ws_client:
        return {"connected": False, "has_credentials": False, "note": "not_configured"}
    return clob_fill_ws_client.health


@api_router.get("/health/auto-resolver")
async def get_auto_resolver_health():
    """Health and status of the automated forecast resolution service."""
    if not auto_resolver_service:
        return {"running": False, "note": "not_configured"}
    return auto_resolver_service.health


@api_router.post("/auto-resolver/run")
async def trigger_auto_resolver():
    """Manually trigger a resolution pass."""
    if not auto_resolver_service:
        raise HTTPException(500, "Auto-resolver not initialized")
    result = await auto_resolver_service.run_once()
    return result



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


# ---- Phase 10: Weather Strategy Endpoints ----

@api_router.get("/strategies/weather/signals")
async def get_weather_signals(limit: int = 50):
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")
    sigs = weather_trader_ref.get_signals(limit=limit)
    tradable = [s for s in sigs if s.get("is_tradable")]
    rejected = [s for s in sigs if not s.get("is_tradable")]
    return {
        "tradable": tradable,
        "rejected": rejected[:limit],
        "total_tradable": len(tradable),
        "total_rejected": len(rejected),
    }


@api_router.get("/strategies/weather/executions")
async def get_weather_executions():
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")
    return {
        "active": weather_trader_ref.get_active_executions(),
        "completed": weather_trader_ref.get_completed_executions(limit=50),
    }


@api_router.get("/strategies/weather/health")
async def get_weather_health():
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")
    health = weather_trader_ref.get_health()
    # Inject auto-resolver status
    if auto_resolver_service:
        health["auto_resolver"] = auto_resolver_service.health
    return health


@api_router.get("/strategies/weather/config")
async def get_weather_config():
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")
    return {
        "enabled": state.strategies.get("weather_trader") and state.strategies["weather_trader"].enabled,
        **weather_trader_ref.config.model_dump(),
    }


@api_router.get("/strategies/weather/forecasts")
async def get_weather_forecasts():
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")
    return weather_trader_ref.get_forecasts()


@api_router.get("/strategies/weather/stations")
async def get_weather_stations():
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")
    return weather_trader_ref.get_stations()


# ---- Forecast Accuracy & Calibration Endpoints ----


@api_router.get("/strategies/weather/alerts")
async def get_weather_alerts(limit: int = 50):
    if not weather_alert_service:
        return {"alerts": [], "stats": {"enabled": False}}
    return {
        "alerts": weather_alert_service.get_alerts(limit=limit),
        "stats": weather_alert_service.get_stats(),
    }


# ---- Forecast Accuracy & Calibration Endpoints (existing) ----

@api_router.get("/strategies/weather/accuracy/history")
async def get_forecast_accuracy_history(limit: int = 100, station_id: str = None):
    """Resolved forecast accuracy log."""
    if not forecast_accuracy_service:
        raise HTTPException(500, "Accuracy service not initialized")
    return await forecast_accuracy_service.get_history(limit=limit, station_id=station_id)


@api_router.get("/strategies/weather/accuracy/stations")
async def get_forecast_accuracy_stations():
    """Per-station forecast error summary."""
    if not forecast_accuracy_service:
        raise HTTPException(500, "Accuracy service not initialized")
    return await forecast_accuracy_service.get_station_summary()


@api_router.get("/strategies/weather/accuracy/calibration")
async def get_calibration_health():
    """Overall calibration health and readiness status."""
    if not forecast_accuracy_service:
        raise HTTPException(500, "Accuracy service not initialized")
    return await forecast_accuracy_service.get_calibration_health()


@api_router.get("/strategies/weather/accuracy/unresolved")
async def get_unresolved_forecasts(limit: int = 50):
    """Forecasts pending resolution (awaiting observed temperature)."""
    if not forecast_accuracy_service:
        raise HTTPException(500, "Accuracy service not initialized")
    return await forecast_accuracy_service.get_unresolved(limit=limit)


@api_router.post("/strategies/weather/accuracy/resolve")
async def resolve_forecast(body: dict):
    """Manually resolve a forecast with observed temperature.

    Body: { "station_id": "KLGA", "target_date": "2026-03-13", "observed_high_f": 42.0, "winning_bucket": "40-41F" }
    """
    if not forecast_accuracy_service:
        raise HTTPException(500, "Accuracy service not initialized")
    station_id = body.get("station_id")
    target_date = body.get("target_date")
    observed_high = body.get("observed_high_f")
    winning_bucket = body.get("winning_bucket")
    if not station_id or not target_date or observed_high is None:
        raise HTTPException(400, "station_id, target_date, and observed_high_f required")
    await forecast_accuracy_service.resolve_forecast(
        station_id=station_id, target_date=target_date,
        observed_high_f=float(observed_high), winning_bucket=winning_bucket,
    )
    return {"status": "resolved", "station_id": station_id, "target_date": target_date, "observed_high_f": observed_high}


@api_router.get("/strategies/weather/shadow-summary")
async def get_weather_shadow_summary():
    """Shadow-mode operational summary for WeatherTrader."""
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")

    health = weather_trader_ref.get_health()
    exec_mode = health.get("execution_mode", "paper")
    is_shadow = exec_mode == "shadow"

    # Gather calibration info
    cal_health = {}
    if forecast_accuracy_service:
        cal_health = await forecast_accuracy_service.get_calibration_health()

    return {
        "execution_mode": exec_mode,
        "is_shadow": is_shadow,
        "shadow_overrides_applied": health.get("shadow_overrides_applied", False),
        "config_snapshot": {
            "min_edge_bps": weather_trader_ref.config.min_edge_bps,
            "kelly_scale": weather_trader_ref.config.kelly_scale,
            "max_signal_size": weather_trader_ref.config.max_signal_size,
            "max_concurrent_signals": weather_trader_ref.config.max_concurrent_signals,
            "max_stale_market_seconds": weather_trader_ref.config.max_stale_market_seconds,
            "cooldown_seconds": weather_trader_ref.config.cooldown_seconds,
            "default_size": weather_trader_ref.config.default_size,
        },
        "operational_stats": {
            "total_scans": health.get("total_scans", 0),
            "markets_classified": health.get("classified_markets", 0),
            "forecasts_fetched": health.get("forecasts_fetched", 0),
            "forecasts_missing": health.get("forecasts_missing", 0),
            "signals_generated": health.get("signals_generated", 0),
            "signals_executed": health.get("signals_executed", 0),
            "signals_filled": health.get("signals_filled", 0),
            "rejection_reasons": health.get("rejection_reasons", {}),
        },
        "calibration": cal_health,
        "running": health.get("running", False),
    }


@api_router.post("/strategies/weather/shadow/enable")
async def enable_weather_shadow():
    """Apply shadow-mode config overrides to WeatherTrader."""
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")
    weather_trader_ref.apply_shadow_overrides()
    return {
        "status": "shadow_overrides_applied",
        "config": weather_trader_ref.config.model_dump(),
    }


@api_router.post("/strategies/weather/shadow/reset")
async def reset_weather_config():
    """Reset WeatherTrader to default (paper-mode) config."""
    if not weather_trader_ref:
        raise HTTPException(500, "Weather trader not initialized")
    from engine.strategies.weather_models import WeatherConfig
    weather_trader_ref.config = WeatherConfig()
    return {
        "status": "config_reset_to_defaults",
        "config": weather_trader_ref.config.model_dump(),
    }


# ---- Calibration Endpoints ----

@api_router.post("/strategies/weather/calibration/run")
async def run_calibration(body: dict = None):
    """Run historical calibration for all or specified stations.

    Body (optional): { "station_ids": ["KLGA", "KORD"], "lookback_days": 90 }
    """
    if not calibration_service:
        raise HTTPException(500, "Calibration service not initialized")

    station_ids = None
    lookback_days = 90
    if body:
        station_ids = body.get("station_ids")
        lookback_days = body.get("lookback_days", 90)

    result = await calibration_service.run_calibration(
        station_ids=station_ids, lookback_days=lookback_days,
    )
    return result


@api_router.get("/strategies/weather/calibration/status")
async def get_calibration_status():
    """Get calibration status including per-station details."""
    if not calibration_service:
        raise HTTPException(500, "Calibration service not initialized")
    return await calibration_service.get_status()


@api_router.get("/strategies/weather/calibration/{station_id}")
async def get_station_calibration(station_id: str):
    """Get calibration data for a specific station."""
    if not calibration_service:
        raise HTTPException(500, "Calibration service not initialized")
    cal = await calibration_service.get_calibration(station_id)
    if not cal:
        raise HTTPException(404, f"No calibration for {station_id}")
    return cal.model_dump()


@api_router.post("/strategies/weather/calibration/reload")
async def reload_calibrations():
    """Reload calibrations from MongoDB into the running WeatherTrader."""
    if not calibration_service or not weather_trader_ref:
        raise HTTPException(500, "Services not initialized")
    calibrations = await calibration_service.get_all_calibrations()
    weather_trader_ref._calibrations = calibrations
    # Also reload rolling calibrations
    rolling_result = {}
    if rolling_calibration_service:
        await rolling_calibration_service.load_cached()
        rolling_result = await weather_trader_ref.reload_rolling_calibrations()
    return {
        "status": "reloaded",
        "calibrations_loaded": len(calibrations),
        "stations": list(calibrations.keys()),
        "rolling": rolling_result,
    }


# ---- Rolling Calibration Endpoints ----

@api_router.get("/strategies/weather/calibration/rolling/status")
async def get_rolling_calibration_status():
    """Get rolling calibration status and per-station details."""
    if not rolling_calibration_service:
        return {"enabled": False, "status": "service_not_initialized"}
    return await rolling_calibration_service.get_status()


@api_router.post("/strategies/weather/calibration/rolling/run")
async def run_rolling_calibration(body: dict = None):
    """Run rolling calibration from live forecast_accuracy data.

    Body (optional): { "station_ids": ["KLGA", "KORD"] }
    """
    if not rolling_calibration_service:
        raise HTTPException(500, "Rolling calibration service not initialized")
    station_ids = body.get("station_ids") if body else None
    result = await rolling_calibration_service.run_rolling_calibration(station_ids=station_ids)
    # Hot-reload into WeatherTrader
    if weather_trader_ref:
        await weather_trader_ref.reload_rolling_calibrations()
    return result


@api_router.post("/strategies/weather/calibration/rolling/reload")
async def reload_rolling_calibrations():
    """Reload rolling calibrations from MongoDB into the running WeatherTrader."""
    if not rolling_calibration_service or not weather_trader_ref:
        raise HTTPException(500, "Services not initialized")
    await rolling_calibration_service.load_cached()
    result = await weather_trader_ref.reload_rolling_calibrations()
    return result



@api_router.post("/test/inject-weather-market")
async def test_inject_weather_market():
    """Inject a synthetic NYC weather market for testing the weather pipeline."""
    if not engine or not engine.is_running:
        raise HTTPException(400, "Engine must be running")

    from models import MarketSnapshot
    from datetime import datetime, timezone, timedelta
    import uuid

    uid = uuid.uuid4().hex[:8]
    condition_id = f"test-weather-{uid}"

    # Build a 5-bucket NYC market for tomorrow
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%B %d, %Y")
    question = f"Highest temperature in NYC on {tomorrow}?"

    bucket_defs = [
        ("40F or below", 0.05),
        ("41-42F", 0.12),
        ("43-44F", 0.30),
        ("45-46F", 0.33),
        ("47F or higher", 0.20),
    ]

    token_ids = []
    for i, (label, price) in enumerate(bucket_defs):
        tid = f"test-weather-{uid}-{i}"
        token_ids.append(tid)
        state.update_market(tid, MarketSnapshot(
            token_id=tid,
            condition_id=condition_id,
            question=question,
            outcome=label,
            mid_price=price,
            last_price=price,
            volume_24h=5000,
            liquidity=500,
        ))

    return {
        "status": "injected",
        "condition_id": condition_id,
        "question": question,
        "buckets": [{"token_id": tid, "label": bd[0], "price": bd[1]}
                    for tid, bd in zip(token_ids, bucket_defs)],
        "note": "Weather trader will detect on next classification refresh (~5min) then evaluate. Use GET /api/strategies/weather/health to monitor.",
    }


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


# ---- Alerts ----

@api_router.get("/alerts/test")
async def test_telegram_alert():
    """Send a test Telegram message to verify alert configuration."""
    if not telegram_notifier:
        raise HTTPException(500, "Telegram notifier not initialized")
    if not telegram_notifier.configured:
        return {
            "status": "skipped",
            "reason": "Telegram credentials not configured (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)",
        }

    ok = await telegram_notifier.send_message(
        "<b>[TEST]</b>\nPolymarket Edge OS alert system operational."
    )
    return {
        "status": "sent" if ok else "failed",
        "configured": telegram_notifier.configured,
        "stats": telegram_notifier.stats,
    }


@api_router.get("/alerts/status")
async def get_alerts_status():
    """Get current Telegram alert configuration and stats."""
    if not telegram_notifier:
        raise HTTPException(500, "Telegram notifier not initialized")
    return telegram_notifier.stats


# ---- Ticker Feed ----

def _extract_asset_tag(question: str) -> str:
    q = question.upper()
    if "BTC" in q or "BITCOIN" in q:
        return "BTC"
    if "ETH" in q or "ETHEREUM" in q:
        return "ETH"
    return "MKT"


@api_router.get("/ticker/feed")
async def get_ticker_feed(limit: int = 50):
    """Unified execution feed for the trade ticker strip."""
    if not state:
        raise HTTPException(500, "Engine not initialized")

    items = []

    if arb_scanner_ref:
        for e in arb_scanner_ref.get_active_executions() + arb_scanner_ref.get_completed_executions(limit=25):
            items.append({
                "id": e["id"],
                "strategy": "ARB",
                "asset": _extract_asset_tag(e.get("question", "")),
                "side": "BUY",
                "size": e["size"],
                "price": e.get("yes_fill_price") or 0,
                "edge_bps": e.get("realized_edge_bps") or e.get("target_edge_bps", 0),
                "timestamp": e.get("completed_at") or e["submitted_at"],
            })

    if crypto_sniper_ref:
        for e in crypto_sniper_ref.get_active_executions() + crypto_sniper_ref.get_completed_executions(limit=25):
            items.append({
                "id": e["id"],
                "strategy": "SNIPER",
                "asset": e.get("asset", "BTC"),
                "side": "BUY" if "buy" in e.get("side", "") else "SELL",
                "size": e["size"],
                "price": e.get("entry_price") or 0,
                "edge_bps": e.get("target_edge_bps", 0),
                "timestamp": e.get("filled_at") or e["submitted_at"],
            })

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]


# ---- Analytics ----

from services.analytics_service import (
    compute_portfolio_summary, compute_strategy_metrics,
    compute_execution_quality, compute_timeseries,
)


@api_router.get("/analytics/global")
async def get_global_analytics():
    """Global analytics — shadow-mode strategy quality dashboard."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    from services.global_analytics_service import GlobalAnalyticsService
    svc = GlobalAnalyticsService(
        state=state,
        weather_trader=weather_trader_ref,
        arb_scanner=arb_scanner_ref,
        crypto_sniper=crypto_sniper_ref,
        forecast_accuracy_service=forecast_accuracy_service,
    )
    report = await svc.get_full_report()
    # Inject auto-resolver health
    if auto_resolver_service:
        report["auto_resolver"] = auto_resolver_service.health
    return report


@api_router.get("/analytics/summary")
async def get_analytics_summary():
    """Portfolio-level analytics: PnL, drawdown, win rate, Sharpe, etc."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return compute_portfolio_summary(state.trades, state.positions)


@api_router.get("/analytics/strategies")
async def get_analytics_strategies():
    """Per-strategy performance breakdown."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return compute_strategy_metrics(state.trades, state.positions)


@api_router.get("/analytics/execution-quality")
async def get_analytics_execution_quality():
    """Execution quality: fill ratio, slippage, rejections."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    live_ords = await live_order_service.get_recent(limit=200) if live_order_service else []
    return compute_execution_quality(state.orders, live_ords)


@api_router.get("/analytics/timeseries")
async def get_analytics_timeseries():
    """Time-based metrics: daily PnL, equity curve, drawdown, trade frequency."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    return compute_timeseries(state.trades)


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


# ---- Test endpoints (synthetic trade injection for analytics testing) ----

@api_router.post("/test/inject-trades")
async def inject_test_trades():
    """Inject synthetic trades for analytics testing. Paper-mode only."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    import random
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    strategies = ["arb_scanner", "crypto_sniper"]
    count = 0
    for day_offset in range(10):
        dt = now - timedelta(days=9 - day_offset)
        for _ in range(random.randint(3, 8)):
            strat = random.choice(strategies)
            side = random.choice(["buy", "sell"])
            price = round(random.uniform(0.3, 0.8), 4)
            size = round(random.uniform(1, 10), 2)
            pnl = round(random.uniform(-2, 3), 4)
            fees = round(price * size * 0.002, 4)
            trade = TradeRecord(
                order_id=f"test_{count}",
                token_id=f"token_{random.randint(1,5)}",
                market_question=f"Test Market {random.randint(1,5)}?",
                outcome="Yes" if random.random() > 0.5 else "No",
                side=OrderSide(side),
                price=price,
                size=size,
                fees=fees,
                pnl=pnl,
                strategy_id=strat,
                signal_reason="test_signal",
                timestamp=dt.isoformat(),
            )
            state.trades.append(trade)
            count += 1
    # Also inject some orders for execution quality testing
    from models import OrderStatus
    for i in range(count):
        status = random.choice([OrderStatus.FILLED, OrderStatus.FILLED, OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED])
        order = OrderRecord(
            id=f"test_order_{i}",
            token_id=f"token_{random.randint(1,5)}",
            side=OrderSide(random.choice(["buy", "sell"])),
            price=round(random.uniform(0.3, 0.8), 4),
            size=round(random.uniform(1, 10), 2),
            status=status,
            strategy_id=random.choice(strategies),
            latency_ms=round(random.uniform(5, 100), 2) if status == OrderStatus.FILLED else None,
        )
        state.orders[order.id] = order
    return {"status": "ok", "count": count}


@api_router.post("/test/clear-trades")
async def clear_test_trades():
    """Clear injected test trades."""
    if not state:
        raise HTTPException(500, "Engine not initialized")
    state.trades = [t for t in state.trades if not t.order_id.startswith("test_")]
    state.orders = {k: v for k, v in state.orders.items() if not k.startswith("test_order_")}
    return {"status": "cleared"}



# ---- Demo Mode ----

from services.demo_data_service import DemoDataService

_demo_service = DemoDataService()
_demo_enabled = False


@api_router.get("/demo/status")
async def get_demo_status():
    return {"enabled": _demo_enabled, "seed": _demo_service._seed, "generated_at": _demo_service.get("generated_at")}


@api_router.post("/demo/enable")
async def enable_demo():
    global _demo_enabled
    _demo_enabled = True
    return {"enabled": True, "seed": _demo_service._seed}


@api_router.post("/demo/disable")
async def disable_demo():
    global _demo_enabled
    _demo_enabled = False
    return {"enabled": False}


@api_router.post("/demo/regenerate")
async def regenerate_demo():
    _demo_service.generate()
    return {"status": "regenerated", "seed": _demo_service._seed, "generated_at": _demo_service.get("generated_at")}


# Demo data endpoints — mirror real endpoints but return generated data
@api_router.get("/demo/positions")
async def demo_positions():
    return _demo_service.get("positions", [])


@api_router.get("/demo/trades")
async def demo_trades():
    return _demo_service.get("trades", [])


@api_router.get("/demo/orders")
async def demo_orders():
    return _demo_service.get("orders", [])


@api_router.get("/demo/markets")
async def demo_markets():
    return _demo_service.get("markets", [])


@api_router.get("/demo/ticker/feed")
async def demo_ticker():
    return _demo_service.get("ticker", [])


@api_router.get("/demo/analytics/summary")
async def demo_analytics_summary():
    return _demo_service.get("analytics_summary", {})


@api_router.get("/demo/analytics/strategies")
async def demo_analytics_strategies():
    return _demo_service.get("analytics_strategies", {})


@api_router.get("/demo/analytics/execution-quality")
async def demo_analytics_execution():
    return _demo_service.get("analytics_execution", {})


@api_router.get("/demo/analytics/timeseries")
async def demo_analytics_timeseries():
    return _demo_service.get("analytics_timeseries", {})


@api_router.get("/demo/analytics/pnl-history")
async def demo_pnl_history():
    return _demo_service.get("pnl_history", {})


@api_router.get("/demo/strategies/arb/opportunities")
async def demo_arb_opportunities():
    return _demo_service.get("arb", {}).get("opportunities", {})


@api_router.get("/demo/strategies/arb/executions")
async def demo_arb_executions():
    return _demo_service.get("arb", {}).get("executions", {})


@api_router.get("/demo/strategies/arb/health")
async def demo_arb_health():
    return _demo_service.get("arb", {}).get("health", {})


@api_router.get("/demo/strategies/sniper/signals")
async def demo_sniper_signals():
    return _demo_service.get("sniper", {}).get("signals", {})


@api_router.get("/demo/strategies/sniper/executions")
async def demo_sniper_executions():
    return _demo_service.get("sniper", {}).get("executions", {})


@api_router.get("/demo/strategies/sniper/health")
async def demo_sniper_health():
    return _demo_service.get("sniper", {}).get("health", {})


@api_router.get("/demo/strategies/weather/signals")
async def demo_weather_signals():
    return _demo_service.get("weather", {}).get("signals", {})


@api_router.get("/demo/strategies/weather/executions")
async def demo_weather_executions():
    return _demo_service.get("weather", {}).get("executions", {})


@api_router.get("/demo/strategies/weather/health")
async def demo_weather_health():
    return _demo_service.get("weather", {}).get("health", {})


@api_router.get("/demo/strategies/weather/forecasts")
async def demo_weather_forecasts():
    return _demo_service.get("weather", {}).get("forecasts", {})


@api_router.get("/demo/strategies/weather/stations")
async def demo_weather_stations():
    return _demo_service.get("weather", {}).get("stations", [])


@api_router.get("/demo/strategies/weather/config")
async def demo_weather_config():
    return _demo_service.get("weather", {}).get("health", {}).get("config", {})


@api_router.get("/demo/strategies/weather/shadow-summary")
async def demo_weather_shadow_summary():
    weather = _demo_service.get("weather", {})
    h = weather.get("health", {})
    return {
        "execution_mode": "shadow",
        "is_shadow": True,
        "shadow_overrides_applied": True,
        "config_snapshot": h.get("config", {}),
        "operational_stats": {
            "total_scans": h.get("total_scans", 0),
            "markets_classified": h.get("markets_classified", 0),
            "forecasts_fetched": h.get("forecasts_fetched", 0),
            "signals_generated": h.get("signals_generated", 0),
            "signals_executed": h.get("signals_executed", 0),
            "signals_filled": h.get("signals_filled", 0),
        },
        "calibration": {
            "calibration_status": "collecting",
            "using_defaults": True,
            "total_records": 15,
            "resolved_records": 8,
            "pending_resolution": 7,
        },
        "running": True,
    }


@api_router.get("/demo/strategies/weather/accuracy/history")
async def demo_accuracy_history():
    return []


@api_router.get("/demo/strategies/weather/accuracy/calibration")
async def demo_accuracy_calibration():
    return {
        "total_records": 0,
        "resolved_records": 0,
        "pending_resolution": 0,
        "stations_with_data": 0,
        "stations_calibratable": 0,
        "global_mae_f": None,
        "global_bias_f": None,
        "using_defaults": True,
        "calibration_status": "no_data",
        "calibration_note": "Demo mode — no real accuracy data",
        "station_summaries": {},
    }


@api_router.get("/demo/config")
async def demo_config():
    return _demo_service.get("config", {})


@api_router.get("/demo/config/strategies")
async def demo_config_strategies():
    cfg = _demo_service.get("config", {})
    return cfg.get("strategy_configs", {})


@api_router.get("/demo/health")
async def demo_health():
    return {"status": "healthy", "engine": "running", "mode": "paper"}


@api_router.get("/demo/health/feeds")
async def demo_feed_health():
    return _demo_service.get("feed_health", {})


@api_router.get("/demo/status-snapshot")
async def demo_status_snapshot():
    return _demo_service.get("status", {})


@api_router.get("/demo/execution/wallet")
async def demo_wallet():
    return _demo_service.get("wallet", {})


@api_router.get("/demo/execution/orders")
async def demo_execution_orders(limit: int = 50):
    orders = _demo_service.get("orders", [])
    return orders[:limit]


# ---- Wire up ----

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
