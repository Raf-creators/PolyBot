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
        self._hourly_streak_task = None
        self._bihourlly_report_task = None

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
        self._12h_analysis_task = None

        from models import EventType
        bus.on(EventType.ORDER_UPDATE, self._on_order_update)
        bus.on(EventType.SYSTEM_EVENT, self._on_system_event)

        # Start periodic digest (every 3 hours)
        self._digest_task = asyncio.create_task(self._periodic_digest_loop())

        # Start new monitoring loops (from forensic rollback)
        self._bihourlly_report_task = asyncio.create_task(self._bihourly_performance_loop())
        self._hourly_streak_task = asyncio.create_task(self._hourly_streak_loop())

        # Start 12-hour deep analysis loop
        self._12h_analysis_task = asyncio.create_task(self._12h_analysis_loop())

        status = "enabled" if self.configured else "disabled (no credentials)"
        logger.info(f"Telegram notifier started [{status}]")

    async def stop(self):
        for task_attr in ['_digest_task', '_upgrade_tracking_task', '_bihourlly_report_task', '_hourly_streak_task', '_12h_analysis_task']:
            task = getattr(self, task_attr, None)
            if task:
                task.cancel()
                try:
                    await task
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
                body = resp.text[:200] if hasattr(resp, 'text') else ''
                logger.warning(f"Telegram API {resp.status_code}: {body}")
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
            # Pre-upgrade rates from FORENSIC ANALYSIS (best period M2→D):
            # M2→D window: 8.77h, $493.57 earned, 2233 trades
            "pre_upgrade_pnl_per_h": 56.28,         # M2→D: $493.57 / 8.77h
            "pre_upgrade_crypto_pnl_per_h": 56.28,  # 99.6% from crypto
            "pre_upgrade_trades_per_h": 255.0,       # M2→D: 2233 / 8.77h
            "pre_upgrade_exec_rate": 4.8,             # from D snapshot
            "pre_upgrade_cap_util_pct": 41.6,         # from D snapshot
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

    # ---- BIHOURLY FULL PERFORMANCE REPORT (every 2h) ----

    async def _bihourly_performance_loop(self):
        """Send a comprehensive performance update every 2 hours."""
        await asyncio.sleep(600)  # wait 10 min after startup for initial data
        while True:
            try:
                await self._send_bihourly_report()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[TELEGRAM] Bihourly report error: {e}")
            await asyncio.sleep(2 * 3600)  # 2 hours

    async def _send_bihourly_report(self):
        """Build and send the full 2-hour performance report."""
        if not self.enabled or not self._state:
            return

        from engine.risk import classify_strategy
        from services.rolling_pnl import compute_rolling_pnl

        state = self._state
        cfg = state.risk_config
        rolling = compute_rolling_pnl(state.trades)
        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")

        # Position counts, exposure, unrealized by strategy
        pos_counts = {"crypto": 0, "weather": 0, "arb": 0}
        exposure = {"crypto": 0.0, "weather": 0.0, "arb": 0.0}
        unrealized = {"crypto": 0.0, "weather": 0.0, "arb": 0.0}
        for pos in state.positions.values():
            bucket = classify_strategy(pos)
            pos_counts[bucket] = pos_counts.get(bucket, 0) + 1
            exp = pos.size * (pos.current_price or pos.avg_cost or 0)
            exposure[bucket] = exposure.get(bucket, 0) + exp
            unrealized[bucket] = unrealized.get(bucket, 0) + (pos.current_price - pos.avg_cost) * pos.size

        total_exposure = sum(exposure.values())
        total_realized = sum(t.pnl for t in state.trades if t.pnl)
        total_unrealized = sum(unrealized.values())

        # Crypto scan health
        crypto_ref = self._strategy_refs.get("crypto")
        crypto_health = {}
        if crypto_ref:
            crypto_health = crypto_ref._m
        exec_count = crypto_health.get("signals_executed", 0)
        rej_count = crypto_health.get("signals_rejected", 0)
        total_signals = exec_count + rej_count
        crypto_exec_rate = exec_count / max(total_signals, 1) * 100

        # Crypto rejection breakdown (top 4)
        rej_reasons = crypto_health.get("rejection_reasons", {})
        top_rejections = sorted(rej_reasons.items(), key=lambda x: x[1], reverse=True)[:4]

        # Weather scan health
        weather_ref = self._strategy_refs.get("weather")
        weather_health = {}
        if weather_ref:
            weather_health = weather_ref._m
        w_sig_exec = weather_health.get("signals_executed", 0)
        w_sig_gen = weather_health.get("signals_generated", 0)
        w_exec_rate = w_sig_exec / max(w_sig_gen, 1) * 100
        w_exit_cands = weather_health.get("lifecycle", {}).get("exit_candidates", 0)

        # Arb scan health
        arb_ref = self._strategy_refs.get("arb")
        arb_health = {}
        if arb_ref:
            arb_health = arb_ref.get_health()
        arb_new_signals = arb_health.get("signals_generated", 0)

        # Crypto position sizes
        crypto_sizes = []
        for pos in state.positions.values():
            if classify_strategy(pos) == "crypto":
                crypto_sizes.append(pos.size)
        avg_crypto_size = sum(crypto_sizes) / len(crypto_sizes) if crypto_sizes else 0
        max_crypto_size = max(crypto_sizes) if crypto_sizes else 0

        # Rolling PnL extraction
        def rpnl(bucket, window):
            return rolling.get(bucket, {}).get(window, {}).get("pnl_per_h", 0)
        def rtrades(bucket, window):
            return rolling.get(bucket, {}).get(window, {}).get("trades_per_h", 0)

        lines = [
            f"<b>FULL PERFORMANCE REPORT</b> {ts}",
            "",
            "<b>CRYPTO:</b>",
            f"  PnL/h: 1h=${rpnl('crypto','1h'):.2f} | 3h=${rpnl('crypto','3h'):.2f} | 6h=${rpnl('crypto','6h'):.2f}",
            f"  Trades/h: {rtrades('crypto','1h'):.0f}",
            f"  Exec rate: {crypto_exec_rate:.1f}%",
            f"  Avg pos size: {avg_crypto_size:.1f} | Max: {max_crypto_size:.0f}",
            f"  Exposure: ${exposure.get('crypto',0):.0f} / ${cfg.crypto_max_exposure:.0f}",
            f"  Unrealized: ${unrealized.get('crypto',0):+.2f}",
            "  Top rejections:",
        ]
        for reason, count in top_rejections:
            lines.append(f"    {reason}: {count}")

        lines += [
            "",
            "<b>ARB:</b>",
            f"  Capital: ${exposure.get('arb',0):.0f} | Slots: {pos_counts.get('arb',0)}/{cfg.max_arb_positions}",
            f"  New signals: {arb_new_signals}",
            f"  Realized: ${sum(t.pnl for t in state.trades if t.pnl and ('arb' in (t.strategy_id or ''))):+.2f}",
            f"  Unrealized: ${unrealized.get('arb',0):+.2f}",
            "",
            "<b>WEATHER:</b>",
            f"  Capital: ${exposure.get('weather',0):.2f} | Pos: {pos_counts.get('weather',0)}",
            f"  Signals exec: {w_sig_exec} ({w_exec_rate:.1f}%)",
            f"  Realized: ${sum(t.pnl for t in state.trades if t.pnl and ('weather' in (t.strategy_id or ''))):+.2f}",
            f"  Unrealized: ${unrealized.get('weather',0):+.2f}",
            f"  Avg pos size: {sum(pos.size for pos in state.positions.values() if classify_strategy(pos)=='weather') / max(pos_counts.get('weather',1),1):.1f}",
            f"  Exit candidates: {w_exit_cands}",
            "",
            "<b>SYSTEM:</b>",
            f"  Allocation: Crypto ${exposure.get('crypto',0):.0f} | Arb ${exposure.get('arb',0):.0f} | Weather ${exposure.get('weather',0):.0f}",
            f"  Total PnL/h: 1h=${rpnl('total','1h'):.2f} | 3h=${rpnl('total','3h'):.2f} | 6h=${rpnl('total','6h'):.2f}",
            f"  Total: R=${total_realized:+.2f} / U=${total_unrealized:+.2f}",
            f"  Idle: {100 - total_exposure / max(cfg.max_market_exposure,1) * 100:.0f}%",
        ]

        # Comparison vs forensic baseline
        bl = getattr(self, "_upgrade_baseline", None)
        if bl:
            pre_pnl_h = bl.get("pre_upgrade_pnl_per_h", 56.28)
            pre_trades_h = bl.get("pre_upgrade_trades_per_h", 255)
            pre_exec_rate = bl.get("pre_upgrade_exec_rate", 4.8)

            lines += [
                "",
                "<b>vs PRE-CHANGE BASELINE (M2→D):</b>",
                f"  Crypto PnL/h: ${rpnl('crypto','3h'):.2f} vs ${pre_pnl_h:.2f} (target)",
                f"  Trades/h: {rtrades('crypto','1h'):.0f} vs {pre_trades_h:.0f}",
                f"  Exec rate: {crypto_exec_rate:.1f}% vs {pre_exec_rate:.1f}%",
                f"  Weather exec: {w_sig_exec} vs baseline N/A",
            ]

        self._fire("\n".join(lines))
        logger.info("[TELEGRAM] Bihourly performance report sent")

    # ---- HOURLY WIN/STREAK REPORT ----

    async def _hourly_streak_loop(self):
        """Send a concise hourly win/streak update."""
        await asyncio.sleep(900)  # wait 15 min after startup
        while True:
            try:
                await self._send_hourly_streak()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[TELEGRAM] Hourly streak error: {e}")
            await asyncio.sleep(3600)  # 1 hour

    async def _send_hourly_streak(self):
        """Build and send the hourly win/streak report using closed-trade data only."""
        if not self.enabled or not self._state:
            return

        state = self._state
        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
        now = datetime.now(timezone.utc)

        # Get trades from the last hour
        one_hour_ago = now.timestamp() - 3600
        recent_trades = []
        for t in reversed(state.trades):
            trade_ts = None
            if hasattr(t, 'closed_at') and t.closed_at:
                try:
                    trade_ts = datetime.fromisoformat(str(t.closed_at).replace('Z', '+00:00')).timestamp()
                except (ValueError, TypeError):
                    pass
            if trade_ts is None and hasattr(t, 'timestamp') and t.timestamp:
                try:
                    trade_ts = datetime.fromisoformat(str(t.timestamp).replace('Z', '+00:00')).timestamp()
                except (ValueError, TypeError):
                    pass
            if trade_ts is None:
                continue
            if trade_ts < one_hour_ago:
                break
            if t.pnl is not None:
                recent_trades.append(t)

        if not recent_trades:
            return  # No trades in last hour, skip

        # 1. Biggest profit win
        wins = [t for t in recent_trades if t.pnl > 0]
        biggest_win = max(wins, key=lambda t: t.pnl) if wins else None

        # 2. Biggest loss
        losses = [t for t in recent_trades if t.pnl < 0]
        biggest_loss = min(losses, key=lambda t: t.pnl) if losses else None

        # 3. Streaks: compute from recent trades (chronological order)
        sorted_trades = list(reversed(recent_trades))
        best_win_streak = 0
        best_win_streak_pnl = 0.0
        current_streak = 0
        current_streak_pnl = 0.0

        for t in sorted_trades:
            if t.pnl > 0:
                current_streak += 1
                current_streak_pnl += t.pnl
                if current_streak > best_win_streak:
                    best_win_streak = current_streak
                    best_win_streak_pnl = current_streak_pnl
            else:
                current_streak = 0
                current_streak_pnl = 0.0

        # 4. Current active streak (from most recent trades)
        active_streak = 0
        active_streak_pnl = 0.0
        for t in reversed(sorted_trades):
            if t.pnl > 0:
                active_streak += 1
                active_streak_pnl += t.pnl
            else:
                break

        # Current losing streak
        losing_streak = 0
        losing_streak_pnl = 0.0
        for t in reversed(sorted_trades):
            if t.pnl < 0:
                losing_streak += 1
                losing_streak_pnl += t.pnl
            else:
                break

        # Build message
        label_map = {"crypto_sniper": "CRYPTO", "weather_trader": "WEATHER", "arb_scanner": "ARB", "resolver": "RESOLVER"}

        lines = [
            f"<b>HOURLY WIN/STREAK UPDATE</b> {ts}",
            f"Trades in last hour: {len(recent_trades)} ({len(wins)}W / {len(losses)}L)",
            "",
        ]

        if biggest_win:
            sid = label_map.get(biggest_win.strategy_id or "", "UNKNOWN")
            market = (biggest_win.market_question or "?")[:60]
            lines += [
                "<b>BIGGEST WIN:</b>",
                f"  [{sid}] ${biggest_win.pnl:+.2f}",
                f"  {market}",
                f"  Size: {biggest_win.size}",
                "",
            ]

        if best_win_streak > 1:
            lines += [
                f"<b>BEST WIN STREAK:</b> {best_win_streak} wins, ${best_win_streak_pnl:+.2f}",
                "",
            ]

        if active_streak > 1:
            lines += [
                f"<b>ACTIVE WIN STREAK:</b> {active_streak} wins, ${active_streak_pnl:+.2f}",
                "",
            ]

        # Warning flags
        if biggest_loss and biggest_loss.pnl < -1.0:
            sid = label_map.get(biggest_loss.strategy_id or "", "UNKNOWN")
            market = (biggest_loss.market_question or "?")[:60]
            lines += [
                "<b>BIGGEST LOSS:</b>",
                f"  [{sid}] ${biggest_loss.pnl:+.2f}",
                f"  {market}",
                "",
            ]

        if losing_streak >= 3:
            lines.append(f"<b>LOSING STREAK:</b> {losing_streak} trades, ${losing_streak_pnl:+.2f}")

        self._fire("\n".join(lines))
        logger.info("[TELEGRAM] Hourly streak report sent")

    # ---- 12-HOUR DEEP ANALYSIS ----

    async def _12h_analysis_loop(self):
        """Send comprehensive trade analysis every 12 hours with learnings and suggestions."""
        await asyncio.sleep(1800)  # wait 30 min for meaningful data
        while True:
            try:
                await self._send_12h_analysis()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[TELEGRAM] 12h analysis error: {e}")
            await asyncio.sleep(12 * 3600)  # 12 hours

    async def _send_12h_analysis(self):
        """Build deep 12-hour analysis with learnings, patterns, and relay-ready suggestions."""
        if not self.enabled or not self._state:
            return

        from engine.risk import classify_strategy

        state = self._state
        now = datetime.now(timezone.utc)
        ts = now.strftime("%H:%M UTC %b %d")
        cutoff = now.timestamp() - (12 * 3600)

        # Gather trades from last 12 hours
        all_trades = []
        for t in reversed(state.trades):
            trade_ts = self._extract_timestamp(t)
            if trade_ts is None:
                continue
            if trade_ts < cutoff:
                break
            if t.pnl is not None:
                all_trades.append(t)
        all_trades.reverse()

        if not all_trades:
            self._fire(f"<b>12H ANALYSIS</b> {ts}\n\nNo closed trades in the last 12 hours.")
            return

        # ---- Classify trades ----
        crypto_trades = [t for t in all_trades if 'sniper' in (t.strategy_id or '') or 'crypto' in (t.strategy_id or '')]
        arb_trades = [t for t in all_trades if 'arb' in (t.strategy_id or '')]
        weather_trades = [t for t in all_trades if 'weather' in (t.strategy_id or '')]

        # ---- CRYPTO DEEP DIVE ----
        crypto_wins = [t for t in crypto_trades if t.pnl > 0]
        crypto_losses = [t for t in crypto_trades if t.pnl <= 0]
        total_crypto_pnl = sum(t.pnl for t in crypto_trades)

        # By asset (BTC vs ETH)
        btc_trades = [t for t in crypto_trades if 'btc' in (t.market_question or '').lower() or 'bitcoin' in (t.market_question or '').lower()]
        eth_trades = [t for t in crypto_trades if 'eth' in (t.market_question or '').lower() or 'ethereum' in (t.market_question or '').lower()]

        btc_pnl = sum(t.pnl for t in btc_trades)
        eth_pnl = sum(t.pnl for t in eth_trades)
        btc_wr = len([t for t in btc_trades if t.pnl > 0]) / max(len(btc_trades), 1) * 100
        eth_wr = len([t for t in eth_trades if t.pnl > 0]) / max(len(eth_trades), 1) * 100

        # By size tier
        size_buckets = {"$5 (low)": [], "$12 (med)": [], "$18 (high)": [], "$25 (max)": []}
        for t in crypto_trades:
            s = t.size
            if s <= 6:
                size_buckets["$5 (low)"].append(t)
            elif s <= 14:
                size_buckets["$12 (med)"].append(t)
            elif s <= 20:
                size_buckets["$18 (high)"].append(t)
            else:
                size_buckets["$25 (max)"].append(t)

        # By window duration (extract from question text)
        window_buckets = {"5m": [], "15m": [], "1h": [], "4h+": []}
        for t in crypto_trades:
            q = (t.market_question or "").lower()
            w = self._detect_window_from_question(q)
            window_buckets.setdefault(w, []).append(t)

        # Biggest individual wins and losses
        top_wins = sorted(crypto_wins, key=lambda t: t.pnl, reverse=True)[:3]
        top_losses = sorted(crypto_losses, key=lambda t: t.pnl)[:3]

        # ---- COMPUTE INSIGHTS ----
        insights = []
        suggestions = []

        # 1. Asset comparison
        if btc_trades and eth_trades:
            btc_avg = btc_pnl / len(btc_trades) if btc_trades else 0
            eth_avg = eth_pnl / len(eth_trades) if eth_trades else 0
            if abs(btc_avg - eth_avg) > 0.5:
                better = "BTC" if btc_avg > eth_avg else "ETH"
                worse = "ETH" if better == "BTC" else "BTC"
                insights.append(f"{better} outperforming {worse} ({better} avg ${btc_avg if better=='BTC' else eth_avg:+.2f}/trade vs {worse} ${eth_avg if better=='BTC' else btc_avg:+.2f})")
                if (btc_avg if worse == "BTC" else eth_avg) < -0.5:
                    suggestions.append(f"Consider reducing {worse} exposure or tightening {worse} min_edge_bps")

        # 2. Window analysis
        best_window = None
        worst_window = None
        best_wr = -1
        worst_wr = 101
        for wkey, wtrades in window_buckets.items():
            if len(wtrades) < 3:
                continue
            wr = len([t for t in wtrades if t.pnl > 0]) / len(wtrades) * 100
            wpnl = sum(t.pnl for t in wtrades)
            if wr > best_wr:
                best_wr = wr
                best_window = (wkey, wr, wpnl, len(wtrades))
            if wr < worst_wr:
                worst_wr = wr
                worst_window = (wkey, wr, wpnl, len(wtrades))

        if best_window:
            insights.append(f"Best window: {best_window[0]} ({best_window[1]:.0f}% WR, ${best_window[2]:+.2f}, {best_window[3]} trades)")
        if worst_window and worst_window[0] != (best_window[0] if best_window else ""):
            insights.append(f"Worst window: {worst_window[0]} ({worst_window[1]:.0f}% WR, ${worst_window[2]:+.2f}, {worst_window[3]} trades)")
            if worst_window[1] < 35 and worst_window[3] > 5:
                suggestions.append(f"Window {worst_window[0]} has {worst_window[1]:.0f}% WR over {worst_window[3]} trades — consider disabling or raising min_edge for this window")

        # 3. Size tier analysis
        for skey, strades in size_buckets.items():
            if len(strades) < 3:
                continue
            spnl = sum(t.pnl for t in strades)
            swr = len([t for t in strades if t.pnl > 0]) / len(strades) * 100
            if spnl < -5 and swr < 40:
                insights.append(f"Sizing tier {skey}: negative (${spnl:+.2f}, {swr:.0f}% WR, {len(strades)} trades)")
                suggestions.append(f"Size tier {skey} is bleeding — the edge estimates at this level may be unreliable")

        # 4. Overall win rate trend
        if len(crypto_trades) >= 10:
            first_half = crypto_trades[:len(crypto_trades)//2]
            second_half = crypto_trades[len(crypto_trades)//2:]
            wr1 = len([t for t in first_half if t.pnl > 0]) / len(first_half) * 100
            wr2 = len([t for t in second_half if t.pnl > 0]) / len(second_half) * 100
            if wr2 > wr1 + 10:
                insights.append(f"Win rate IMPROVING: {wr1:.0f}% -> {wr2:.0f}% (first vs second half)")
            elif wr1 > wr2 + 10:
                insights.append(f"Win rate DECLINING: {wr1:.0f}% -> {wr2:.0f}% (first vs second half)")
                suggestions.append("Win rate declining — market regime may have shifted, consider reducing position sizes temporarily")

        # 5. Big loss patterns
        if top_losses:
            big_loss_windows = [self._detect_window_from_question((t.market_question or '').lower()) for t in top_losses]
            big_loss_assets = ['BTC' if 'btc' in (t.market_question or '').lower() or 'bitcoin' in (t.market_question or '').lower() else 'ETH' for t in top_losses]
            from collections import Counter
            common_window = Counter(big_loss_windows).most_common(1)
            common_asset = Counter(big_loss_assets).most_common(1)
            if common_window and common_window[0][1] >= 2:
                insights.append(f"Biggest losses cluster in {common_window[0][0]} windows")
            if common_asset and common_asset[0][1] >= 2:
                insights.append(f"Biggest losses cluster in {common_asset[0][0]}")

        # 6. Capital efficiency
        total_deployed = sum(abs(t.size * (t.price or 0)) for t in crypto_trades)
        if total_deployed > 0:
            roi_pct = total_crypto_pnl / total_deployed * 100
            insights.append(f"Capital efficiency: {roi_pct:+.2f}% return on ${total_deployed:.0f} deployed")

        # 7. Profit factor
        gross_wins = sum(t.pnl for t in crypto_wins) if crypto_wins else 0
        gross_losses = abs(sum(t.pnl for t in crypto_losses)) if crypto_losses else 0
        pf = gross_wins / max(gross_losses, 0.01)
        insights.append(f"Profit factor: {pf:.2f}x ({'>1 is profitable' if pf > 1 else 'LOSING — below 1.0'})")

        if not suggestions:
            if pf > 1.5:
                suggestions.append("Strong performance — consider incrementally increasing position sizes or deploying more capital")
            elif pf > 1.0:
                suggestions.append("Marginal edge — maintain current sizing, collect more data before changes")
            else:
                suggestions.append("Negative edge detected — review model calibration, check if vol estimates are stale")

        # ---- SHADOW COMPARISON ----
        shadow_lines = []
        crypto_ref = self._strategy_refs.get("crypto")
        if crypto_ref:
            dislocation = crypto_ref._m.get("dislocation_filtered", 0)
            pos_capped = crypto_ref._m.get("position_capped", 0)
            shadow_lines = [
                f"  Dislocation filter: {dislocation} blocked",
                f"  Position cap: {pos_capped} blocked",
            ]

        # ---- BUILD MESSAGE (split into 2 messages for Telegram 4096 limit) ----
        crypto_wr = len(crypto_wins) / max(len(crypto_trades), 1) * 100
        avg_win = sum(t.pnl for t in crypto_wins) / max(len(crypto_wins), 1) if crypto_wins else 0
        avg_loss = sum(t.pnl for t in crypto_losses) / max(len(crypto_losses), 1) if crypto_losses else 0

        msg1_lines = [
            f"<b>12H DEEP ANALYSIS</b> {ts}",
            "Period: last 12 hours | Epoch 4",
            "",
            "<b>=== CRYPTO SNIPER ===</b>",
            f"Trades: {len(crypto_trades)} ({len(crypto_wins)}W / {len(crypto_losses)}L)",
            f"Win Rate: {crypto_wr:.1f}%",
            f"Total PnL: <b>${total_crypto_pnl:+.2f}</b>",
            f"Avg Win: ${avg_win:+.2f} | Avg Loss: ${avg_loss:+.2f}",
            f"Profit Factor: {pf:.2f}x",
            "",
            "<b>By Asset:</b>",
            f"  BTC: {len(btc_trades)} trades, ${btc_pnl:+.2f}, {btc_wr:.0f}% WR",
            f"  ETH: {len(eth_trades)} trades, ${eth_pnl:+.2f}, {eth_wr:.0f}% WR",
            "",
            "<b>By Window:</b>",
        ]
        for wkey in ["5m", "15m", "1h", "4h+"]:
            wt = window_buckets.get(wkey, [])
            if wt:
                wpnl = sum(t.pnl for t in wt)
                wwr = len([t for t in wt if t.pnl > 0]) / len(wt) * 100
                msg1_lines.append(f"  {wkey}: {len(wt)} trades, ${wpnl:+.2f}, {wwr:.0f}% WR")

        msg1_lines += ["", "<b>By Size Tier:</b>"]
        for skey in ["$5 (low)", "$12 (med)", "$18 (high)", "$25 (max)"]:
            st = size_buckets.get(skey, [])
            if st:
                spnl = sum(t.pnl for t in st)
                swr = len([t for t in st if t.pnl > 0]) / len(st) * 100
                msg1_lines.append(f"  {skey}: {len(st)} trades, ${spnl:+.2f}, {swr:.0f}% WR")

        self._fire("\n".join(msg1_lines))

        # Second message: insights + suggestions
        msg2_lines = [
            "<b>12H ANALYSIS — INSIGHTS</b>",
            "",
        ]

        if top_wins:
            msg2_lines.append("<b>Top Wins:</b>")
            for t in top_wins[:3]:
                q = (t.market_question or '?')[:55]
                msg2_lines.append(f"  ${t.pnl:+.2f} | {q}")
            msg2_lines.append("")

        if top_losses:
            msg2_lines.append("<b>Top Losses:</b>")
            for t in top_losses[:3]:
                q = (t.market_question or '?')[:55]
                msg2_lines.append(f"  ${t.pnl:+.2f} | {q}")
            msg2_lines.append("")

        msg2_lines.append("<b>LEARNINGS:</b>")
        for i, insight in enumerate(insights[:8], 1):
            msg2_lines.append(f"  {i}. {insight}")

        msg2_lines += ["", "<b>SUGGESTIONS (relay to dev):</b>"]
        for i, sug in enumerate(suggestions[:5], 1):
            msg2_lines.append(f"  {i}. {sug}")

        if shadow_lines:
            msg2_lines += ["", "<b>FILTER STATS:</b>"] + shadow_lines

        # ARB + WEATHER summary
        if arb_trades:
            arb_pnl = sum(t.pnl for t in arb_trades)
            msg2_lines += ["", f"<b>ARB:</b> {len(arb_trades)} trades, ${arb_pnl:+.2f}"]
        if weather_trades:
            w_pnl = sum(t.pnl for t in weather_trades)
            msg2_lines += [f"<b>WEATHER:</b> {len(weather_trades)} trades, ${w_pnl:+.2f}"]

        # Balance snapshot
        balance = 1000.0  # Epoch 4 starting balance
        for t in state.trades:
            if t.pnl:
                balance += t.pnl
        msg2_lines += [
            "",
            f"<b>BALANCE:</b> ${balance:.2f}",
            "<b>NEXT ANALYSIS:</b> in 12 hours",
        ]

        self._fire("\n".join(msg2_lines))
        logger.info("[TELEGRAM] 12h deep analysis sent")

    def _detect_window_from_question(self, q: str) -> str:
        """Detect time window from market question text."""
        import re
        # Look for time range patterns like "7:00PM-7:05PM" (5m), "7:00PM-7:15PM" (15m), etc.
        time_pat = re.findall(r'(\d{1,2}):(\d{2})(am|pm)\s*-\s*(\d{1,2}):(\d{2})(am|pm)', q.replace(' ', ''))
        if not time_pat:
            time_pat = re.findall(r'(\d{1,2}):(\d{2})(am|pm)-(\d{1,2}):(\d{2})(am|pm)', q)
        if time_pat:
            m = time_pat[0]
            h1 = int(m[0]) % 12 + (12 if m[2] == 'pm' else 0)
            min1 = int(m[1])
            h2 = int(m[3]) % 12 + (12 if m[5] == 'pm' else 0)
            min2 = int(m[4])
            diff_min = (h2 * 60 + min2) - (h1 * 60 + min1)
            if diff_min < 0:
                diff_min += 24 * 60
            if diff_min <= 5:
                return "5m"
            elif diff_min <= 15:
                return "15m"
            elif diff_min <= 60:
                return "1h"
            else:
                return "4h+"
        return "4h+"

    def _extract_timestamp(self, trade) -> Optional[float]:
        """Extract unix timestamp from a trade object."""
        for attr in ('closed_at', 'timestamp', 'created_at'):
            val = getattr(trade, attr, None)
            if val:
                try:
                    return datetime.fromisoformat(str(val).replace('Z', '+00:00')).timestamp()
                except (ValueError, TypeError):
                    pass
        return None

