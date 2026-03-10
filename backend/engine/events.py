import asyncio
import logging
from collections import defaultdict
from typing import Callable, Dict, List, Optional

from models import Event, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """Central event bus. asyncio.Queue-backed, serial dispatch per event."""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._event_count = 0

    def on(self, event_type: EventType, handler: Callable):
        self._handlers[event_type.value].append(handler)

    def off(self, event_type: EventType, handler: Callable):
        handlers = self._handlers.get(event_type.value, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: Event):
        await self._queue.put(event)
        self._event_count += 1

    async def _process_loop(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                channel = event.type.value if isinstance(event.type, EventType) else event.type
                for handler in self._handlers.get(channel, []):
                    try:
                        result = handler(event)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.error(f"Handler error on {channel}: {e}", exc_info=True)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"EventBus error: {e}", exc_info=True)

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("EventBus started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"EventBus stopped ({self._event_count} events processed)")

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()
