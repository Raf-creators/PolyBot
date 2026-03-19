"""Telegram notification service — all strategies, clear formatting.

Format every closed trade as:
[CRYPTO] / [WEATHER] / [ARB]
Market: ...
Side: YES/NO
Entry: X
Exit: X
PnL: $X
ROI: X%
Time: X
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MSGS_PER_MINUTE = 20

# Map strategy IDs and keywords to short labels
_STRATEGY_LABELS = {
    "crypto_sniper": "CRYPTO",
    "weather_trader": "WEATHER",
    "arb_scanner": "ARB",
    "resolver": "RESOLVER",
}

_WEATHER_KW = ("temperature", "highest temp", "weather", "°f", "°c")
_CRYPTO_KW = ("btc", "bitcoin", "eth", "ethereum", "up or down")


def _label_from_question(q: str) -> str:
    ql = q.lower()
    if any(kw in ql for kw in _WEATHER_KW):
        return "WEATHER"
    if any(kw in ql for kw in _CRYPTO_KW):
        return "CRYPTO"
    return "UNKNOWN"


class TelegramNotifier:
    def __init__(self):
        self._token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self._chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self._enabled = False
        self._signals_enabled = False
        self._client: Optional[httpx.AsyncClient] = None
        self._bus = None
        self._state = None
        self._send_times: list = []
        self._total_sent = 0
        self._total_failed = 0
        self._strategy_refs: dict = {}
        self._upgrade_baseline: dict = {}
        self._upgrade_tracking_task = None

    @property
    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    @property
    def enabled(self) -> bool:
        return self._enabled and self.configured

    @property
    def signals_enabled(self) -> bool:
        return self._signals_enabled and self.enabled

    @property
    def stats(self) -> dict:
        return {
            "configured": self.configured,
            "enabled": self._enabled,
            "signals_enabled": self._signals_enabled,
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
        }

    def configure(self, enabled: bool, signals_enabled: bool):
        self._enabled = enabled
        self._signals_enabled = signals_enabled

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._client = httpx.AsyncClient(timeout=10)
        self._digest_task = None
        self._strategy_refs = {}  # set from server.py: {"weather": ref, "arb": ref, "crypto": ref}

        from models import EventType
        bus.on(EventType.ORDER_UPDATE, self._on_order_update)
        bus.on(EventType.SYSTEM_EVENT, self._on_system_event)

        # Start periodic digest (every 3 hours)
        self._digest_task = asyncio.create_task(self._periodic_digest_loop())

        status = "enabled" if self.configured else "disabled (no credentials)"
        logger.info(f"Telegram notifier started [{status}]")

    async def stop(self):
        if self._digest_task:
            self._digest_task.cancel()
            try:
                await self._digest_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._bus:
            from models import EventType
            self._bus.off(EventType.ORDER_UPDATE, self._on_order_update)
            self._bus.off(EventType.SYSTEM_EVENT, self._on_system_event)
        if self._client:
            await self._client.aclose()

    # ---- Rate limiter ----

    def _rate_ok(self) -> bool:
        now = time.time()
        self._send_times = [t for t in self._send_times if now - t < 60]
        return len(self._send_times) < MAX_MSGS_PER_MINUTE

    # ---- Core send ----

    async def send_message(self, text: str) -> bool:
        if not self.configured:
            return False
        if not self._rate_ok():
            logger.warning("Telegram rate limit hit")
            return False

        url = TELEGRAM_API.format(token=self._token)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            resp = await self._client.post(url, json=payload)
            if resp.status_code == 200:
                self._send_times.append(time.time())
                self._total_sent += 1
                return True
            else:
                logger.warning(f"Telegram API {resp.status_code}")
                self._total_failed += 1
                return False
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")
            self._total_failed += 1
            return False

    def _fire(self, text: str):
        asyncio.create_task(self.send_message(text))

    # ---- Event Handlers ----

    async def _on_order_update(self, event):
        if not self.enabled:
            return
        if event.data.get("status") == "closed":
            self._send_trade_closed(event.data)

    async def _on_system_event(self, event):
        if not self.enabled:
            return
        if event.source == "market_resolver" and event.data.get("action") == "positions_resolved":
            count = event.data.get("count", 0)
            if count > 0:
                self._send_resolver_trades(count)

    # ---- Trade Close Notifications ----

    def _resolve_label(self, strategy_id: str, market_question: str) -> str:
        """Get [CRYPTO] / [WEATHER] / [ARB] label."""
        label = _STRATEGY_LABELS.get(strategy_id or "")
        if label and label != "RESOLVER":
            return label
        # For resolver or unknown, infer from question
        return _label_from_question(market_question or "")

    def _send_trade_closed(self, data: dict):
        trade = self._find_trade(data.get("order_id", ""))

        strategy_id = data.get("strategy_id") or ""
        market = (data.get("market_question") or "")[:80]
        outcome = data.get("outcome", data.get("side", "?"))
        entry_price = data.get("entry_price", 0)
        exit_price = data.get("exit_price", data.get("fill_price", 0))
        pnl = data.get("pnl", 0)
        size = data.get("size", 1)

        if trade:
            strategy_id = trade.strategy_id or strategy_id
            market = (trade.market_question or market)[:80]
            outcome = trade.outcome or trade.side.value
            entry_price = entry_price or trade.price
            exit_price = exit_price or trade.price
            pnl = trade.pnl if trade.pnl else pnl
            size = trade.size

        label = self._resolve_label(strategy_id, market)
        self._send_formatted(label, market, outcome, entry_price, exit_price, pnl, size)

    def _send_resolver_trades(self, count: int):
        if not self._state:
            return

        resolver_trades = []
        for t in reversed(self._state.trades):
            if t.strategy_id == "resolver":
                resolver_trades.append(t)
                if len(resolver_trades) >= count:
                    break

        for t in resolver_trades:
            market = (t.market_question or "?")[:80]
            label = self._resolve_label("resolver", market)
            outcome = t.outcome or "?"
            exit_price = t.price
            pnl = t.pnl or 0
            size = t.size
            entry_price = round(exit_price - (pnl / size), 4) if size else 0
            self._send_formatted(label, market, outcome, entry_price, exit_price, pnl, size)

    def _send_formatted(self, label, market, outcome, entry_price, exit_price, pnl, size):
        """Structured Telegram message with clear strategy label."""
        cost = abs(entry_price * size) if entry_price and size else 0
        roi = (pnl / cost * 100) if cost > 0 else 0
        pnl_sign = "+" if pnl >= 0 else ""
        roi_sign = "+" if roi >= 0 else ""
        emoji = "+" if pnl >= 0 else "-"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        text = (
            f"<b>[{label}] TRADE CLOSED {emoji}</b>\n"
            f"\n"
            f"Market: {market}\n"
            f"Side: {outcome}\n"
            f"Entry: {entry_price:.4f}\n"
            f"Exit: {exit_price:.4f}\n"
            f"PnL: <b>{pnl_sign}${pnl:.2f}</b>\n"
            f"ROI: {roi_sign}{roi:.1f}%\n"
            f"Time: {ts}"
        )
        self._fire(text)

    def _find_trade(self, order_id):
        if self._state:
            for t in reversed(self._state.trades):
                if t.order_id == order_id:
                    return t
        return None


    def set_strategy_refs(self, refs: dict):
        """Set references to strategy instances for digest metrics."""
        self._strategy_refs = refs

    async def _periodic_digest_loop(self):
        """Send a system digest every 3 hours."""
        await asyncio.sleep(300)  # wait 5 min after startup for data to accumulate
        while True:
            try:
                await self._send_digest()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[TELEGRAM] Digest error: {e}")
            await asyncio.sleep(3 * 3600)  # 3 hours

    async def _send_digest(self):
        """Build and send a structured system performance digest with rolling PnL windows."""
        if not self.enabled or not self._state:
            return

        from engine.risk import classify_strategy
        from services.rolling_pnl import compute_rolling_pnl, format_rolling_pnl_text

        state = self._state
        cfg = state.risk_config

        # Rolling PnL windows (trade-timestamp based, not uptime)
        rolling = compute_rolling_pnl(state.trades)

        # Position counts and exposure by strategy
        pos_counts = {"crypto": 0, "weather": 0, "arb": 0}
        exposure = {"crypto": 0.0, "weather": 0.0, "arb": 0.0}
        unrealized = {"crypto": 0.0, "weather": 0.0, "arb": 0.0}

        for pos in state.positions.values():
            bucket = classify_strategy(pos)
            pos_counts[bucket] = pos_counts.get(bucket, 0) + 1
            exp = pos.size * (pos.current_price or pos.avg_cost or 0)
            exposure[bucket] = exposure.get(bucket, 0) + exp
            unrealized[bucket] = unrealized.get(bucket, 0) + (pos.current_price - pos.avg_cost) * pos.size

        total_realized = sum(t.pnl for t in state.trades if t.pnl)
        total_unrealized = sum(unrealized.values())
        total_exposure = sum(exposure.values())
        total_positions = sum(pos_counts.values())

        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")

        # Arb stats
        arb_opps = 0
        arb_exec = 0
        arb_ref = self._strategy_refs.get("arb")
        if arb_ref:
            ah = arb_ref.get_health()
            arb_opps = ah.get("eligible_count", 0)
            arb_exec = ah.get("executions_submitted", 0)

        # Weather exit candidates
        exit_candidates = 0
        weather_ref = self._strategy_refs.get("weather")
        if weather_ref:
            exit_candidates = weather_ref._m.get("lifecycle", {}).get("exit_candidates", 0)

        lines = [
            f"<b>SYSTEM DIGEST</b> {ts}",
            "",
            f"PnL: <b>${total_realized + total_unrealized:+.2f}</b> (R: ${total_realized:+.2f} / U: ${total_unrealized:+.2f})",
            f"Exposure: ${total_exposure:.0f} / ${cfg.max_market_exposure:.0f} ({total_exposure/max(cfg.max_market_exposure,1)*100:.0f}%)",
            f"Positions: {total_positions} / {cfg.max_concurrent_positions}",
            "",
            "<b>=== PnL/hour (rolling windows) ===</b>",
            format_rolling_pnl_text(rolling),
            "",
            f"Arb: {arb_opps} opps | {arb_exec} executed",
            f"Weather exits: {exit_candidates} candidates",
        ]

        # Large win/loss alerts
        recent_trades = state.trades[-20:] if state.trades else []
        big_wins = [t for t in recent_trades if t.pnl > 1.0]
        big_losses = [t for t in recent_trades if t.pnl < -1.0]
        if big_wins:
            lines.append(f"\nBig wins: {len(big_wins)} (best ${max(t.pnl for t in big_wins):+.2f})")
        if big_losses:
            lines.append(f"Big losses: {len(big_losses)} (worst ${min(t.pnl for t in big_losses):+.2f})")

        text = "\n".join(lines)
        self._fire(text)
        logger.info("[TELEGRAM] Periodic digest sent")

    # ---- UPGRADE TRACKING SYSTEM ----

    def capture_baseline(self):
        """Capture current absolute metric values as a baseline for before/after comparison.

        Records raw totals at deploy time. Later updates compute incremental
        performance (new PnL, new trades) since this snapshot.
        """
        if not self._state:
            return
        from engine.risk import classify_strategy

        state = self._state

        # PnL by strategy — absolute totals at deploy time
        pnl_map = {}
        trade_count_map = {}
        for t in state.trades:
            sid = t.strategy_id or "unknown"
            bucket = "crypto" if "crypto" in sid or "sniper" in sid else \
                     "weather" if "weather" in sid else \
                     "arb" if "arb" in sid else "other"
            pnl_map[bucket] = pnl_map.get(bucket, 0) + t.pnl
            trade_count_map[bucket] = trade_count_map.get(bucket, 0) + 1

        # Exposure
        exposure = {"crypto": 0.0, "weather": 0.0, "arb": 0.0}
        pos_counts = {"crypto": 0, "weather": 0, "arb": 0}
        for pos in state.positions.values():
            bucket = classify_strategy(pos)
            pos_counts[bucket] = pos_counts.get(bucket, 0) + 1
            exposure[bucket] = exposure.get(bucket, 0) + pos.size * (pos.current_price or pos.avg_cost or 0)

        total_realized = sum(pnl_map.values())
        total_exposure = sum(exposure.values())

        self._upgrade_baseline = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "deploy_time_unix": time.time(),
            # Absolute values at deploy — used as starting point for incremental calc
            "abs_total_realized": round(total_realized, 2),
            "abs_crypto_realized": round(pnl_map.get("crypto", 0), 2),
            "abs_crypto_trades": trade_count_map.get("crypto", 0),
            "abs_total_trades": sum(trade_count_map.values()),
            # Snapshot values (for display)
            "crypto_exposure": round(exposure.get("crypto", 0), 2),
            "total_exposure": round(total_exposure, 2),
            "total_positions": sum(pos_counts.values()),
            "capital_utilization_pct": round(total_exposure / max(state.risk_config.max_market_exposure, 1) * 100, 1),
            # Pre-upgrade rates from the live snapshot (user-provided context)
            # These are the "before" rates that the system was achieving
            "pre_upgrade_pnl_per_h": 161.0,       # $1161.69 / 7.2h from audit
            "pre_upgrade_crypto_pnl_per_h": 160.0, # $1161.69 / 7.2h (99.6% from crypto)
            "pre_upgrade_trades_per_h": 1721.0,     # 12425 / 7.2h
            "pre_upgrade_exec_rate": 0.94,          # from snapshot
            "pre_upgrade_cap_util_pct": 41.6,       # from snapshot
        }
        logger.info(f"[UPGRADE-TRACK] Baseline captured (abs PnL=${total_realized:.2f}, {sum(trade_count_map.values())} trades)")
        return self._upgrade_baseline

    def send_upgrade_deployed(self, changes: list):
        """Send 'UPGRADE DEPLOYED' Telegram alert with baseline metrics."""
        if not self.enabled:
            return
        bl = getattr(self, "_upgrade_baseline", None)
        if not bl:
            return

        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
        lines = [
            f"<b>UPGRADE DEPLOYED</b> {ts}",
            "",
            "<b>Changes Applied:</b>",
        ]
        for c in changes:
            lines.append(f"  {c}")

        lines += [
            "",
            "<b>PRE-UPGRADE BASELINE:</b>",
            f"  Total PnL/hour: ${bl['pre_upgrade_pnl_per_h']:.0f}/h",
            f"  Crypto PnL/hour: ${bl['pre_upgrade_crypto_pnl_per_h']:.0f}/h",
            f"  Crypto trades/hour: {bl['pre_upgrade_trades_per_h']:.0f}",
            f"  Crypto exec rate: {bl['pre_upgrade_exec_rate']:.2f}%",
            f"  Capital utilization: {bl['pre_upgrade_cap_util_pct']:.0f}%",
            "",
            "Tracking updates every 2h. Final report at +6h.",
        ]
        self._fire("\n".join(lines))
        logger.info("[UPGRADE-TRACK] Deployment notification sent")

    async def _upgrade_tracking_loop(self):
        """Background loop: send performance updates every 2h, final report at 6h."""
        if not self.enabled or not self._state:
            return

        bl = getattr(self, "_upgrade_baseline", None)
        if not bl:
            return

        deploy_time = datetime.now(timezone.utc)
        update_interval_s = 2 * 3600  # 2 hours
        final_report_s = 6 * 3600     # 6 hours
        update_count = 0

        while True:
            try:
                await asyncio.sleep(update_interval_s)
                update_count += 1
                elapsed_s = (datetime.now(timezone.utc) - deploy_time).total_seconds()
                elapsed_h = elapsed_s / 3600

                current = self._compute_current_metrics(deploy_time)
                if not current:
                    continue

                is_final = elapsed_s >= final_report_s

                msg = self._build_comparison_msg(bl, current, elapsed_h, is_final)
                self._fire(msg)
                logger.info(f"[UPGRADE-TRACK] Update #{update_count} sent (elapsed={elapsed_h:.1f}h, final={is_final})")

                if is_final:
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[UPGRADE-TRACK] Error: {e}")

    def _compute_current_metrics(self, deploy_time):
        """Compute current metrics using rolling trade-timestamp windows."""
        if not self._state:
            return None

        from services.rolling_pnl import compute_rolling_pnl
        from engine.risk import classify_strategy

        bl = getattr(self, "_upgrade_baseline", None)
        if not bl:
            return None

        state = self._state
        elapsed_s = time.time() - bl["deploy_time_unix"]
        elapsed_h = max(elapsed_s / 3600, 0.01)

        # Rolling PnL windows (trade-timestamp based)
        rolling = compute_rolling_pnl(state.trades)

        # Current exposure
        exposure = {"crypto": 0.0, "weather": 0.0, "arb": 0.0}
        pos_counts = {"crypto": 0, "weather": 0, "arb": 0}
        for pos in state.positions.values():
            bucket = classify_strategy(pos)
            pos_counts[bucket] = pos_counts.get(bucket, 0) + 1
            exposure[bucket] = exposure.get(bucket, 0) + pos.size * (pos.current_price or pos.avg_cost or 0)

        total_exposure = sum(exposure.values())

        # Crypto scan health (exec rate)
        crypto_ref = self._strategy_refs.get("crypto")
        crypto_exec_rate = 0
        if crypto_ref:
            m = crypto_ref._m
            exec_count = m.get("signals_executed", 0)
            rej_count = m.get("signals_rejected", 0)
            total = exec_count + rej_count
            crypto_exec_rate = exec_count / max(total, 1) * 100

        return {
            "elapsed_h": round(elapsed_h, 2),
            "rolling": rolling,
            "crypto_exec_rate": round(crypto_exec_rate, 2),
            "crypto_exposure": round(exposure.get("crypto", 0), 2),
            "total_exposure": round(total_exposure, 2),
            "total_positions": sum(pos_counts.values()),
            "capital_utilization_pct": round(total_exposure / max(self._state.risk_config.max_market_exposure, 1) * 100, 1),
            "idle_capital_pct": round(100 - total_exposure / max(self._state.risk_config.max_market_exposure, 1) * 100, 1),
        }

    def _build_comparison_msg(self, baseline, current, elapsed_h, is_final):
        """Build comparison message using rolling-window PnL (no uptime-based metrics)."""
        from services.rolling_pnl import format_rolling_pnl_text

        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
        header = "UPGRADE IMPACT REPORT (FINAL)" if is_final else "SYSTEM PERFORMANCE UPDATE"

        rolling = current.get("rolling", {})

        lines = [
            f"<b>{header}</b> {ts}",
            f"Time since upgrade: {elapsed_h:.1f}h",
            "",
            "<b>=== PERFORMANCE SNAPSHOT ===</b>",
            "",
            format_rolling_pnl_text(rolling),
            "",
            "<b>SYSTEM STATUS:</b>",
            f"  Crypto exposure: ${current['crypto_exposure']:.0f}",
            f"  Capital utilization: {current['capital_utilization_pct']:.0f}%",
            f"  Idle capital: {current['idle_capital_pct']:.0f}%",
            f"  Crypto exec rate: {current['crypto_exec_rate']:.2f}%",
        ]

        # Warnings
        warnings = []
        crypto_1h = rolling.get("crypto", {}).get("1h", {})
        if crypto_1h.get("trades_per_h", 0) > 5000:
            warnings.append("OVERTRADING: Crypto >5000 trades/h")
        if crypto_1h.get("pnl_per_h", 0) < -50 and elapsed_h > 1:
            warnings.append(f"DRAWDOWN: Crypto -${abs(crypto_1h['pnl_per_h']):.2f}/h in last hour")
        if current["capital_utilization_pct"] > 95:
            warnings.append("EXPOSURE: Capital util >95%")

        if warnings:
            lines.append("")
            lines.append("<b>WARNINGS:</b>")
            for w in warnings:
                lines.append(f"  {w}")
        else:
            lines.append("")
            lines.append("No warnings. System healthy.")

        if is_final:
            lines.append("")
            total_6h = rolling.get("total", {}).get("6h", {})
            pnl_6h = total_6h.get("pnl_per_h", 0)
            lines.append("<b>VERDICT:</b>")
            lines.append(f"  6h average PnL/hour: ${pnl_6h:.2f}/h")
            lines.append(f"  6h total PnL: ${total_6h.get('pnl', 0):.2f}")
            lines.append(f"  6h total trades: {total_6h.get('trades', 0)}")

        return "\n".join(lines)

    def start_upgrade_tracking(self):
        """Start the upgrade tracking background loop."""
        self._upgrade_tracking_task = asyncio.create_task(self._upgrade_tracking_loop())
        logger.info("[UPGRADE-TRACK] Periodic tracking started (updates every 2h, final at 6h)")

