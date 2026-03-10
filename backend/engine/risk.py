import logging

from models import Event, EventType, OrderRecord, OrderStatus

logger = logging.getLogger(__name__)


class RiskEngine:
    """Gates all order requests. Enforces limits, kill switch, exposure checks."""

    def __init__(self):
        self._state = None
        self._bus = None
        self._running = False

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True
        self._bus.on(EventType.ORDER_REQUEST, self._on_order_request)
        logger.info("Risk engine started")

    async def stop(self):
        self._running = False
        if self._bus:
            self._bus.off(EventType.ORDER_REQUEST, self._on_order_request)
        logger.info("Risk engine stopped")

    def check_order(self, order: OrderRecord) -> tuple:
        """Returns (approved: bool, reason: str)."""
        if not self._state:
            return False, "risk engine not initialized"

        cfg = self._state.risk_config

        if cfg.kill_switch_active:
            return False, "kill switch active"

        if order.size > cfg.max_order_size:
            return False, f"order size {order.size} > max {cfg.max_order_size}"

        existing = self._state.get_position(order.token_id)
        projected = (existing.size if existing else 0) + order.size
        if projected > cfg.max_position_size:
            return False, f"projected position {projected} > max {cfg.max_position_size}"

        if len(self._state.positions) >= cfg.max_concurrent_positions:
            if order.token_id not in self._state.positions:
                return False, f"max concurrent positions ({cfg.max_concurrent_positions}) reached"

        if self._state.daily_pnl <= -cfg.max_daily_loss:
            return False, f"daily loss limit hit ({self._state.daily_pnl})"

        return True, "approved"

    async def _on_order_request(self, event: Event):
        order = OrderRecord(**event.data)
        approved, reason = self.check_order(order)

        if approved:
            await self._bus.emit(Event(
                type=EventType.ORDER_UPDATE,
                source="risk_engine",
                data={**order.model_dump(), "_risk_approved": True},
            ))
        else:
            logger.warning(f"Order {order.id} rejected: {reason}")
            order.status = OrderStatus.REJECTED
            self._state.update_order(order.id, status=OrderStatus.REJECTED)
            await self._bus.emit(Event(
                type=EventType.RISK_ALERT,
                source="risk_engine",
                data={"order_id": order.id, "reason": reason},
            ))

    async def activate_kill_switch(self, reason: str = "manual"):
        if self._state:
            self._state.risk_config.kill_switch_active = True
            logger.warning(f"KILL SWITCH ACTIVATED: {reason}")
            if self._bus:
                await self._bus.emit(Event(
                    type=EventType.RISK_ALERT,
                    source="risk_engine",
                    data={"action": "kill_switch_activated", "reason": reason},
                ))

    async def deactivate_kill_switch(self):
        if self._state:
            self._state.risk_config.kill_switch_active = False
            logger.info("Kill switch deactivated")
