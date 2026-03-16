"""Telegram notification service for Polymarket Edge OS.

Only sends alerts when a trade/position is CLOSED or RESOLVED with
realized PnL. All other events are silently ignored.
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

        from models import EventType
        bus.on(EventType.ORDER_UPDATE, self._on_order_update)
        bus.on(EventType.SYSTEM_EVENT, self._on_system_event)

        status = "enabled" if self.configured else "disabled (no credentials)"
        logger.info(f"Telegram notifier started [{status}] — close-only alerts")

    async def stop(self):
        if self._bus:
            from models import EventType
            self._bus.off(EventType.ORDER_UPDATE, self._on_order_update)
            self._bus.off(EventType.SYSTEM_EVENT, self._on_system_event)
        if self._client:
            await self._client.aclose()
        logger.info("Telegram notifier stopped")

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
            logger.warning("Telegram rate limit hit, dropping message")
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
                logger.warning(f"Telegram API error {resp.status_code}: {resp.text[:200]}")
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
        """Only react to 'closed' status — ignore filled/submitted/etc."""
        if not self.enabled:
            return
        if event.data.get("status") == "closed":
            self._send_trade_closed(event.data)

    async def _on_system_event(self, event):
        """Handle resolver-generated closes."""
        if not self.enabled:
            return
        if event.source == "market_resolver" and event.data.get("action") == "positions_resolved":
            count = event.data.get("count", 0)
            pnl = event.data.get("pnl", 0)
            if count > 0:
                self._send_resolver_summary(count, pnl)

    def _send_trade_closed(self, data: dict):
        order_id = data.get("order_id", "?")
        trade = self._find_trade(order_id)

        strategy = (data.get("strategy_id") or "unknown").replace("_", " ").upper()
        market = (data.get("market_question") or order_id[:16])[:60]
        side = data.get("side", "?")
        outcome = data.get("outcome", side)
        entry_price = data.get("entry_price", 0)
        exit_price = data.get("exit_price", data.get("fill_price", 0))
        pnl = data.get("pnl", 0)
        size = data.get("size", 1)

        if trade:
            strategy = trade.strategy_id.replace("_", " ").upper()
            market = (trade.market_question or order_id[:16])[:60]
            outcome = trade.outcome or trade.side.value
            if not entry_price:
                entry_price = trade.price
            if not exit_price:
                exit_price = trade.price
            pnl = trade.pnl if trade.pnl else pnl
            size = trade.size

        cost = entry_price * size if entry_price and size else 0
        roi = (pnl / cost * 100) if cost > 0 else 0
        pnl_sign = "+" if pnl >= 0 else ""
        roi_sign = "+" if roi >= 0 else ""
        emoji = "+" if pnl >= 0 else "-"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        text = (
            f"<b>TRADE CLOSED {emoji}</b>\n"
            f"Strategy: {strategy}\n"
            f"Market: {market}\n"
            f"Side: {outcome}\n"
            f"Entry: {entry_price:.4f}\n"
            f"Exit: {exit_price:.4f}\n"
            f"PnL: <b>{pnl_sign}${pnl:.2f}</b>\n"
            f"ROI: {roi_sign}{roi:.1f}%\n"
            f"Time: {ts}"
        )
        self._fire(text)

    def _send_resolver_summary(self, count: int, pnl: float):
        pnl_sign = "+" if pnl >= 0 else ""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Also send individual resolution details from recent trades
        resolver_trades = []
        if self._state:
            for t in reversed(self._state.trades):
                if t.strategy_id == "resolver":
                    resolver_trades.append(t)
                    if len(resolver_trades) >= count:
                        break

        if resolver_trades:
            for t in resolver_trades:
                cost = t.price * t.size if t.price else 0
                roi = (t.pnl / cost * 100) if cost > 0 and t.pnl else 0
                pnl_s = "+" if (t.pnl or 0) >= 0 else ""
                roi_s = "+" if roi >= 0 else ""
                won = "WON" if (t.pnl or 0) >= 0 else "LOST"
                text = (
                    f"<b>MARKET RESOLVED — {won}</b>\n"
                    f"Market: {(t.market_question or '?')[:60]}\n"
                    f"Outcome: {t.outcome or '?'}\n"
                    f"Settlement: {t.price:.4f}\n"
                    f"PnL: <b>{pnl_s}${t.pnl:.2f}</b>\n"
                    f"ROI: {roi_s}{roi:.1f}%\n"
                    f"Time: {ts}"
                )
                self._fire(text)
        else:
            text = (
                f"<b>POSITIONS RESOLVED</b>\n"
                f"Count: {count}\n"
                f"PnL: <b>{pnl_sign}${pnl:.2f}</b>\n"
                f"Time: {ts}"
            )
            self._fire(text)

    def _find_trade(self, order_id):
        if self._state:
            for t in reversed(self._state.trades):
                if t.order_id == order_id:
                    return t
        return None
