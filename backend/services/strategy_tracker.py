"""Strategy performance tracker and discovery watchdog.

Tracks per-strategy metrics (PnL, win rate, trade counts) and signal rejection
diagnostics. Monitors trading activity and fires Telegram alerts when activity
drops below thresholds.
"""

import asyncio
import logging
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

        # Signal rejection tracking
        self._rejections = defaultdict(lambda: defaultdict(int))
        self._rejection_log = []

        # Signals per strategy
        self._signals = defaultdict(int)

        # Discovery watchdog — timestamps initialised to None,
        # populated on first event; watchdog ignores None timestamps
        self._watchdog = {
            "last_new_market_at": None,
            "last_trade_opened_at": None,
            "last_trade_closed_at": None,
            "no_market_alert_minutes": 30,
            "no_trade_open_alert_minutes": 60,
            "no_trade_close_alert_minutes": 120,
        }

        # Per-condition dedup: condition → last_alert_time
        self._alert_dedup = {}
        self._watchdog_task = None
        self._started_at = None

    async def start(self, state, bus, telegram=None):
        self._state = state
        self._bus = bus
        self._telegram = telegram
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

        bus.on(EventType.SIGNAL, self._on_signal)
        bus.on(EventType.RISK_ALERT, self._on_risk_alert)
        bus.on(EventType.ORDER_UPDATE, self._on_order_update)

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

    # ---- Recording API ----

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
        strategy = "unknown"
        if self._state and order_id in self._state.orders:
            strategy = self._state.orders[order_id].strategy_id or "unknown"
        self.record_rejection(strategy, reason)

    async def _on_order_update(self, event: Event):
        if event.data.get("status") == "filled":
            self.record_trade_opened()

    # ---- Discovery Watchdog ----

    async def _watchdog_loop(self):
        await asyncio.sleep(120)  # wait 2 min after start before first check
        while self._running:
            try:
                await self._check_watchdog()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            await asyncio.sleep(300)  # check every 5 min

    async def _check_watchdog(self):
        now = datetime.now(timezone.utc)
        alerts = []

        def _minutes_since(iso_str):
            """Returns minutes since timestamp, or None if not yet recorded."""
            if not iso_str:
                return None
            try:
                ts = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
                return (now - ts).total_seconds() / 60
            except Exception:
                return None

        checks = [
            ("no_markets", self._watchdog["last_new_market_at"],
             self._watchdog["no_market_alert_minutes"],
             "No new markets discovered"),
            ("no_trade_open", self._watchdog["last_trade_opened_at"],
             self._watchdog["no_trade_open_alert_minutes"],
             "No trades opened"),
            ("no_trade_close", self._watchdog["last_trade_closed_at"],
             self._watchdog["no_trade_close_alert_minutes"],
             "No trades closed"),
        ]

        for condition_key, ts_str, threshold, message in checks:
            mins = _minutes_since(ts_str)

            # Skip if never recorded AND service started < threshold minutes ago
            if mins is None:
                uptime_mins = (now - self._started_at).total_seconds() / 60 if self._started_at else 0
                if uptime_mins < threshold:
                    continue  # too early to alert
                mins = uptime_mins  # use uptime as elapsed time

            if mins <= threshold:
                # Condition cleared — reset dedup so next breach triggers alert
                self._alert_dedup.pop(condition_key, None)
                continue

            # Check dedup — only alert once per condition until it clears
            last_alert = self._alert_dedup.get(condition_key)
            if last_alert:
                since_last = (now - last_alert).total_seconds() / 60
                if since_last < 30:  # don't re-alert within 30 min
                    continue

            alerts.append(f"{message} in {mins:.0f} min (threshold: {threshold} min)")
            self._alert_dedup[condition_key] = now

        if alerts and self._telegram and self._telegram.enabled:
            text = "<b>WATCHDOG ALERT</b>\n" + "\n".join(f"- {a}" for a in alerts)
            await self._telegram.send_message(text)
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
        return {sid: dict(reasons) for sid, reasons in self._rejections.items()}

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
                ts = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
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
            "uptime_minutes": round((now - self._started_at).total_seconds() / 60, 1) if self._started_at else 0,
        }

    def get_signal_quality(self) -> dict:
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
