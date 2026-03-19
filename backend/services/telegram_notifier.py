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
        """Build and send a structured system performance digest."""
        if not self.enabled or not self._state:
            return

        from engine.risk import classify_strategy

        state = self._state
        cfg = state.risk_config

        # PnL by strategy
        pnl_map = {}
        trade_count_map = {}
        for t in state.trades:
            sid = t.strategy_id or "unknown"
            bucket = "crypto" if "crypto" in sid or "sniper" in sid else \
                     "weather" if "weather" in sid else \
                     "arb" if "arb" in sid else "other"
            pnl_map[bucket] = pnl_map.get(bucket, 0) + t.pnl
            trade_count_map[bucket] = trade_count_map.get(bucket, 0) + 1

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

        total_realized = sum(pnl_map.values())
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
            "<b>By Strategy:</b>",
            f"  CRYPTO: ${pnl_map.get('crypto',0):+.2f} | {pos_counts.get('crypto',0)} pos | ${exposure.get('crypto',0):.0f} exp",
            f"  WEATHER: ${pnl_map.get('weather',0):+.2f} | {pos_counts.get('weather',0)} pos | ${exposure.get('weather',0):.0f} exp",
            f"  ARB: ${pnl_map.get('arb',0):+.2f} | {pos_counts.get('arb',0)} pos | ${exposure.get('arb',0):.0f} exp",
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
