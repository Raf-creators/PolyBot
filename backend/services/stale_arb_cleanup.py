"""Stale Arb Position Cleanup Cron.

Periodically scans arb positions and auto-closes those that are:
  - Older than 48 hours (based on earliest buy trade timestamp)
  - Have negative or zero unrealized PnL

Frees trapped capital and position slots for productive strategies.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_HOURS = 4
STALE_THRESHOLD_HOURS = 48


class StaleArbCleanupService:

    def __init__(self, state, db, telegram_notifier=None):
        self._state = state
        self._db = db
        self._telegram = telegram_notifier
        self._task = None
        self._health = {
            "running": False,
            "total_runs": 0,
            "total_cleaned": 0,
            "total_capital_freed": 0.0,
            "last_run_at": None,
            "last_run_cleaned": 0,
            "last_run_capital_freed": 0.0,
        }

    async def start(self):
        self._health["running"] = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"[STALE-ARB-CLEANUP] Started (interval={CLEANUP_INTERVAL_HOURS}h, "
            f"threshold={STALE_THRESHOLD_HOURS}h)"
        )

    async def stop(self):
        self._health["running"] = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    @property
    def health(self):
        return dict(self._health)

    async def _loop(self):
        await asyncio.sleep(300)  # 5 min initial delay
        while self._health["running"]:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[STALE-ARB-CLEANUP] Loop error: {e}")
            await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)

    async def run_once(self):
        """Execute one cleanup pass."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=STALE_THRESHOLD_HOURS)
        cleaned = 0
        capital_freed = 0.0

        # Find all arb positions
        arb_token_ids = [
            tid for tid, pos in self._state.positions.items()
            if pos.strategy_id == "arb_scanner"
        ]

        if not arb_token_ids:
            self._health["last_run_at"] = now.isoformat()
            self._health["total_runs"] += 1
            return

        # For each arb position, find the earliest buy trade to determine age
        for tid in arb_token_ids:
            pos = self._state.positions.get(tid)
            if not pos:
                continue

            # Check unrealized PnL: only close if negative or near-zero
            invested = pos.size * pos.avg_cost
            unrealized = (pos.current_price - pos.avg_cost) * pos.size if pos.current_price else 0
            if unrealized > 0.05:
                continue  # Skip positions that are in profit

            # Find earliest buy trade for this token
            earliest_trade = await self._db.trades.find_one(
                {"token_id": tid, "side": "buy", "strategy_id": "arb_scanner"},
                {"_id": 0, "timestamp": 1},
                sort=[("timestamp", 1)],
            )

            if not earliest_trade or not earliest_trade.get("timestamp"):
                continue

            try:
                trade_ts = datetime.fromisoformat(
                    str(earliest_trade["timestamp"]).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue

            if trade_ts > cutoff:
                continue  # Not stale yet

            age_hours = (now - trade_ts).total_seconds() / 3600

            # Close the position
            self._state.positions.pop(tid, None)

            from models import TradeRecord
            close_trade = TradeRecord(
                id=str(uuid.uuid4()),
                order_id=f"stale-arb-cleanup-{str(uuid.uuid4())[:8]}",
                token_id=tid,
                side="sell",
                price=pos.current_price or 0.01,
                size=pos.size,
                strategy_id="arb_scanner",
                market_question=pos.market_question or "",
                outcome=getattr(pos, "outcome", ""),
                signal_reason=f"stale_arb_cleanup_{age_hours:.0f}h",
                pnl=unrealized if unrealized != 0 else -(invested),
            )
            self._state.trades.append(close_trade)
            await self._db.trades.insert_one(
                {k: v for k, v in close_trade.model_dump().items() if k != "_id"}
            )
            await self._db.positions.delete_one({"token_id": tid})

            cleaned += 1
            capital_freed += invested
            logger.info(
                f"[STALE-ARB-CLEANUP] Closed {tid[:16]}.. "
                f"age={age_hours:.0f}h invested=${invested:.2f} pnl=${close_trade.pnl:.2f}"
            )

        self._health["total_runs"] += 1
        self._health["total_cleaned"] += cleaned
        self._health["total_capital_freed"] += capital_freed
        self._health["last_run_at"] = now.isoformat()
        self._health["last_run_cleaned"] = cleaned
        self._health["last_run_capital_freed"] = round(capital_freed, 2)

        if cleaned > 0:
            logger.info(
                f"[STALE-ARB-CLEANUP] Pass complete: {cleaned} positions closed, "
                f"${capital_freed:.2f} capital freed"
            )
            if self._telegram and self._telegram.enabled:
                self._telegram._fire(
                    f"<b>STALE ARB CLEANUP</b>\n"
                    f"Closed {cleaned} arb positions (>{STALE_THRESHOLD_HOURS}h old, negative PnL)\n"
                    f"Capital freed: ${capital_freed:.2f}"
                )
        else:
            logger.info("[STALE-ARB-CLEANUP] Pass complete: no stale positions found")
