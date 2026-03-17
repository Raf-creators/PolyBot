"""Strategy performance tracker and discovery watchdog.

Tracks per-strategy metrics (PnL, win rate, trade counts) and signal rejection
diagnostics. Monitors trading activity and fires Telegram alerts when activity
drops below thresholds.
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from models import Event, EventType

logger = logging.getLogger(__name__)


class StrategyTracker:
    """Centralized per-strategy performance + diagnostics tracker."""

    def __init__(self):
        self._state = None
        self._bus = None
        self._telegram = None
        self._running = False

        # Per-strategy performance
        self._performance = defaultdict(lambda: {
            "total_pnl": 0.0,
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "last_trade_at": None,
        })

        # Signal rejection tracking (per-strategy -> reason -> count)
        self._rejections = defaultdict(lambda: defaultdict(int))
        self._rejection_log = []  # last 200 detailed entries

        # Signals generated per strategy
        self._signals = defaultdict(int)

        # Discovery watchdog
        self._watchdog = {
            "last_new_market_at": None,
            "last_trade_opened_at": None,
            "last_trade_closed_at": None,
            "no_market_alert_minutes": 30,
            "no_trade_open_alert_minutes": 60,
            "no_trade_close_alert_minutes": 120,
            "last_alert_sent_at": None,
        }
        self._watchdog_task = None

    async def start(self, state, bus, telegram=None):
        self._state = state
        self._bus = bus
        self._telegram = telegram
        self._running = True
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

        bus.on(EventType.SIGNAL, self._on_signal)
        bus.on(EventType.RISK_ALERT, self._on_risk_alert)
        bus.on(EventType.ORDER_UPDATE, self._on_order_update)

        # Rebuild from existing state
        self._rebuild_from_state()
        logger.info("StrategyTracker started with watchdog")

    async def stop(self):
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        if self._bus:
            self._bus.off(EventType.SIGNAL, self._on_signal)
            self._bus.off(EventType.RISK_ALERT, self._on_risk_alert)
            self._bus.off(EventType.ORDER_UPDATE, self._on_order_update)
        logger.info("StrategyTracker stopped")

    def _rebuild_from_state(self):
        """Reconstruct performance counters from existing trades in state."""
        if not self._state:
            return
        for trade in self._state.trades:
            sid = trade.strategy_id or "unknown"
            self._performance[sid]["total_pnl"] += trade.pnl
            self._performance[sid]["trade_count"] += 1
            if trade.pnl > 0:
                self._performance[sid]["wins"] += 1
            elif trade.pnl < 0:
                self._performance[sid]["losses"] += 1

    # ---- Public Recording API ----

    def record_signal(self, strategy_id: str, accepted: bool = True, rejection_reason: str = None):
        self._signals[strategy_id] += 1
        if not accepted and rejection_reason:
            self.record_rejection(strategy_id, rejection_reason)

    def record_rejection(self, strategy_id: str, reason: str, details: dict = None):
        self._rejections[strategy_id][reason] += 1
        entry = {
            "strategy": strategy_id,
            "reason": reason,
            "time": datetime.now(timezone.utc).isoformat(),
        }
        if details:
            entry["details"] = details
        self._rejection_log.append(entry)
        if len(self._rejection_log) > 200:
            self._rejection_log = self._rejection_log[-200:]

    def record_close(self, strategy_id: str, pnl: float):
        self._performance[strategy_id]["total_pnl"] = round(
            self._performance[strategy_id]["total_pnl"] + pnl, 4
        )
        self._performance[strategy_id]["trade_count"] += 1
        if pnl > 0:
            self._performance[strategy_id]["wins"] += 1
        elif pnl < 0:
            self._performance[strategy_id]["losses"] += 1
        self._performance[strategy_id]["last_trade_at"] = datetime.now(timezone.utc).isoformat()
        self._watchdog["last_trade_closed_at"] = datetime.now(timezone.utc).isoformat()

    def record_new_market(self):
        self._watchdog["last_new_market_at"] = datetime.now(timezone.utc).isoformat()

    def record_trade_opened(self):
        self._watchdog["last_trade_opened_at"] = datetime.now(timezone.utc).isoformat()

    # ---- Event Handlers ----

    async def _on_signal(self, event: Event):
        sid = event.data.get("strategy", "unknown")
        self.record_signal(sid)

    async def _on_risk_alert(self, event: Event):
        reason = event.data.get("reason", "unknown")
        order_id = event.data.get("order_id", "")
        # Try to identify strategy from the rejected order
        strategy = "unknown"
        if self._state and order_id in self._state.orders:
            strategy = self._state.orders[order_id].strategy_id or "unknown"
        self.record_rejection(strategy, reason)

    async def _on_order_update(self, event: Event):
        if event.data.get("status") == "filled":
            self.record_trade_opened()

    # ---- Discovery Watchdog ----

    async def _watchdog_loop(self):
        await asyncio.sleep(60)  # initial settling
        while self._running:
            try:
                await self._check_watchdog()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            await asyncio.sleep(300)  # check every 5 mins

    async def _check_watchdog(self):
        now = datetime.now(timezone.utc)
        alerts = []

        def _minutes_since(iso_str):
            if not iso_str:
                return 9999  # never happened
            try:
                ts = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                return (now - ts).total_seconds() / 60
            except Exception:
                return 9999

        no_market_mins = _minutes_since(self._watchdog["last_new_market_at"])
        no_open_mins = _minutes_since(self._watchdog["last_trade_opened_at"])
        no_close_mins = _minutes_since(self._watchdog["last_trade_closed_at"])

        if no_market_mins > self._watchdog["no_market_alert_minutes"]:
            alerts.append(f"No new markets discovered in {no_market_mins:.0f} minutes")
        if no_open_mins > self._watchdog["no_trade_open_alert_minutes"]:
            alerts.append(f"No trades opened in {no_open_mins:.0f} minutes")
        if no_close_mins > self._watchdog["no_trade_close_alert_minutes"]:
            alerts.append(f"No trades closed in {no_close_mins:.0f} minutes")

        if alerts and self._telegram and self._telegram.enabled:
            # Only alert every 30 minutes max
            last = self._watchdog.get("last_alert_sent_at")
            if last:
                mins_since_last = _minutes_since(last)
                if mins_since_last < 30:
                    return

            text = "<b>WATCHDOG ALERT</b>\n" + "\n".join(f"- {a}" for a in alerts)
            await self._telegram.send_message(text)
            self._watchdog["last_alert_sent_at"] = now.isoformat()
            logger.warning(f"Watchdog alerts: {alerts}")

    # ---- Data Access ----

    def get_performance(self) -> dict:
        result = {}
        for sid, perf in self._performance.items():
            count = perf["trade_count"]
            wins = perf["wins"]
            losses = perf["losses"]
            closes = wins + losses
            win_rate = round(wins / closes * 100, 1) if closes > 0 else 0
            result[sid] = {
                "total_pnl": round(perf["total_pnl"], 4),
                "trade_count": count,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "last_trade_at": perf["last_trade_at"],
            }
        return result

    def get_rejections(self) -> dict:
        result = {}
        for sid, reasons in self._rejections.items():
            result[sid] = dict(reasons)
        return result

    def get_rejection_log(self, limit: int = 50) -> list:
        return self._rejection_log[-limit:]

    def get_signals(self) -> dict:
        return dict(self._signals)

    def get_watchdog(self) -> dict:
        now = datetime.now(timezone.utc)

        def _age(iso_str):
            if not iso_str:
                return None
            try:
                ts = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                return round((now - ts).total_seconds() / 60, 1)
            except Exception:
                return None

        return {
            "last_new_market_at": self._watchdog["last_new_market_at"],
            "last_trade_opened_at": self._watchdog["last_trade_opened_at"],
            "last_trade_closed_at": self._watchdog["last_trade_closed_at"],
            "minutes_since_new_market": _age(self._watchdog["last_new_market_at"]),
            "minutes_since_trade_opened": _age(self._watchdog["last_trade_opened_at"]),
            "minutes_since_trade_closed": _age(self._watchdog["last_trade_closed_at"]),
            "thresholds": {
                "no_market_alert_minutes": self._watchdog["no_market_alert_minutes"],
                "no_trade_open_alert_minutes": self._watchdog["no_trade_open_alert_minutes"],
                "no_trade_close_alert_minutes": self._watchdog["no_trade_close_alert_minutes"],
            },
        }

    def get_signal_quality(self) -> dict:
        """Full signal quality report: generated, rejected, by reason."""
        result = {}
        all_strategies = set(list(self._signals.keys()) + list(self._rejections.keys()))
        for sid in all_strategies:
            generated = self._signals.get(sid, 0)
            rejections = dict(self._rejections.get(sid, {}))
            total_rejected = sum(rejections.values())
            accepted = max(0, generated - total_rejected)
            result[sid] = {
                "signals_generated": generated,
                "signals_rejected": total_rejected,
                "signals_accepted": accepted,
                "acceptance_rate": round(accepted / max(generated, 1) * 100, 1),
                "rejection_reasons": rejections,
            }
        return result

    def get_full_diagnostics(self) -> dict:
        return {
            "performance": self.get_performance(),
            "rejections": self.get_rejections(),
            "signals": self.get_signal_quality(),
            "watchdog": self.get_watchdog(),
        }
