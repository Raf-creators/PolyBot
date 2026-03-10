import asyncio
import logging
import time
from typing import List

from models import EngineStatusEnum, Event, EventType
from engine.state import StateManager
from engine.events import EventBus
from engine.risk import RiskEngine
from engine.execution import ExecutionEngine
from engine.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class TradingEngine:
    """Orchestrator. Manages lifecycle of all engine components."""

    def __init__(self, state: StateManager, bus: EventBus):
        self.state = state
        self.bus = bus
        self.risk_engine = RiskEngine()
        self.execution_engine = ExecutionEngine()
        self._strategies: List[BaseStrategy] = []
        self._running = False
        # Phase 2 components (set before start)
        self.market_data = None
        self.price_feeds = None
        self.persistence = None

    def register_strategy(self, strategy: BaseStrategy):
        self._strategies.append(strategy)
        self.state.strategies[strategy.strategy_id] = strategy.get_config()
        logger.info(f"Registered strategy: {strategy.name}")

    async def start(self):
        if self._running:
            logger.warning("Engine already running")
            return

        logger.info(f"Starting engine in {self.state.trading_mode.value} mode")
        self.state.engine_status = EngineStatusEnum.STARTING
        self.state.start_time = time.time()

        try:
            # 1. Event bus
            await self.bus.start()
            self.state.register_component("event_bus", "running")

            # 2. Market data feed
            if self.market_data:
                try:
                    await self.market_data.start(self.state, self.bus)
                    self.state.register_component("market_data", "running")
                except Exception as e:
                    logger.warning(f"Market data start failed (non-fatal): {e}")
                    self.state.register_component("market_data", "error")

            # 3. Price feeds
            if self.price_feeds:
                try:
                    await self.price_feeds.start(self.state, self.bus)
                    self.state.register_component("price_feeds", "running")
                except Exception as e:
                    logger.warning(f"Price feeds start failed (non-fatal): {e}")
                    self.state.register_component("price_feeds", "error")

            # 4. Risk engine
            await self.risk_engine.start(self.state, self.bus)
            self.state.register_component("risk_engine", "running")

            # 5. Execution engine
            await self.execution_engine.start(self.state, self.bus)
            self.state.register_component("execution_engine", "running")

            # 6. Persistence
            if self.persistence:
                await self.persistence.start(self.state, self.bus)
                self.state.register_component("persistence", "running")

            # 7. Strategies (only enabled ones)
            for strategy in self._strategies:
                cfg = self.state.strategies.get(strategy.strategy_id)
                if cfg and cfg.enabled:
                    await strategy.start(self.state, self.bus)
                    self.state.update_component(strategy.name, "running")
                else:
                    self.state.register_component(strategy.name, "disabled")

            self._running = True
            self.state.engine_status = EngineStatusEnum.RUNNING

            await self.bus.emit(Event(
                type=EventType.SYSTEM_EVENT,
                source="engine",
                data={"action": "started", "mode": self.state.trading_mode.value},
            ))
            logger.info("Engine started")

        except Exception as e:
            logger.error(f"Engine start failed: {e}", exc_info=True)
            self.state.engine_status = EngineStatusEnum.ERROR
            await self._force_stop()
            raise

    async def stop(self):
        if not self._running and self.state.engine_status == EngineStatusEnum.STOPPED:
            return
        logger.info("Stopping engine")
        self.state.engine_status = EngineStatusEnum.STOPPING
        await self._force_stop()
        logger.info("Engine stopped")

    async def _force_stop(self):
        """Stop all components in reverse order."""
        for strategy in reversed(self._strategies):
            try:
                await strategy.stop()
                self.state.update_component(strategy.name, "stopped")
            except Exception as e:
                logger.error(f"Error stopping {strategy.name}: {e}")

        components = [
            ("persistence", self.persistence),
            ("execution_engine", self.execution_engine),
            ("risk_engine", self.risk_engine),
            ("price_feeds", self.price_feeds),
            ("market_data", self.market_data),
            ("event_bus", self.bus),
        ]
        for name, component in components:
            if component is None:
                continue
            try:
                await component.stop()
                self.state.update_component(name, "stopped")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

        self._running = False
        self.state.engine_status = EngineStatusEnum.STOPPED

    @property
    def is_running(self) -> bool:
        return self._running
