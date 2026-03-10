import asyncio
import logging

from models import utc_now

logger = logging.getLogger(__name__)


class PersistenceService:
    """Async write-behind persistence to MongoDB. Off the hot path."""

    def __init__(self, db):
        self._db = db
        self._state = None
        self._bus = None
        self._running = False
        self._task = None
        self._last_trade_idx = 0
        self._persisted_orders = set()

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True
        self._task = asyncio.create_task(self._flush_loop())
        logger.info("PersistenceService started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        try:
            await self._flush()
        except Exception as e:
            logger.error(f"Final flush error: {e}")
        logger.info("PersistenceService stopped")

    async def _flush_loop(self):
        while self._running:
            try:
                await asyncio.sleep(10)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Persistence flush error: {e}")

    async def _flush(self):
        if not self._state:
            return

        # ---- Trades ----
        new_trades = self._state.trades[self._last_trade_idx:]
        if new_trades:
            docs = [t.model_dump() for t in new_trades]
            try:
                await self._db.trades.insert_many(docs)
                self._last_trade_idx = len(self._state.trades)
            except Exception as e:
                logger.error(f"Trade persist error: {e}")

        # ---- Completed orders ----
        terminal = {"filled", "rejected", "cancelled", "expired"}
        for oid, order in self._state.orders.items():
            if oid in self._persisted_orders:
                continue
            if order.status.value in terminal:
                try:
                    doc = order.model_dump()
                    await self._db.orders.update_one(
                        {"id": oid}, {"$set": doc}, upsert=True,
                    )
                    self._persisted_orders.add(oid)
                except Exception as e:
                    logger.error(f"Order persist error: {e}")

        # ---- Positions snapshot ----
        if self._state.positions:
            snap = [p.model_dump() for p in self._state.positions.values()]
            try:
                await self._db.positions_snapshots.update_one(
                    {"snapshot_type": "current"},
                    {"$set": {"positions": snap, "timestamp": utc_now()}},
                    upsert=True,
                )
            except Exception as e:
                logger.error(f"Position snapshot error: {e}")
