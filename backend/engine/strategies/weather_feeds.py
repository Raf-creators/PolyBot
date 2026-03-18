"""Weather data ingestion layer for the Weather strategy.

Responsibilities:
  1. Open-Meteo forecast client (primary) — hourly temperature forecasts
  2. NWS METAR observation client (secondary) — current station observations
  3. Forecast caching with staleness tracking
  4. Station-based data retrieval using STATION_REGISTRY

Architecture:
  - Raw API fetch → normalization → ForecastSnapshot storage
  - Cache keyed by (station_id, target_date)
  - Each source is an independent async method
  - No execution or strategy logic here

All network I/O is async (aiohttp). Failures are logged and return None
rather than raising, so the strategy loop never crashes from feed issues.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, date as date_type, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp

from engine.strategies.weather_models import ForecastSnapshot, StationInfo
from engine.strategies.weather_parser import STATION_REGISTRY

logger = logging.getLogger(__name__)

# ---- API URLs ----

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
NWS_API_BASE = "https://api.weather.gov"
GAMMA_API_EVENTS = "https://gamma-api.polymarket.com/events"

# ---- Cache Entry ----


class _CacheEntry:
    """Internal cache entry wrapping a ForecastSnapshot with a fetch timestamp."""
    __slots__ = ("snapshot", "fetched_at_mono")

    def __init__(self, snapshot: ForecastSnapshot):
        self.snapshot = snapshot
        self.fetched_at_mono = time.monotonic()

    def age_seconds(self) -> float:
        return time.monotonic() - self.fetched_at_mono


# ---- Weather Feed Manager ----


class WeatherFeedManager:
    """Manages weather data ingestion from Open-Meteo and NWS.

    Lifecycle:
      feed = WeatherFeedManager()
      await feed.start()
      ...
      snapshot = await feed.get_forecast("KLGA", "2026-03-15")
      obs = await feed.get_observation("KLGA")
      ...
      await feed.stop()
    """

    def __init__(
        self,
        forecast_cache_ttl_seconds: float = 1800.0,
        observation_cache_ttl_seconds: float = 300.0,
        request_timeout_seconds: float = 15.0,
    ):
        self._session: Optional[aiohttp.ClientSession] = None
        self._forecast_cache: Dict[str, _CacheEntry] = {}   # key: "KLGA:2026-03-15"
        self._observation_cache: Dict[str, _CacheEntry] = {}  # key: "KLGA"
        self._forecast_ttl = forecast_cache_ttl_seconds
        self._observation_ttl = observation_cache_ttl_seconds
        self._request_timeout = request_timeout_seconds

        # Health / observability
        self._health: Dict[str, object] = {
            "open_meteo_last_success": None,
            "open_meteo_last_error": None,
            "open_meteo_errors": 0,
            "nws_last_success": None,
            "nws_last_error": None,
            "nws_errors": 0,
            "forecast_cache_size": 0,
            "observation_cache_size": 0,
        }

    async def start(self):
        """Initialize the HTTP session."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self._request_timeout),
            headers={"User-Agent": "PolymarketEdgeOS/1.0 (weather-strategy)"},
        )
        logger.info("WeatherFeedManager started")

    async def stop(self):
        """Close the HTTP session and clear caches."""
        if self._session:
            await self._session.close()
            self._session = None
        self._forecast_cache.clear()
        self._observation_cache.clear()
        logger.info("WeatherFeedManager stopped")

    @property
    def health(self) -> dict:
        self._health["forecast_cache_size"] = len(self._forecast_cache)
        self._health["observation_cache_size"] = len(self._observation_cache)
        return dict(self._health)

    # ---- Public API ----

    async def get_forecast(
        self,
        station_id: str,
        target_date: str,
        force_refresh: bool = False,
    ) -> Optional[ForecastSnapshot]:
        """Get forecast for a station and target date.

        Returns cached value if fresh enough, otherwise fetches from Open-Meteo.
        Returns None on failure (logged, never raises).
        """
        cache_key = f"{station_id}:{target_date}"

        # Check cache
        if not force_refresh:
            entry = self._forecast_cache.get(cache_key)
            if entry and entry.age_seconds() < self._forecast_ttl:
                return entry.snapshot

        # Fetch fresh
        station = STATION_REGISTRY.get(station_id)
        if not station:
            logger.warning(f"Unknown station: {station_id}")
            return None

        snapshot = await self._fetch_open_meteo_forecast(station, target_date)
        if snapshot:
            self._forecast_cache[cache_key] = _CacheEntry(snapshot)
        return snapshot

    async def get_observation(
        self,
        station_id: str,
        force_refresh: bool = False,
    ) -> Optional[Dict]:
        """Get latest observation for a station from NWS.

        Returns dict with keys: temperature_f, observed_at, station_id.
        Returns None on failure.
        """
        if not force_refresh:
            entry = self._observation_cache.get(station_id)
            if entry and entry.age_seconds() < self._observation_ttl:
                return entry.snapshot  # stored as dict in this case

        obs = await self._fetch_nws_observation(station_id)
        if obs:
            # Store as a lightweight dict (not ForecastSnapshot)
            self._observation_cache[station_id] = _CacheEntry(obs)
        return obs

    async def get_forecasts_bulk(
        self,
        station_dates: List[Tuple[str, str]],
    ) -> Dict[str, ForecastSnapshot]:
        """Fetch forecasts for multiple (station_id, target_date) pairs.

        Returns dict keyed by "station_id:target_date".
        Respects cache; fetches only stale/missing entries.
        Rate-limits requests to avoid hammering the API.
        """
        results = {}
        to_fetch = []

        for station_id, target_date in station_dates:
            cache_key = f"{station_id}:{target_date}"
            entry = self._forecast_cache.get(cache_key)
            if entry and entry.age_seconds() < self._forecast_ttl:
                results[cache_key] = entry.snapshot
            else:
                to_fetch.append((station_id, target_date, cache_key))

        for station_id, target_date, cache_key in to_fetch:
            snapshot = await self.get_forecast(station_id, target_date, force_refresh=True)
            if snapshot:
                results[cache_key] = snapshot
            await asyncio.sleep(0.2)  # rate-limit: 5 req/sec

        return results

    async def discover_weather_events(self, cities: List[str], days_ahead: int = 5) -> List[dict]:
        """Discover active Polymarket weather temperature events via Gamma API.

        Uses TWO strategies for full coverage:
        1. Known city slug probing (fastest, handles known cities)
        2. Broad keyword search (catches global/unknown cities)
        """
        if not self._session:
            return []

        all_markets = []
        seen_conditions = set()
        from datetime import datetime, timezone
        import json as _json

        # ---- Strategy 1: Known city slug probing ----
        city_slug_map = {
            "New York City": "nyc", "Chicago": "chicago",
            "Los Angeles": "los-angeles", "Atlanta": "atlanta",
            "Dallas": "dallas", "Miami": "miami",
            "Denver": "denver", "San Francisco": "san-francisco",
            "Houston": "houston", "Phoenix": "phoenix",
            "Philadelphia": "philadelphia", "San Antonio": "san-antonio",
            "San Diego": "san-diego", "Seattle": "seattle",
            "Boston": "boston", "Nashville": "nashville",
            "Washington": "washington-dc", "Las Vegas": "las-vegas",
            "Portland": "portland", "Minneapolis": "minneapolis",
            "London": "london", "Hong Kong": "hong-kong",
            "Buenos Aires": "buenos-aires", "Tokyo": "tokyo",
            "Sydney": "sydney", "Paris": "paris",
            "Dubai": "dubai", "Singapore": "singapore",
            "Toronto": "toronto", "Mumbai": "mumbai",
            "Berlin": "berlin", "Moscow": "moscow",
            "Seoul": "seoul", "Bangkok": "bangkok",
        }

        today = datetime.now(timezone.utc).date()

        for city_name in list(set(cities)) + [c for c in city_slug_map if c not in cities]:
            city_slug = city_slug_map.get(city_name)
            if not city_slug:
                # Auto-generate slug from city name
                city_slug = city_name.lower().replace(" ", "-").replace("'", "")

            for day_offset in range(0, days_ahead + 1):
                target = today + timedelta(days=day_offset)
                month_name = target.strftime("%B").lower()
                slug = f"highest-temperature-in-{city_slug}-on-{month_name}-{target.day}-{target.year}"

                markets = await self._fetch_slug_markets(slug, seen_conditions)
                all_markets.extend(markets)
                await asyncio.sleep(0.1)

        # ---- Strategy 2: Broad keyword search via Gamma search ----
        search_terms = ["highest temperature", "high temperature", "weather temperature"]
        search_tags = ["temperature", "weather", "rain", "snow", "precipitation", "wind"]
        for tag in search_tags:
            try:
                async with self._session.get(
                    GAMMA_API_EVENTS,
                    params={"tag": tag, "closed": "false", "limit": 100},
                ) as resp:
                    if resp.status == 200:
                        events = await resp.json()
                        for event in (events if isinstance(events, list) else []):
                            for m in event.get("markets", []):
                                q = (m.get("question", "") or "").lower()
                                weather_kw = any(k in q for k in [
                                    "temperature", "temp", "rain", "precipitation",
                                    "snow", "snowfall", "wind", "mph",
                                ])
                                if weather_kw:
                                    market = self._parse_gamma_market(m)
                                    if market and market["condition_id"] not in seen_conditions:
                                        seen_conditions.add(market["condition_id"])
                                        all_markets.append(market)
            except Exception as e:
                logger.debug(f"Broad weather search error for tag='{tag}': {e}")
            await asyncio.sleep(0.2)

        self._health["weather_events_discovered"] = len(all_markets)
        self._health["weather_cities_probed"] = len(city_slug_map)
        return all_markets

    async def _fetch_slug_markets(self, slug: str, seen: set) -> List[dict]:
        """Fetch markets for a specific event slug."""
        results = []
        try:
            async with self._session.get(
                GAMMA_API_EVENTS, params={"slug": slug},
            ) as resp:
                if resp.status != 200:
                    return []
                events = await resp.json()

            for event in (events if isinstance(events, list) else []):
                for m in event.get("markets", []):
                    market = self._parse_gamma_market(m)
                    if market and market["condition_id"] not in seen:
                        seen.add(market["condition_id"])
                        results.append(market)
        except Exception as e:
            logger.debug(f"Slug discovery error for {slug}: {e}")
        return results

    def _parse_gamma_market(self, m: dict) -> Optional[dict]:
        """Parse a Gamma API market dict into our standard format."""
        import json as _json
        clob_ids = m.get("clobTokenIds", "")
        if isinstance(clob_ids, str):
            try:
                clob_ids = _json.loads(clob_ids)
            except (ValueError, TypeError):
                clob_ids = []

        outcome_prices = m.get("outcomePrices", "")
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = _json.loads(outcome_prices)
            except (ValueError, TypeError):
                outcome_prices = []

        yes_token = clob_ids[0] if len(clob_ids) > 0 else ""
        yes_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0

        if not yes_token:
            return None

        return {
            "question": m.get("question", ""),
            "condition_id": m.get("conditionId", ""),
            "yes_token_id": yes_token,
            "mid_price": yes_price,
            "liquidity": float(m.get("liquidity", 0)),
            "end_date_iso": m.get("endDateIso") or m.get("endDate") or "",
        }

    def get_cached_forecast(self, station_id: str, target_date: str) -> Optional[ForecastSnapshot]:
        """Return cached forecast without any network call. Returns None if not cached or stale."""
        cache_key = f"{station_id}:{target_date}"
        entry = self._forecast_cache.get(cache_key)
        if entry and entry.age_seconds() < self._forecast_ttl:
            return entry.snapshot
        return None

    def get_forecast_age_minutes(self, station_id: str, target_date: str) -> Optional[float]:
        """Age of cached forecast in minutes. None if not cached."""
        cache_key = f"{station_id}:{target_date}"
        entry = self._forecast_cache.get(cache_key)
        if entry:
            return entry.age_seconds() / 60.0
        return None

    def evict_stale(self):
        """Remove stale entries from all caches."""
        stale_fc = [k for k, v in self._forecast_cache.items() if v.age_seconds() > self._forecast_ttl * 2]
        for k in stale_fc:
            del self._forecast_cache[k]
        stale_ob = [k for k, v in self._observation_cache.items() if v.age_seconds() > self._observation_ttl * 2]
        for k in stale_ob:
            del self._observation_cache[k]

    # ---- Open-Meteo Forecast ----

    async def _fetch_open_meteo_forecast(
        self,
        station: StationInfo,
        target_date: str,
    ) -> Optional[ForecastSnapshot]:
        """Fetch hourly forecast from Open-Meteo and extract daily high for target_date."""
        if not self._session:
            return None

        try:
            target = date_type.fromisoformat(target_date)
        except (ValueError, TypeError):
            logger.warning(f"Invalid target_date: {target_date}")
            return None

        # Compute forecast_days needed (must include the target date)
        today = datetime.now(timezone.utc).date()
        days_ahead = (target - today).days
        if days_ahead < 0:
            return None  # past date
        forecast_days = min(days_ahead + 2, 16)  # +2 for safety, max 16

        params = {
            "latitude": station.latitude,
            "longitude": station.longitude,
            "hourly": "temperature_2m,precipitation,snowfall,wind_speed_10m",
            "temperature_unit": "fahrenheit",
            "precipitation_unit": "inch",
            "wind_speed_unit": "mph",
            "timezone": station.timezone,
            "forecast_days": forecast_days,
        }

        try:
            async with self._session.get(OPEN_METEO_FORECAST_URL, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    self._health["open_meteo_last_error"] = f"HTTP {resp.status}: {body[:200]}"
                    self._health["open_meteo_errors"] += 1
                    logger.warning(f"Open-Meteo HTTP {resp.status} for {station.station_id}")
                    return None

                data = await resp.json()

        except Exception as e:
            self._health["open_meteo_last_error"] = str(e)
            self._health["open_meteo_errors"] += 1
            logger.warning(f"Open-Meteo fetch error for {station.station_id}: {e}")
            return None

        # Parse response
        return self._parse_open_meteo_response(data, station, target_date)

    def _parse_open_meteo_response(
        self,
        data: dict,
        station: StationInfo,
        target_date: str,
    ) -> Optional[ForecastSnapshot]:
        """Extract daily high, precipitation, snow, and wind from Open-Meteo hourly response."""
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        precips = hourly.get("precipitation", [])
        snows = hourly.get("snowfall", [])
        winds = hourly.get("wind_speed_10m", [])

        if not times or not temps or len(times) != len(temps):
            self._health["open_meteo_last_error"] = "empty or mismatched response arrays"
            return None

        # Filter to target date hours
        target_prefix = target_date  # "2026-03-15"
        target_temps = []
        target_precips = []
        target_snows = []
        target_winds = []
        for i, t in enumerate(times):
            if t.startswith(target_prefix):
                if i < len(temps) and temps[i] is not None:
                    target_temps.append(temps[i])
                if i < len(precips) and precips[i] is not None:
                    target_precips.append(precips[i])
                if i < len(snows) and snows[i] is not None:
                    target_snows.append(snows[i])
                if i < len(winds) and winds[i] is not None:
                    target_winds.append(winds[i])

        if not target_temps:
            logger.debug(f"No hourly data for {station.station_id} on {target_date}")
            return None

        forecast_high = max(target_temps)

        # Daily totals for precip/snow, max for wind
        forecast_precip = round(sum(target_precips), 2) if target_precips else None
        forecast_snow = round(sum(target_snows), 2) if target_snows else None
        forecast_wind = round(max(target_winds), 1) if target_winds else None

        # Lead hours: hours from now until end of target date (11:59 PM local)
        now = datetime.now(timezone.utc)
        try:
            target_dt = datetime.fromisoformat(target_date + "T23:59:00")
            lead_hours = max((target_dt - now.replace(tzinfo=None)).total_seconds() / 3600.0, 0)
        except (ValueError, TypeError):
            lead_hours = 0

        self._health["open_meteo_last_success"] = time.time()

        return ForecastSnapshot(
            station_id=station.station_id,
            target_date=target_date,
            forecast_high_f=round(forecast_high, 1),
            forecast_precip_in=forecast_precip,
            forecast_snow_in=forecast_snow,
            forecast_wind_mph=forecast_wind,
            source="open_meteo",
            lead_hours=round(lead_hours, 1),
            raw_hourly=target_temps,
        )

    # ---- NWS Observation ----

    async def _fetch_nws_observation(self, station_id: str) -> Optional[Dict]:
        """Fetch latest METAR observation from NWS API."""
        if not self._session:
            return None

        url = f"{NWS_API_BASE}/stations/{station_id}/observations/latest"

        try:
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    self._health["nws_last_error"] = f"HTTP {resp.status}"
                    self._health["nws_errors"] += 1
                    return None

                data = await resp.json()

        except Exception as e:
            self._health["nws_last_error"] = str(e)
            self._health["nws_errors"] += 1
            logger.warning(f"NWS fetch error for {station_id}: {e}")
            return None

        return self._parse_nws_observation(data, station_id)

    def _parse_nws_observation(self, data: dict, station_id: str) -> Optional[Dict]:
        """Parse NWS observation JSON into a simple dict."""
        try:
            props = data.get("properties", {})

            # Temperature: NWS returns Celsius as a QuantitativeValue
            temp_obj = props.get("temperature", {})
            temp_c = temp_obj.get("value")
            if temp_c is None:
                return None

            temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)

            observed_at = props.get("timestamp")

            self._health["nws_last_success"] = time.time()

            return {
                "station_id": station_id,
                "temperature_f": temp_f,
                "temperature_c": round(temp_c, 1),
                "observed_at": observed_at,
                "source": "nws_metar",
            }

        except (KeyError, TypeError, ValueError) as e:
            self._health["nws_last_error"] = f"parse error: {e}"
            return None
