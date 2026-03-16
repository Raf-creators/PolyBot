import asyncio
import json
import logging
import time

import aiohttp

from models import MarketSnapshot, Event, EventType, utc_now

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


class MarketDataFeed:
    """Polymarket market discovery and midpoint polling."""

    def __init__(self):
        self._state = None
        self._bus = None
        self._running = False
        self._session = None
        self._refresh_task = None
        self._midpoint_task = None

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
        )

        await self._load_markets()

        self._refresh_task = asyncio.create_task(self._market_refresh_loop())
        self._midpoint_task = asyncio.create_task(self._midpoint_refresh_loop())
        logger.info(f"MarketDataFeed started ({len(self._state.markets)} markets)")

    async def stop(self):
        self._running = False
        for task in [self._refresh_task, self._midpoint_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._session:
            await self._session.close()
        logger.info("MarketDataFeed stopped")

    # ---- Market Discovery (Gamma API) ----

    async def _load_markets(self):
        try:
            params = {"active": "true", "closed": "false", "limit": "500"}
            async with self._session.get(f"{GAMMA_API}/markets", params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Gamma API status {resp.status}")
                    self._state.health["market_data_stale"] = True
                    return
                markets = await resp.json()

            loaded = 0
            for m in markets:
                try:
                    self._parse_gamma_market(m)
                    loaded += 1
                except Exception:
                    continue

            self._state.health["last_market_data_update"] = time.time()
            self._state.health["market_data_stale"] = False
            self._state.health["polymarket_connected"] = True
            if loaded:
                logger.info(f"Loaded {loaded} markets from Gamma API")
        except Exception as e:
            logger.error(f"Market load failed: {e}")
            self._state.health["market_data_stale"] = True
            self._state.health["polymarket_connected"] = False

    def _parse_gamma_market(self, m: dict):
        question = m.get("question", "")
        condition_id = m.get("conditionId", "")
        slug = m.get("slug", "")
        end_date = m.get("endDate")
        try:
            outcomes = json.loads(m.get("outcomes", "[]"))
            prices = json.loads(m.get("outcomePrices", "[]"))
            token_ids = json.loads(m.get("clobTokenIds", "[]"))
        except (json.JSONDecodeError, TypeError):
            return

        if len(token_ids) < 2 or len(outcomes) < 2:
            return

        volume = float(m.get("volume", 0) or 0)
        liquidity = float(m.get("liquidity", 0) or 0)

        for i, (outcome, token_id) in enumerate(zip(outcomes, token_ids)):
            if not token_id:
                continue
            price = float(prices[i]) if i < len(prices) else None
            complement = token_ids[1 - i] if len(token_ids) > 1 else None

            self._state.update_market(token_id, MarketSnapshot(
                token_id=token_id,
                condition_id=condition_id,
                question=question,
                outcome=outcome,
                slug=slug,
                end_date=end_date,
                complement_token_id=complement,
                mid_price=price,
                last_price=price,
                volume_24h=volume,
                liquidity=liquidity,
                updated_at=utc_now(),
            ))

    # ---- Midpoint Refresh (CLOB API) ----

    async def _update_midpoints(self, token_ids: list):
        for token_id in token_ids:
            if not self._running:
                break
            try:
                async with self._session.get(
                    f"{CLOB_API}/midpoint", params={"token_id": token_id}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        mid = float(data.get("mid", 0))
                        existing = self._state.get_market(token_id)
                        if existing and mid > 0:
                            existing.mid_price = mid
                            existing.updated_at = utc_now()
                            self._state.update_market(token_id, existing)
                await asyncio.sleep(0.15)  # rate-limit
            except Exception:
                continue

    # ---- Background loops ----

    async def _market_refresh_loop(self):
        while self._running:
            try:
                await asyncio.sleep(60)
                await self._load_markets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Market refresh error: {e}")
                await asyncio.sleep(30)

    async def _midpoint_refresh_loop(self):
        while self._running:
            try:
                await asyncio.sleep(15)
                # Only refresh top-volume markets
                sorted_markets = sorted(
                    self._state.markets.values(),
                    key=lambda m: m.volume_24h, reverse=True,
                )
                top_ids = [m.token_id for m in sorted_markets[:30]]
                if top_ids:
                    await self._update_midpoints(top_ids)
                    await self._bus.emit(Event(
                        type=EventType.MARKET_UPDATE,
                        source="market_data",
                        data={"tokens_updated": len(top_ids)},
                    ))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Midpoint refresh error: {e}")
                await asyncio.sleep(10)
