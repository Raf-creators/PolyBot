"""Polymarket CLOB WebSocket — User/Trade channel for real-time fill updates.

Connects to wss://ws-subscriptions-clob.polymarket.com/ws/user with API
credentials and subscribes to condition_ids of tracked orders. Processes
trade events (MATCHED, MINED, CONFIRMED, FAILED) and dispatches fill
updates to the LiveAdapter.

Architecture:
  - Runs as an asyncio.Task alongside the existing market-data WS
  - Requires API credentials (api_key, api_secret, passphrase)
  - Maintains heartbeat ping every 10s
  - Auto-reconnects with exponential backoff
  - Calls a fill_callback when trade events arrive
"""

import asyncio
import json
import logging
import time
from typing import Callable, Dict, Optional, Set

import aiohttp

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
PING_INTERVAL = 10
RECONNECT_BASE = 2.0
RECONNECT_MAX = 60.0


class ClobFillWsClient:
    """WebSocket client for Polymarket CLOB user/trade channel."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        fill_callback: Optional[Callable] = None,
    ):
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._fill_callback = fill_callback

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Subscriptions: condition_ids we care about
        self._subscribed_markets: Set[str] = set()

        # Metrics
        self._connected = False
        self._connect_count = 0
        self._disconnect_count = 0
        self._messages_received = 0
        self._trade_events = 0
        self._confirmed_fills = 0
        self._failed_fills = 0
        self._last_message_at: Optional[float] = None
        self._last_error: Optional[str] = None

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key and self._api_secret and self._passphrase)

    # ---- Lifecycle ----

    async def start(self):
        if self._running:
            return
        if not self.has_credentials:
            logger.info("[FILL WS] No API credentials — fill WebSocket disabled")
            return
        self._running = True
        self._session = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._connect_loop())
        logger.info("[FILL WS] Fill WebSocket client started")

    async def stop(self):
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
        self._connected = False
        logger.info("[FILL WS] Fill WebSocket client stopped")

    # ---- Connection ----

    async def _connect_loop(self):
        backoff = RECONNECT_BASE
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                return
            except Exception as e:
                self._last_error = str(e)
                self._disconnect_count += 1
                self._connected = False
                logger.warning(f"[FILL WS] Disconnected: {e}. Reconnecting in {backoff:.0f}s")
            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, RECONNECT_MAX)

    async def _connect_and_listen(self):
        logger.info(f"[FILL WS] Connecting to {WS_URL}")
        self._ws = await self._session.ws_connect(WS_URL, heartbeat=PING_INTERVAL)
        self._connected = True
        self._connect_count += 1
        logger.info("[FILL WS] Connected")

        # Send auth + subscribe
        await self._send_subscription()

        # Start ping task
        ping_task = asyncio.create_task(self._ping_loop())
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._messages_received += 1
                    self._last_message_at = time.time()
                    await self._handle_message(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            ping_task.cancel()
            self._connected = False

    async def _ping_loop(self):
        try:
            while self._running and self._ws and not self._ws.closed:
                await asyncio.sleep(PING_INTERVAL)
                if self._ws and not self._ws.closed:
                    await self._ws.ping()
        except (asyncio.CancelledError, Exception):
            pass

    # ---- Subscriptions ----

    async def _send_subscription(self):
        """Send initial auth + market subscription."""
        sub_msg = {
            "auth": {
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "passphrase": self._passphrase,
            },
            "type": "user",
        }
        if self._subscribed_markets:
            sub_msg["markets"] = list(self._subscribed_markets)

        if self._ws and not self._ws.closed:
            await self._ws.send_json(sub_msg)
            logger.info(f"[FILL WS] Subscribed with {len(self._subscribed_markets)} markets")

    async def subscribe_markets(self, condition_ids: Set[str]):
        """Subscribe to additional condition_ids (can be called while connected)."""
        new_markets = condition_ids - self._subscribed_markets
        if not new_markets:
            return
        self._subscribed_markets |= new_markets
        if self._ws and not self._ws.closed:
            await self._ws.send_json({
                "type": "user",
                "operation": "subscribe",
                "markets": list(new_markets),
            })
            logger.info(f"[FILL WS] Subscribed to {len(new_markets)} additional markets")

    async def unsubscribe_markets(self, condition_ids: Set[str]):
        """Unsubscribe from condition_ids."""
        to_unsub = condition_ids & self._subscribed_markets
        if not to_unsub:
            return
        self._subscribed_markets -= to_unsub
        if self._ws and not self._ws.closed:
            await self._ws.send_json({
                "type": "user",
                "operation": "unsubscribe",
                "markets": list(to_unsub),
            })

    # ---- Message Handling ----

    async def _handle_message(self, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Handle arrays of events
        events = data if isinstance(data, list) else [data]
        for event in events:
            event_type = event.get("event_type") or event.get("type", "")
            if event_type.upper() in ("TRADE", "trade"):
                await self._process_trade_event(event)

    async def _process_trade_event(self, event: dict):
        """Process a trade/fill event from the user channel."""
        self._trade_events += 1

        status = (event.get("status") or "").upper()
        asset_id = event.get("asset_id", "")
        condition_id = event.get("market", "")
        side = event.get("side", "").lower()
        size = float(event.get("size", 0))
        price = float(event.get("price", 0))
        trade_id = event.get("id", "")
        taker_order_id = event.get("taker_order_id", "")
        trader_side = event.get("trader_side", "")
        timestamp = event.get("timestamp", "")
        tx_hash = event.get("transaction_hash", "")

        is_terminal = status in ("CONFIRMED", "FAILED")
        is_fill = status in ("MATCHED", "MINED", "CONFIRMED")
        is_failure = status == "FAILED"

        if is_failure:
            self._failed_fills += 1
        if status == "CONFIRMED":
            self._confirmed_fills += 1

        logger.info(
            f"[FILL WS] Trade event: status={status} asset={asset_id[:16]}... "
            f"side={side} size={size} price={price} "
            f"trader_side={trader_side} tx={tx_hash[:16] if tx_hash else 'n/a'}..."
        )

        # Dispatch to callback
        if self._fill_callback and is_fill:
            try:
                await self._fill_callback({
                    "source": "websocket",
                    "trade_id": trade_id,
                    "asset_id": asset_id,
                    "condition_id": condition_id,
                    "taker_order_id": taker_order_id,
                    "side": side,
                    "size": size,
                    "price": price,
                    "status": status,
                    "trader_side": trader_side,
                    "timestamp": timestamp,
                    "transaction_hash": tx_hash,
                    "is_terminal": is_terminal,
                })
            except Exception as e:
                logger.error(f"[FILL WS] Fill callback error: {e}")

    # ---- Health ----

    @property
    def health(self) -> dict:
        last_msg_ago = None
        if self._last_message_at:
            last_msg_ago = round(time.time() - self._last_message_at, 1)
        return {
            "connected": self._connected,
            "has_credentials": self.has_credentials,
            "connect_count": self._connect_count,
            "disconnect_count": self._disconnect_count,
            "messages_received": self._messages_received,
            "trade_events": self._trade_events,
            "confirmed_fills": self._confirmed_fills,
            "failed_fills": self._failed_fills,
            "subscribed_markets": len(self._subscribed_markets),
            "last_message_seconds_ago": last_msg_ago,
            "last_error": self._last_error,
        }
