import asyncio
import json
import logging
import time

import websockets

from models import Event, EventType

logger = logging.getLogger(__name__)

BINANCE_WS = "wss://stream.binance.com:9443/ws"
STALENESS_THRESHOLD = 15  # seconds


class PriceFeedManager:
    """Binance WebSocket spot feeds for BTC/ETH with staleness detection."""

    def __init__(self):
        self._state = None
        self._bus = None
        self._running = False
        self._tasks = []

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True

        self._tasks = [
            asyncio.create_task(self._stream("btcusdt@trade", "BTC")),
            asyncio.create_task(self._stream("ethusdt@trade", "ETH")),
            asyncio.create_task(self._staleness_monitor()),
        ]
        logger.info("PriceFeedManager started (BTC + ETH)")

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("PriceFeedManager stopped")

    async def _stream(self, stream_name: str, symbol: str):
        url = f"{BINANCE_WS}/{stream_name}"
        backoff = 1

        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    self._state.health["binance_connected"] = True
                    backoff = 1
                    logger.info(f"Binance WS connected: {symbol}")

                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            price = float(msg["p"])
                            self._state.update_spot_price(symbol, price)

                            ts_key = f"last_spot_{symbol.lower()}_update"
                            self._state.health[ts_key] = time.time()
                            self._state.health[f"spot_{symbol.lower()}_stale"] = False
                        except (KeyError, ValueError, TypeError):
                            continue

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Binance WS {symbol} disconnected: {e}")
                self._state.health["binance_connected"] = False
                self._state.health[f"spot_{symbol.lower()}_stale"] = True
                await asyncio.sleep(min(backoff, 30))
                backoff = min(backoff * 2, 30)

    async def _staleness_monitor(self):
        while self._running:
            try:
                await asyncio.sleep(5)
                now = time.time()
                for symbol in ["btc", "eth"]:
                    ts_key = f"last_spot_{symbol}_update"
                    last = self._state.health.get(ts_key)
                    stale = last is None or (now - last) > STALENESS_THRESHOLD
                    self._state.health[f"spot_{symbol}_stale"] = stale
            except asyncio.CancelledError:
                break
            except Exception:
                pass
