import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import aiohttp

from models import MarketSnapshot, Event, EventType, utc_now

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# Slug prefixes that indicate crypto updown markets (used for midpoint refresh filtering)
CRYPTO_SLUG_PREFIXES = [
    "btc-updown-", "eth-updown-",
    "bitcoin-up-or-down", "ethereum-up-or-down",
    "bitcoin-above-", "ethereum-above-",
    "sol-updown-", "xrp-updown-", "bnb-updown-",
]

# Targeted crypto updown discovery: (asset, window_label, interval_seconds)
CRYPTO_UPDOWN_COMBOS = [
    ("btc", "5m", 300),
    ("btc", "15m", 900),
    ("btc", "1h", 3600),
    ("btc", "4h", 14400),
    ("eth", "5m", 300),
    ("eth", "15m", 900),
    ("eth", "1h", 3600),
    ("eth", "4h", 14400),
]


class MarketDataFeed:
    """Polymarket market discovery and pricing.

    Two discovery layers:
      1. Broad: /markets endpoint (500 markets, every 60s)
      2. Targeted: /events endpoint with pagination for crypto updown (every 30s)

    Pricing via CLOB /midpoint and /book endpoints.
    """

    def __init__(self):
        self._state = None
        self._bus = None
        self._running = False
        self._session = None
        self._refresh_task = None
        self._midpoint_task = None
        self._crypto_task = None

        # Discovery stats
        self._stats = {
            "broad_markets_loaded": 0,
            "crypto_markets_discovered": 0,
            "crypto_slugs_queried": 0,
            "crypto_slugs_hit": 0,
            "crypto_updown_btc": 0,
            "crypto_updown_eth": 0,
            "crypto_active_slugs": [],
            "last_broad_fetch": None,
            "last_crypto_fetch": None,
            "crypto_fetch_errors": 0,
        }

    @property
    def discovery_stats(self) -> dict:
        return dict(self._stats)

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "PolymarketEdgeOS/1.0"},
        )

        # Initial loads
        await self._load_broad_markets()
        await self._load_crypto_markets()

        self._refresh_task = asyncio.create_task(self._market_refresh_loop())
        self._midpoint_task = asyncio.create_task(self._midpoint_refresh_loop())
        self._crypto_task = asyncio.create_task(self._crypto_discovery_loop())
        logger.info(
            f"MarketDataFeed started ({len(self._state.markets)} markets, "
            f"crypto={self._stats['crypto_markets_discovered']})"
        )

    async def stop(self):
        self._running = False
        for task in [self._refresh_task, self._midpoint_task, self._crypto_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._session:
            await self._session.close()
        logger.info("MarketDataFeed stopped")

    # ---- Layer 1: Broad Market Discovery ----

    async def _load_broad_markets(self):
        """Fetch top markets from /markets endpoint."""
        try:
            params = {"active": "true", "closed": "false", "limit": "500"}
            async with self._session.get(f"{GAMMA_API}/markets", params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Gamma API /markets status {resp.status}")
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

            self._stats["broad_markets_loaded"] = loaded
            self._stats["last_broad_fetch"] = utc_now()
            self._state.health["last_market_data_update"] = time.time()
            self._state.health["market_data_stale"] = False
            self._state.health["polymarket_connected"] = True
            if loaded:
                logger.info(f"Broad discovery: {loaded} markets")
        except Exception as e:
            logger.error(f"Broad market load failed: {e}")
            self._state.health["market_data_stale"] = True
            self._state.health["polymarket_connected"] = False

    # ---- Layer 2: Targeted Crypto Slug Discovery ----

    async def _load_crypto_markets(self):
        """Discover live crypto updown markets by constructing exact slugs.

        For each (asset, window) combo, compute the current time boundary and
        generate slugs for the current window + next LOOKAHEAD windows.
        Query GET /events?slug={exact_slug} for each — returns 0 or 1 event.
        """
        LOOKAHEAD = 3  # current + next 3 windows
        try:
            now_ts = int(time.time())
            crypto_count = 0
            btc_count = 0
            eth_count = 0
            slugs_queried = 0
            slugs_hit = 0
            active_slugs = []

            for asset, window, interval in CRYPTO_UPDOWN_COMBOS:
                base_ts = (now_ts // interval) * interval
                for offset in range(LOOKAHEAD + 1):
                    ts = base_ts + (offset * interval)
                    slug = f"{asset}-updown-{window}-{ts}"
                    slugs_queried += 1

                    try:
                        async with self._session.get(
                            f"{GAMMA_API}/events",
                            params={"slug": slug},
                        ) as resp:
                            if resp.status != 200:
                                continue
                            events = await resp.json()
                            if not events:
                                continue
                    except Exception:
                        continue

                    event = events[0]
                    if event.get("closed", False):
                        continue

                    slugs_hit += 1
                    for m in event.get("markets", []):
                        try:
                            self._parse_gamma_market(m)
                            crypto_count += 1
                            active_slugs.append(slug)
                            if asset == "btc":
                                btc_count += 1
                            else:
                                eth_count += 1
                        except Exception:
                            continue

                    # Tiny delay between API calls to avoid rate limits
                    await asyncio.sleep(0.05)

            self._stats["crypto_slugs_queried"] = slugs_queried
            self._stats["crypto_slugs_hit"] = slugs_hit
            self._stats["crypto_markets_discovered"] = crypto_count
            self._stats["crypto_updown_btc"] = btc_count
            self._stats["crypto_updown_eth"] = eth_count
            self._stats["crypto_active_slugs"] = active_slugs
            self._stats["last_crypto_fetch"] = utc_now()

            if crypto_count:
                logger.info(
                    f"Crypto slug discovery: {crypto_count} markets "
                    f"(BTC={btc_count} ETH={eth_count}) "
                    f"from {slugs_hit}/{slugs_queried} slug hits"
                )
            else:
                logger.debug(
                    f"Crypto slug discovery: 0 markets from {slugs_queried} slugs"
                )

        except Exception as e:
            logger.error(f"Crypto slug discovery failed: {e}")
            self._stats["crypto_fetch_errors"] += 1

    # ---- Gamma Market Parser ----

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

    # ---- CLOB Pricing ----

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
                await asyncio.sleep(0.15)
            except Exception:
                continue

    # ---- Background Loops ----

    async def _market_refresh_loop(self):
        """Broad market refresh every 60s."""
        while self._running:
            try:
                await asyncio.sleep(60)
                await self._load_broad_markets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Market refresh error: {e}")
                await asyncio.sleep(30)

    async def _crypto_discovery_loop(self):
        """Crypto slug discovery every 15s — catches short-lived updown markets."""
        while self._running:
            try:
                await asyncio.sleep(15)
                await self._load_crypto_markets()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Crypto discovery error: {e}")
                await asyncio.sleep(10)

    async def _midpoint_refresh_loop(self):
        """CLOB midpoint refresh for top-volume + crypto markets."""
        while self._running:
            try:
                await asyncio.sleep(15)
                # Top-volume markets
                sorted_markets = sorted(
                    self._state.markets.values(),
                    key=lambda m: m.volume_24h, reverse=True,
                )
                top_ids = [m.token_id for m in sorted_markets[:30]]

                # Also refresh crypto markets (may not be in top-volume)
                crypto_ids = [
                    m.token_id for m in self._state.markets.values()
                    if any(m.slug.lower().startswith(p) for p in CRYPTO_SLUG_PREFIXES)
                    and m.token_id not in top_ids
                ]

                all_ids = top_ids + crypto_ids[:20]  # cap crypto at 20
                if all_ids:
                    await self._update_midpoints(all_ids)
                    await self._bus.emit(Event(
                        type=EventType.MARKET_UPDATE,
                        source="market_data",
                        data={"tokens_updated": len(all_ids)},
                    ))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Midpoint refresh error: {e}")
                await asyncio.sleep(10)
