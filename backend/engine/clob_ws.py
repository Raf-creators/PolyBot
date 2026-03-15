"""Polymarket CLOB WebSocket client for real-time market data.

Connects to the public Market channel at:
  wss://ws-subscriptions-clob.polymarket.com/ws/market

Streams orderbook snapshots, price changes, best bid/ask, and trades
directly into StateManager so strategies receive real-time prices.

No authentication required for the public Market channel.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

import aiohttp

from models import Event, EventType, utc_now

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PING_INTERVAL = 10  # Polymarket requires pings every 10s
RECONNECT_BASE_DELAY = 2
RECONNECT_MAX_DELAY = 60
MAX_SUBSCRIBE_BATCH = 100  # Subscribe in batches


class ClobWebSocketClient:
    """Real-time CLOB market data via WebSocket.

    Usage:
        client = ClobWebSocketClient()
        client.set_state(state_manager)
        client.set_bus(event_bus)
        await client.start()
        client.subscribe_tokens(["token_id_1", "token_id_2"])
        ...
        await client.stop()
    """

    def __init__(self):
        self._state = None
        self._bus = None
        self._running = False
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None

        # Subscription management
        self._subscribed_tokens: Set[str] = set()
        self._pending_tokens: Set[str] = set()

        # Health metrics
        self._connected = False
        self._connect_time: Optional[float] = None
        self._last_message_time: Optional[float] = None
        self._reconnect_count = 0
        self._messages_received = 0
        self._price_updates = 0
        self._book_updates = 0
        self._trade_updates = 0
        self._errors = 0
        self._last_error: Optional[str] = None

    def set_state(self, state):
        self._state = state

    def set_bus(self, bus):
        self._bus = bus

    # ---- Lifecycle ----

    async def start(self):
        if self._running:
            return
        self._running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        self._reconnect_task = asyncio.create_task(self._connection_loop())
        logger.info("ClobWebSocketClient started")

    async def stop(self):
        self._running = False
        for task in [self._recv_task, self._ping_task, self._reconnect_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session:
            await self._session.close()
        self._connected = False
        logger.info(
            f"ClobWebSocketClient stopped "
            f"(msgs={self._messages_received} prices={self._price_updates} "
            f"books={self._book_updates} trades={self._trade_updates} "
            f"reconnects={self._reconnect_count})"
        )

    # ---- Token Subscription ----

    def subscribe_tokens(self, token_ids: List[str]):
        """Add token IDs to the subscription set. Sends subscribe if connected."""
        new_tokens = set(token_ids) - self._subscribed_tokens
        if not new_tokens:
            return

        self._pending_tokens.update(new_tokens)

        if self._connected and self._ws and not self._ws.closed:
            asyncio.create_task(self._send_subscribe(list(new_tokens)))

    def unsubscribe_tokens(self, token_ids: List[str]):
        """Remove token IDs from the subscription set."""
        for tid in token_ids:
            self._subscribed_tokens.discard(tid)
            self._pending_tokens.discard(tid)

    def get_subscribed_count(self) -> int:
        return len(self._subscribed_tokens)

    # ---- Connection Loop ----

    async def _connection_loop(self):
        delay = RECONNECT_BASE_DELAY
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._errors += 1
                self._last_error = str(e)
                self._connected = False
                logger.warning(f"CLOB WS connection lost: {e}")

            if not self._running:
                break

            # Exponential backoff
            self._reconnect_count += 1
            logger.info(f"CLOB WS reconnecting in {delay}s (attempt #{self._reconnect_count})")
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, RECONNECT_MAX_DELAY)

    async def _connect_and_listen(self):
        """Connect, subscribe, and process messages until disconnected."""
        logger.info(f"CLOB WS connecting to {WS_URL}")
        self._ws = await self._session.ws_connect(
            WS_URL,
            heartbeat=30,
            receive_timeout=60,
        )
        self._connected = True
        self._connect_time = time.time()
        logger.info("CLOB WS connected")

        # Update health
        if self._state:
            self._state.health["clob_ws_connected"] = True

        # Subscribe to all known tokens
        all_tokens = list(self._subscribed_tokens | self._pending_tokens)
        if all_tokens:
            await self._send_subscribe(all_tokens)

        # Start ping task
        self._ping_task = asyncio.create_task(self._ping_loop())

        # Message receive loop
        try:
            async for msg in self._ws:
                if not self._running:
                    break
                if msg.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                    self._last_message_time = time.time()
                    self._messages_received += 1
                    data_str = msg.data if isinstance(msg.data, str) else msg.data.decode("utf-8")
                    await self._handle_message(data_str)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            if self._ping_task:
                self._ping_task.cancel()
                try:
                    await self._ping_task
                except asyncio.CancelledError:
                    pass
            self._connected = False
            if self._state:
                self._state.health["clob_ws_connected"] = False

    async def _send_subscribe(self, token_ids: List[str]):
        """Send subscription message for a batch of token IDs."""
        if not self._ws or self._ws.closed:
            return

        # Subscribe in batches
        for i in range(0, len(token_ids), MAX_SUBSCRIBE_BATCH):
            batch = token_ids[i:i + MAX_SUBSCRIBE_BATCH]
            payload = {
                "assets_ids": batch,
                "type": "market",
                "custom_feature_enabled": True,
            }
            try:
                await self._ws.send_json(payload)
                self._subscribed_tokens.update(batch)
                self._pending_tokens -= set(batch)
                logger.info(f"CLOB WS subscribed to {len(batch)} tokens (total: {len(self._subscribed_tokens)})")
            except Exception as e:
                logger.error(f"CLOB WS subscribe error: {e}")
                self._errors += 1

    async def _ping_loop(self):
        """Send pings every 10s to keep the connection alive."""
        while self._running and self._connected:
            try:
                await asyncio.sleep(PING_INTERVAL)
                if self._ws and not self._ws.closed:
                    await self._ws.ping()
            except asyncio.CancelledError:
                break
            except Exception:
                break

    # ---- Message Handling ----

    async def _handle_message(self, raw: str):
        """Parse and dispatch a CLOB WS message."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Messages can be arrays
        messages = data if isinstance(data, list) else [data]
        for msg in messages:
            event_type = msg.get("event_type")
            if event_type == "price_change":
                await self._on_price_change(msg)
            elif event_type == "book":
                await self._on_book(msg)
            elif event_type == "last_trade_price":
                await self._on_trade(msg)
            elif event_type == "best_bid_ask":
                await self._on_best_bid_ask(msg)

    async def _on_price_change(self, msg: dict):
        """Handle price_change — incremental orderbook updates with BBA."""
        self._price_updates += 1
        asset_id = msg.get("asset_id", "")

        if not self._state or not asset_id:
            return

        existing = self._state.get_market(asset_id)
        if not existing:
            return

        changes = msg.get("price_changes", [])
        best_bid = None
        best_ask = None
        for change in changes:
            bid = change.get("best_bid")
            ask = change.get("best_ask")
            if bid:
                best_bid = float(bid)
            if ask:
                best_ask = float(ask)

        if best_bid is not None and best_ask is not None:
            mid = round((best_bid + best_ask) / 2, 6)
            existing.mid_price = mid
            existing.best_bid = best_bid
            existing.best_ask = best_ask
            existing.updated_at = utc_now()
            self._state.update_market(asset_id, existing)
        elif best_bid is not None:
            existing.best_bid = best_bid
            existing.mid_price = best_bid
            existing.updated_at = utc_now()
            self._state.update_market(asset_id, existing)

        # Emit event for strategies
        if self._bus:
            await self._bus.emit(Event(
                type=EventType.MARKET_UPDATE,
                source="clob_ws",
                data={"token_id": asset_id, "update_type": "price_change"},
            ))

    async def _on_book(self, msg: dict):
        """Handle book — full L2 orderbook snapshot."""
        self._book_updates += 1
        asset_id = msg.get("asset_id", "")

        if not self._state or not asset_id:
            return

        existing = self._state.get_market(asset_id)
        if not existing:
            return

        bids = msg.get("bids", [])
        asks = msg.get("asks", [])

        # Extract best bid/ask from the snapshot
        best_bid = max((float(b["price"]) for b in bids if b.get("price")), default=None)
        best_ask = min((float(a["price"]) for a in asks if a.get("price")), default=None)

        if best_bid is not None and best_ask is not None:
            mid = round((best_bid + best_ask) / 2, 6)
            existing.mid_price = mid
            existing.best_bid = best_bid
            existing.best_ask = best_ask
        elif best_bid is not None:
            existing.mid_price = best_bid
            existing.best_bid = best_bid

        existing.updated_at = utc_now()
        self._state.update_market(asset_id, existing)

    async def _on_trade(self, msg: dict):
        """Handle last_trade_price — a trade just executed."""
        self._trade_updates += 1
        asset_id = msg.get("asset_id", "")

        if not self._state or not asset_id:
            return

        existing = self._state.get_market(asset_id)
        if not existing:
            return

        price = msg.get("price")
        if price:
            existing.last_price = float(price)
            existing.updated_at = utc_now()
            self._state.update_market(asset_id, existing)

    async def _on_best_bid_ask(self, msg: dict):
        """Handle best_bid_ask updates (requires custom_feature_enabled)."""
        asset_id = msg.get("asset_id", "")
        if not self._state or not asset_id:
            return

        existing = self._state.get_market(asset_id)
        if not existing:
            return

        bid = msg.get("best_bid")
        ask = msg.get("best_ask")
        if bid:
            existing.best_bid = float(bid)
        if ask:
            existing.best_ask = float(ask)
        if bid and ask:
            existing.mid_price = round((float(bid) + float(ask)) / 2, 6)

        existing.updated_at = utc_now()
        self._state.update_market(asset_id, existing)

    # ---- Health / Observability ----

    @property
    def health(self) -> Dict[str, Any]:
        uptime = None
        if self._connect_time and self._connected:
            uptime = round(time.time() - self._connect_time, 1)

        last_msg_ago = None
        if self._last_message_time:
            last_msg_ago = round(time.time() - self._last_message_time, 1)

        return {
            "connected": self._connected,
            "url": WS_URL,
            "uptime_seconds": uptime,
            "subscribed_tokens": len(self._subscribed_tokens),
            "pending_tokens": len(self._pending_tokens),
            "messages_received": self._messages_received,
            "price_updates": self._price_updates,
            "book_updates": self._book_updates,
            "trade_updates": self._trade_updates,
            "reconnect_count": self._reconnect_count,
            "errors": self._errors,
            "last_error": self._last_error,
            "last_message_seconds_ago": last_msg_ago,
        }
