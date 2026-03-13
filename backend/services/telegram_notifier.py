"""Telegram notification service for Polymarket Edge OS.

Subscribes to EventBus events and dispatches formatted Telegram messages
asynchronously. Fails gracefully if credentials are missing — the engine
continues to run without alerts.

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
        bus.on(EventType.RISK_ALERT, self._on_risk_alert)
        bus.on(EventType.SYSTEM_EVENT, self._on_system_event)
        bus.on(EventType.SIGNAL, self._on_signal)

        status = "enabled" if self.configured else "disabled (no credentials)"
        logger.info(f"Telegram notifier started [{status}]")

    async def stop(self):
        if self._bus:
            from models import EventType
            self._bus.off(EventType.ORDER_UPDATE, self._on_order_update)
            self._bus.off(EventType.RISK_ALERT, self._on_risk_alert)
            self._bus.off(EventType.SYSTEM_EVENT, self._on_system_event)
            self._bus.off(EventType.SIGNAL, self._on_signal)
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
        if event.source != "paper_adapter":
            return
        if event.data.get("status") != "filled":
            return

        order_id = event.data.get("order_id", "?")
        fill_price = event.data.get("fill_price", 0)
        latency = event.data.get("latency_ms", 0)

        # Look up the trade in state for more context
        trade = None
        if self._state:
            for t in reversed(self._state.trades):
                if t.order_id == order_id:
                    trade = t
                    break

        if trade:
            strategy = trade.strategy_id.replace("_", " ").upper()
            question = trade.market_question[:60] if trade.market_question else order_id[:12]
            text = (
                f"<b>[TRADE EXECUTED]</b>\n"
                f"Strategy: {strategy}\n"
                f"Market: {question}\n"
                f"Side: {trade.side.value.upper()}\n"
                f"Price: {fill_price:.4f}\n"
                f"Size: {trade.size}\n"
                f"Latency: {latency:.1f}ms"
            )
        else:
            text = (
                f"<b>[TRADE EXECUTED]</b>\n"
                f"Order: {order_id[:12]}\n"
                f"Price: {fill_price:.4f}\n"
                f"Latency: {latency:.1f}ms"
            )

        self._fire(text)

    async def _on_risk_alert(self, event):
        if not self.enabled:
            return

        data = event.data
        action = data.get("action")

        if action == "kill_switch_activated":
            text = (
                f"<b>[RISK ALERT]</b>\n"
                f"Kill switch ACTIVATED\n"
                f"Reason: {data.get('reason', 'unknown')}"
            )
        else:
            text = (
                f"<b>[RISK]</b>\n"
                f"Order rejected\n"
                f"Reason: {data.get('reason', 'unknown')}"
            )

        self._fire(text)

    async def _on_system_event(self, event):
        if not self.enabled:
            return

        action = event.data.get("action", "")
        mode = event.data.get("mode", "")

        if action in ("started", "stopped"):
            text = (
                f"<b>[ENGINE]</b>\n"
                f"{action.upper()}\n"
                f"Mode: {mode}"
            )
            self._fire(text)

    async def _on_signal(self, event):
        if not self.signals_enabled:
            return

        d = event.data
        strategy = d.get("strategy", "?").upper()
        asset = d.get("asset", "")
        strike = d.get("strike", "")
        fair = d.get("fair_price", 0)
        mkt = d.get("market_price", 0)
        edge = d.get("edge_bps", 0)
        side = d.get("side", "")

        text = (
            f"<b>[SIGNAL]</b>\n"
            f"Strategy: {strategy}\n"
            f"Asset: {asset}\n"
            f"Strike: {strike}\n"
            f"Fair: {fair:.4f}\n"
            f"Market: {mkt:.4f}\n"
            f"Edge: {edge:.0f}bps\n"
            f"Side: {side}"
        )

        self._fire(text)

    # ---- Formatting helpers (for external use / testing) ----

    @staticmethod
    def format_trade(strategy, market, side, price, size, edge_bps):
        return (
            f"<b>[TRADE EXECUTED]</b>\n"
            f"Strategy: {strategy}\n"
            f"Market: {market}\n"
            f"Side: {side}\n"
            f"Price: {price:.4f}\n"
            f"Size: {size}\n"
            f"Edge: {edge_bps:.0f}bps"
        )

    @staticmethod
    def format_signal(strategy, asset, strike, fair, market, edge_bps):
        return (
            f"<b>[SIGNAL]</b>\n"
            f"Strategy: {strategy}\n"
            f"Asset: {asset}\n"
            f"Strike: {strike}\n"
            f"Fair: {fair:.4f}\n"
            f"Market: {market:.4f}\n"
            f"Edge: {edge_bps:.0f}bps"
        )

    @staticmethod
    def format_risk(reason):
        return (
            f"<b>[RISK]</b>\n"
            f"Order rejected\n"
            f"Reason: {reason}"
        )

    @staticmethod
    def format_engine(action, mode=""):
        return (
            f"<b>[ENGINE]</b>\n"
            f"{action.upper()}\n"
            f"Mode: {mode}"
        )
