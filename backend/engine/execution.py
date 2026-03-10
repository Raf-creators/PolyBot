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

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True

        from engine.paper import PaperAdapter
        self._paper_adapter = PaperAdapter(state, bus)

        self._bus.on(EventType.ORDER_UPDATE, self._on_risk_approved)
        logger.info("Execution engine started")

    async def stop(self):
        self._running = False
        if self._bus:
            self._bus.off(EventType.ORDER_UPDATE, self._on_risk_approved)
        logger.info("Execution engine stopped")

    async def submit_order(self, order: OrderRecord):
        if not self._running:
            return
        self._state.add_order(order)

        if self._state.trading_mode.value == "paper":
            await self._paper_adapter.execute(order)
        else:
            # Live / shadow adapters added in later phases
            logger.info(f"Live execution not implemented. Order {order.id} queued.")

    async def _on_risk_approved(self, event: Event):
        """Only process events from risk_engine with approval flag."""
        if event.source != "risk_engine":
            return
        if not event.data.get("_risk_approved"):
            return

        data = {k: v for k, v in event.data.items() if not k.startswith("_")}
        order = OrderRecord(**data)
        await self.submit_order(order)
