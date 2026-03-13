import logging

from models import Event, EventType, OrderRecord

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Handles order routing to the correct adapter (paper or live)."""

    def __init__(self):
        self._state = None
        self._bus = None
        self._running = False
        self._paper_adapter = None
        self._live_adapter = None
        self._pending_order_service = None  # Store until adapter ready

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True

        from engine.paper import PaperAdapter
        self._paper_adapter = PaperAdapter(state, bus)

        from engine.live_adapter import LiveAdapter
        self._live_adapter = LiveAdapter(state, bus)

        # Wire pending order service if set before start
        if self._pending_order_service:
            self._live_adapter.set_order_service(self._pending_order_service)

        # Try to initialize live adapter (non-blocking, fails gracefully)
        try:
            await self._live_adapter.initialize()
        except Exception as e:
            logger.warning(f"Live adapter init failed (non-fatal): {e}")

        self._bus.on(EventType.ORDER_UPDATE, self._on_risk_approved)
        logger.info("Execution engine started")

    def set_live_order_service(self, service):
        """Wire the live order persistence service after init."""
        self._pending_order_service = service  # Store for when adapter starts
        if self._live_adapter:
            self._live_adapter.set_order_service(service)

    async def start_live_polling(self):
        """Start background polling for live order statuses."""
        if self._live_adapter and self._live_adapter._authenticated:
            await self._live_adapter.start_polling()

    async def stop(self):
        self._running = False
        if self._live_adapter:
            await self._live_adapter.stop_polling()
        if self._bus:
            self._bus.off(EventType.ORDER_UPDATE, self._on_risk_approved)
        logger.info("Execution engine stopped")

    async def submit_order(self, order: OrderRecord):
        if not self._running:
            return
        self._state.add_order(order)

        mode = self._state.trading_mode.value
        if mode == "paper":
            await self._paper_adapter.execute(order)
        elif mode == "live":
            if self._live_adapter and self._live_adapter._authenticated:
                await self._live_adapter.execute(order)
            else:
                logger.warning(f"Live mode but adapter not authenticated. Falling back to paper for order {order.id}")
                await self._paper_adapter.execute(order)
        elif mode == "shadow":
            logger.info(f"[SHADOW] Would submit live: {order.side.value} {order.size}@{order.price} token={order.token_id[:12]}...")
            await self._paper_adapter.execute(order)
        else:
            await self._paper_adapter.execute(order)

    async def _on_risk_approved(self, event: Event):
        if event.source != "risk_engine":
            return
        if not event.data.get("_risk_approved"):
            return
        data = {k: v for k, v in event.data.items() if not k.startswith("_")}
        order = OrderRecord(**data)
        await self.submit_order(order)

    @property
    def live_adapter_status(self) -> dict:
        if self._live_adapter:
            return self._live_adapter.status
        from engine.live_adapter import LiveAdapter
        return {
            "adapter": "live",
            "authenticated": False,
            "credentials": LiveAdapter.credentials_present(),
            "total_submitted": 0, "total_filled": 0, "total_partial_fills": 0,
            "total_failed": 0, "total_cancelled": 0, "total_slippage_rejected": 0,
            "open_orders": 0, "partial_orders": 0,
            "last_api_call": None, "last_status_refresh": None,
            "last_error": "engine not started", "recent_errors": [],
            "fill_update_method": "polling", "poll_interval_seconds": 5,
        }
