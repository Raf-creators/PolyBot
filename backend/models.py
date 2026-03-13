from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from enum import Enum
from datetime import datetime, timezone
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---- Enums ----

class TradingMode(str, Enum):
    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


class EngineStatusEnum(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class StrategyStatusEnum(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class EventType(str, Enum):
    MARKET_UPDATE = "market_update"
    PRICE_UPDATE = "price_update"
    SIGNAL = "signal"
    ORDER_REQUEST = "order_request"
    ORDER_UPDATE = "order_update"
    RISK_ALERT = "risk_alert"
    SYSTEM_EVENT = "system_event"
    ALERT = "alert"


# ---- Core Data Models ----

class MarketSnapshot(BaseModel):
    token_id: str
    condition_id: str = ""
    question: str = ""
    outcome: str = ""
    complement_token_id: Optional[str] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    mid_price: Optional[float] = None
    spread: Optional[float] = None
    last_price: Optional[float] = None
    volume_24h: float = 0.0
    liquidity: float = 0.0
    updated_at: str = Field(default_factory=utc_now)


class Position(BaseModel):
    token_id: str
    market_question: str = ""
    outcome: str = ""
    size: float = 0.0
    avg_cost: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


class OrderRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    token_id: str
    side: OrderSide
    price: float
    size: float
    filled_size: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    strategy_id: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    exchange_order_id: Optional[str] = None
    fill_price: Optional[float] = None
    slippage: Optional[float] = None
    latency_ms: Optional[float] = None


class TradeRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    order_id: str
    token_id: str
    market_question: str = ""
    outcome: str = ""
    side: OrderSide
    price: float
    size: float
    fees: float = 0.0
    pnl: float = 0.0
    strategy_id: str = ""
    signal_reason: str = ""
    timestamp: str = Field(default_factory=utc_now)


# ---- Config Models ----

class RiskConfig(BaseModel):
    max_daily_loss: float = 100.0
    max_loss_per_strategy: float = 50.0
    max_position_size: float = 25.0
    max_market_exposure: float = 50.0
    max_concurrent_positions: int = 10
    max_order_size: float = 10.0
    kill_switch_active: bool = False


class StrategyConfig(BaseModel):
    strategy_id: str
    name: str
    enabled: bool = False
    status: StrategyStatusEnum = StrategyStatusEnum.STOPPED
    parameters: Dict[str, Any] = {}


# ---- Event Models ----

class Event(BaseModel):
    type: EventType
    timestamp: str = Field(default_factory=utc_now)
    source: str = ""
    data: Dict[str, Any] = {}


# ---- API Response/Request Models ----

class ComponentStatusResponse(BaseModel):
    name: str
    status: str
    last_heartbeat: Optional[str] = None
    error: Optional[str] = None


class EngineStateResponse(BaseModel):
    status: str
    mode: str
    uptime_seconds: float
    components: List[ComponentStatusResponse]
    strategies: List[StrategyConfig]
    risk: Dict[str, Any]
    stats: Dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    trading_mode: Optional[TradingMode] = None
    risk: Optional[RiskConfig] = None
    telegram_enabled: Optional[bool] = None
    telegram_signals_enabled: Optional[bool] = None


class HealthMetrics(BaseModel):
    last_market_data_update: Optional[float] = None
    last_spot_btc_update: Optional[float] = None
    last_spot_eth_update: Optional[float] = None
    market_data_stale: bool = True
    spot_btc_stale: bool = True
    spot_eth_stale: bool = True
    last_order_latency_ms: Optional[float] = None
    binance_connected: bool = False
    polymarket_connected: bool = False
