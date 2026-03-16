import asyncio
import logging
from datetime import datetime, timezone

from models import TradeRecord, Position, utc_now

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

    async def load_state_from_db(self, state):
        """Reconstruct in-memory state from MongoDB on startup.

        Loads all persisted trades and the last positions snapshot so that
        after a Railway restart the dashboard immediately reflects historical
        closed-trade analytics (PnL, win rate, close count).
        """
        # ---- Load trades ----
        try:
            cursor = self._db.trades.find(
                {}, {"_id": 0}
            ).sort("timestamp", 1)
            docs = await cursor.to_list(length=50_000)
            if docs:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                for doc in docs:
                    try:
                        trade = TradeRecord(**doc)
                        state.trades.append(trade)
                        state.total_trades += 1
                        if trade.pnl > 0:
                            state.win_count += 1
                        elif trade.pnl < 0:
                            state.loss_count += 1
                        # daily_pnl: only sum today's closed trades
                        ts = trade.timestamp
                        trade_day = ts[:10] if isinstance(ts, str) else (
                            ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else ""
                        )
                        if trade_day == today and trade.pnl != 0:
                            state.daily_pnl += trade.pnl
                    except Exception as e:
                        logger.warning(f"Skip malformed trade doc: {e}")
                logger.info(
                    f"[PERSISTENCE] Loaded {len(state.trades)} trades from MongoDB "
                    f"(wins={state.win_count}, losses={state.loss_count}, "
                    f"daily_pnl=${state.daily_pnl:.4f})"
                )
        except Exception as e:
            logger.error(f"[PERSISTENCE] Trade load error: {e}")

        # ---- Load positions snapshot ----
        try:
            snap_doc = await self._db.positions_snapshots.find_one(
                {"snapshot_type": "current"}, {"_id": 0}
            )
            if snap_doc and snap_doc.get("positions"):
                for pdoc in snap_doc["positions"]:
                    try:
                        pos = Position(**pdoc)
                        state.positions[pos.token_id] = pos
                    except Exception as e:
                        logger.warning(f"Skip malformed position doc: {e}")
                logger.info(
                    f"[PERSISTENCE] Loaded {len(state.positions)} positions from snapshot"
                )
        except Exception as e:
            logger.error(f"[PERSISTENCE] Position load error: {e}")

        # Mark all loaded trades as already persisted so flush doesn't
        # re-insert them into MongoDB.
        self._last_trade_idx = len(state.trades)

        # Mark all loaded orders as already persisted
        try:
            cursor = self._db.orders.find({}, {"_id": 0, "id": 1})
            order_docs = await cursor.to_list(length=50_000)
            for od in order_docs:
                if od.get("id"):
                    self._persisted_orders.add(od["id"])
        except Exception as e:
            logger.warning(f"[PERSISTENCE] Order ID preload error: {e}")

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

        # ---- Arb opportunities log ----
        if self._state.arb_opportunities_log:
            batch = self._state.arb_opportunities_log[:]
            self._state.arb_opportunities_log.clear()
            try:
                await self._db.arb_opportunities.insert_many(batch)
            except Exception as e:
                logger.error(f"Arb opportunities persist error: {e}")

        # ---- Arb executions log ----
        if self._state.arb_executions_log:
            batch = self._state.arb_executions_log[:]
            self._state.arb_executions_log.clear()
            try:
                await self._db.arb_executions.insert_many(batch)
            except Exception as e:
                logger.error(f"Arb executions persist error: {e}")
