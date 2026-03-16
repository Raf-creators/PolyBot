"""Telegram notification service for Polymarket Edge OS.

Only sends two types of alerts:
  1. TRADE EXECUTED — when an order is filled
  2. TRADE CLOSED — when a position resolves with final PnL

All other events (signals, scanner activity, weather alerts, risk,
diagnostics) are logged locally but never sent to Telegram.

Design:
  - All sends are fire-and-forget via asyncio.create_task
  - Never blocks the EventBus dispatch loop
  - Rate-limited to avoid Telegram API throttling (max 20 msgs/min)
"""

import asyncio
import logging
import os
import time
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

        status = "enabled" if self.configured else "disabled (no credentials)"
        logger.info(f"Telegram notifier started [{status}]")

    async def stop(self):
        if self._bus:
            from models import EventType
            self._bus.off(EventType.ORDER_UPDATE, self._on_order_update)
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
            logger.debug("Telegram send skipped: no credentials")
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
        """Fire-and-forget async send."""
        asyncio.create_task(self.send_message(text))

    # ---- Event Handlers ----

    async def _on_order_update(self, event):
        if not self.enabled:
            return

        status = event.data.get("status")
        order_id = event.data.get("order_id", "?")

        if status == "filled":
            self._send_trade_executed(event, order_id)
        elif status == "closed":
            self._send_trade_closed(event, order_id)

    def _send_trade_executed(self, event, order_id):
        fill_price = event.data.get("fill_price", 0)
        edge_bps = event.data.get("edge_bps", 0)

        trade = self._find_trade(order_id)

        if trade:
            strategy = trade.strategy_id.replace("_", " ").upper()
            market = trade.market_question[:60] if trade.market_question else order_id[:12]
            side = trade.side.value.upper()
            size = trade.size
            # Try to get edge from event data first, then from trade
            edge = edge_bps or event.data.get("target_edge_bps", 0)
        else:
            strategy = event.data.get("strategy_id", "UNKNOWN").replace("_", " ").upper()
            market = event.data.get("market_question", order_id[:12])[:60]
            side = event.data.get("side", "?").upper()
            size = event.data.get("size", 0)
            edge = edge_bps

        text = (
            f"<b>TRADE EXECUTED</b>\n"
            f"Strategy: {strategy}\n"
            f"Market: {market}\n"
            f"Side: {side}\n"
            f"Price: {fill_price:.4f}\n"
            f"Size: {size}\n"
            f"Edge: {edge:.0f}bps"
        )
        self._fire(text)

    def _send_trade_closed(self, event, order_id):
        data = event.data
        pnl = data.get("pnl", 0)
        entry_price = data.get("entry_price", 0)
        roi = (pnl / (entry_price * data.get("size", 1)) * 100) if entry_price > 0 else 0

        trade = self._find_trade(order_id)

        if trade:
            strategy = trade.strategy_id.replace("_", " ").upper()
            market = trade.market_question[:60] if trade.market_question else order_id[:12]
        else:
            strategy = data.get("strategy_id", "UNKNOWN").replace("_", " ").upper()
            market = data.get("market_question", order_id[:12])[:60]

        resolution = data.get("resolution", "—")
        pnl_sign = "+" if pnl >= 0 else ""

        text = (
            f"<b>TRADE CLOSED</b>\n"
            f"Strategy: {strategy}\n"
            f"Market: {market}\n"
            f"Resolution: {resolution}\n"
            f"PnL: {pnl_sign}${pnl:.2f}\n"
            f"ROI: {pnl_sign}{roi:.1f}%"
        )
        self._fire(text)

    def _find_trade(self, order_id):
        if self._state:
            for t in reversed(self._state.trades):
                if t.order_id == order_id:
                    return t
        return None
