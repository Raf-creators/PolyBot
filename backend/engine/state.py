import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from models import (
    MarketSnapshot, Position, OrderRecord, TradeRecord,
    RiskConfig, StrategyConfig, EngineStatusEnum, TradingMode,
    EngineStateResponse, ComponentStatusResponse, utc_now,
)

logger = logging.getLogger(__name__)


class StateManager:
    """Single source of truth for all engine state. In-memory, pub/sub enabled."""

    def __init__(self):
        # Market state
        self.markets: Dict[str, MarketSnapshot] = {}
        self.spot_prices: Dict[str, float] = {}

        # Trading state
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, OrderRecord] = {}
        self.trades: List[TradeRecord] = []

        # Engine state
        self.engine_status: EngineStatusEnum = EngineStatusEnum.STOPPED
        self.trading_mode: TradingMode = TradingMode.PAPER
        self.start_time: Optional[float] = None

        # Config
        self.risk_config: RiskConfig = RiskConfig()
        self.strategies: Dict[str, StrategyConfig] = {}

        # Component tracking
        self._components: Dict[str, ComponentStatusResponse] = {}

        # Stats
        self.daily_pnl: float = 0.0
        self.total_trades: int = 0
        self.win_count: int = 0
        self.loss_count: int = 0

        # Internal pub/sub
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

    # ---- Pub/Sub ----

    def subscribe(self, channel: str, callback: Callable):
        self._subscribers[channel].append(callback)

    async def publish(self, channel: str, data: Any = None):
        for cb in self._subscribers.get(channel, []):
            try:
                result = cb(channel, data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"State subscriber error on {channel}: {e}")

    # ---- Market State ----

    def update_market(self, token_id: str, snapshot: MarketSnapshot):
        self.markets[token_id] = snapshot

    def get_market(self, token_id: str) -> Optional[MarketSnapshot]:
        return self.markets.get(token_id)

    def update_spot_price(self, symbol: str, price: float):
        self.spot_prices[symbol] = price

    def get_spot_price(self, symbol: str) -> Optional[float]:
        return self.spot_prices.get(symbol)

    # ---- Position State ----

    def update_position(self, token_id: str, position: Position):
        if position.size == 0:
            self.positions.pop(token_id, None)
        else:
            self.positions[token_id] = position

    def get_position(self, token_id: str) -> Optional[Position]:
        return self.positions.get(token_id)

    # ---- Order State ----

    def add_order(self, order: OrderRecord):
        self.orders[order.id] = order

    def update_order(self, order_id: str, **kwargs):
        if order_id in self.orders:
            current = self.orders[order_id].model_dump()
            current.update(kwargs)
            # Convert enum values back if needed
            if "status" in kwargs and hasattr(kwargs["status"], "value"):
                current["status"] = kwargs["status"].value
            if "side" in current and hasattr(current["side"], "value"):
                current["side"] = current["side"]
            self.orders[order_id] = OrderRecord(**current)

    def get_open_orders(self) -> List[OrderRecord]:
        open_statuses = {"pending", "submitted", "partially_filled"}
        return [o for o in self.orders.values() if o.status.value in open_statuses]

    # ---- Trade State ----

    def add_trade(self, trade: TradeRecord):
        self.trades.append(trade)
        self.total_trades += 1
        if trade.pnl > 0:
            self.win_count += 1
        elif trade.pnl < 0:
            self.loss_count += 1
        self.daily_pnl += trade.pnl

    # ---- Component Tracking ----

    def register_component(self, name: str, status: str = "stopped"):
        self._components[name] = ComponentStatusResponse(name=name, status=status)

    def update_component(self, name: str, status: str, error: Optional[str] = None):
        self._components[name] = ComponentStatusResponse(
            name=name, status=status, last_heartbeat=utc_now(), error=error
        )

    # ---- Snapshot (for dashboard / cold path) ----

    def snapshot(self) -> dict:
        uptime = time.time() - self.start_time if self.start_time else 0.0
        win_rate = (self.win_count / self.total_trades * 100) if self.total_trades > 0 else 0.0

        return EngineStateResponse(
            status=self.engine_status.value,
            mode=self.trading_mode.value,
            uptime_seconds=round(uptime, 1),
            components=list(self._components.values()),
            strategies=list(self.strategies.values()),
            risk=self.risk_config.model_dump(),
            stats={
                "daily_pnl": round(self.daily_pnl, 4),
                "total_trades": self.total_trades,
                "win_count": self.win_count,
                "loss_count": self.loss_count,
                "win_rate": round(win_rate, 2),
                "open_positions": len(self.positions),
                "open_orders": len(self.get_open_orders()),
                "markets_tracked": len(self.markets),
                "spot_prices": dict(self.spot_prices),
            },
        ).model_dump()
