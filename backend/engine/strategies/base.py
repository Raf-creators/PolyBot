from abc import ABC, abstractmethod

from models import StrategyConfig, StrategyStatusEnum


class BaseStrategy(ABC):
    """Interface that all strategies must implement."""

    def __init__(self, strategy_id: str, name: str):
        self.strategy_id = strategy_id
        self.name = name
        self._state = None
        self._bus = None
        self._running = False

    @abstractmethod
    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True

    @abstractmethod
    async def stop(self):
        self._running = False

    @abstractmethod
    async def on_market_update(self, event):
        """React to market data changes. Emit signals here."""
        pass

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            strategy_id=self.strategy_id,
            name=self.name,
            enabled=False,
            status=StrategyStatusEnum.ACTIVE if self._running else StrategyStatusEnum.STOPPED,
        )

    @property
    def is_running(self) -> bool:
        return self._running
