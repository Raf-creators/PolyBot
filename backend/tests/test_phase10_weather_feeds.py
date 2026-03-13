"""Tests for Phase 10 Step 4: weather_feeds.py

Covers:
  - Forecast cache behavior (TTL, hits, misses, eviction)
  - Open-Meteo response parsing and normalization
  - NWS observation response parsing (C→F conversion)
  - Staleness tracking and health reporting
  - Graceful failure handling (HTTP errors, malformed JSON, network errors)
  - Cache-only reads (no network)

All tests use mocked HTTP responses — no live external API calls.
Async tests use asyncio.run() for portability (no plugin dependency).
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.strategies.weather_feeds import WeatherFeedManager, _CacheEntry
from engine.strategies.weather_models import ForecastSnapshot
from engine.strategies.weather_parser import STATION_REGISTRY


# ---- Mock Helpers ----

def _make_open_meteo_response(target_date: str, temps: list):
    """Build a realistic Open-Meteo JSON response."""
    times = [f"{target_date}T{h:02d}:00" for h in range(len(temps))]
    return {
        "latitude": 40.78,
        "longitude": -73.87,
        "hourly": {
            "time": times,
            "temperature_2m": temps,
        },
        "hourly_units": {"temperature_2m": "°F"},
    }


def _make_nws_observation(temp_c: float, timestamp: str = "2026-03-15T18:00:00+00:00"):
    return {
        "properties": {
            "temperature": {"value": temp_c, "unitCode": "wmoUnit:degC"},
            "timestamp": timestamp,
        }
    }


class MockResponse:
    """Minimal mock for aiohttp response context manager."""
    def __init__(self, status, json_data=None, text_data=""):
        self.status = status
        self._json = json_data
        self._text = text_data

    async def json(self):
        return self._json

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _mock_session_get(response):
    """Create a MagicMock session whose .get() returns the given MockResponse."""
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    return session


def _mock_session_get_error(exc):
    """Create a MagicMock session whose .get() raises the given exception."""
    session = MagicMock()
    session.get = MagicMock(side_effect=exc)
    return session


# ===========================================================================
# Open-Meteo Response Parsing
# ===========================================================================

class TestOpenMeteoResponseParsing:
    def test_parse_valid_response(self):
        feed = WeatherFeedManager()
        station = STATION_REGISTRY["KLGA"]
        temps = [35.0, 34.0, 33.5, 34.0, 36.0, 38.0, 40.0, 42.0,
                 44.0, 45.5, 46.0, 45.0, 44.0, 43.0, 42.0, 41.0,
                 40.0, 39.0, 38.0, 37.0, 36.5, 36.0, 35.5, 35.0]
        data = _make_open_meteo_response("2026-03-15", temps)

        snapshot = feed._parse_open_meteo_response(data, station, "2026-03-15")
        assert snapshot is not None
        assert snapshot.station_id == "KLGA"
        assert snapshot.target_date == "2026-03-15"
        assert snapshot.forecast_high_f == 46.0
        assert snapshot.source == "open_meteo"
        assert snapshot.raw_hourly == temps

    def test_parse_empty_response(self):
        feed = WeatherFeedManager()
        station = STATION_REGISTRY["KLGA"]
        data = {"hourly": {"time": [], "temperature_2m": []}}
        assert feed._parse_open_meteo_response(data, station, "2026-03-15") is None

    def test_parse_no_matching_date(self):
        feed = WeatherFeedManager()
        station = STATION_REGISTRY["KLGA"]
        data = _make_open_meteo_response("2026-03-14", [40.0, 41.0])
        assert feed._parse_open_meteo_response(data, station, "2026-03-15") is None

    def test_parse_with_none_temps(self):
        feed = WeatherFeedManager()
        station = STATION_REGISTRY["KLGA"]
        temps = [40.0, None, 42.0, None, 44.0]
        data = _make_open_meteo_response("2026-03-15", temps)
        snapshot = feed._parse_open_meteo_response(data, station, "2026-03-15")
        assert snapshot is not None
        assert snapshot.forecast_high_f == 44.0
        assert len(snapshot.raw_hourly) == 3  # None values filtered

    def test_parse_mismatched_arrays(self):
        feed = WeatherFeedManager()
        station = STATION_REGISTRY["KLGA"]
        data = {"hourly": {"time": ["2026-03-15T00:00"], "temperature_2m": []}}
        assert feed._parse_open_meteo_response(data, station, "2026-03-15") is None


# ===========================================================================
# NWS Observation Parsing
# ===========================================================================

class TestNWSObservationParsing:
    def test_parse_valid(self):
        feed = WeatherFeedManager()
        data = _make_nws_observation(temp_c=7.2)
        obs = feed._parse_nws_observation(data, "KLGA")
        assert obs is not None
        assert obs["station_id"] == "KLGA"
        assert abs(obs["temperature_f"] - 45.0) < 0.1
        assert obs["source"] == "nws_metar"

    def test_parse_null_temperature(self):
        feed = WeatherFeedManager()
        data = {"properties": {"temperature": {"value": None}}}
        assert feed._parse_nws_observation(data, "KLGA") is None

    def test_parse_missing_properties(self):
        feed = WeatherFeedManager()
        assert feed._parse_nws_observation({}, "KLGA") is None

    def test_freezing_point_conversion(self):
        feed = WeatherFeedManager()
        obs = feed._parse_nws_observation(_make_nws_observation(0.0), "KLGA")
        assert abs(obs["temperature_f"] - 32.0) < 0.01

    def test_negative_temperature(self):
        feed = WeatherFeedManager()
        obs = feed._parse_nws_observation(_make_nws_observation(-10.0), "KORD")
        assert abs(obs["temperature_f"] - 14.0) < 0.01  # -10C = 14F


# ===========================================================================
# Cache Behavior
# ===========================================================================

class TestCacheBehavior:
    def test_cache_entry_age(self):
        snapshot = ForecastSnapshot(
            station_id="KLGA", target_date="2026-03-15",
            forecast_high_f=44.0, lead_hours=36.0,
        )
        entry = _CacheEntry(snapshot)
        assert entry.age_seconds() < 1.0
        time.sleep(0.05)
        assert entry.age_seconds() >= 0.05

    def test_cache_hit(self):
        feed = WeatherFeedManager(forecast_cache_ttl_seconds=60.0)
        snapshot = ForecastSnapshot(
            station_id="KLGA", target_date="2026-03-15",
            forecast_high_f=44.0, lead_hours=36.0,
        )
        feed._forecast_cache["KLGA:2026-03-15"] = _CacheEntry(snapshot)
        result = feed.get_cached_forecast("KLGA", "2026-03-15")
        assert result is not None
        assert result.forecast_high_f == 44.0

    def test_cache_miss(self):
        feed = WeatherFeedManager()
        assert feed.get_cached_forecast("KLGA", "2026-03-15") is None

    def test_stale_cache_returns_none(self):
        feed = WeatherFeedManager(forecast_cache_ttl_seconds=0.01)
        snapshot = ForecastSnapshot(
            station_id="KLGA", target_date="2026-03-15",
            forecast_high_f=44.0, lead_hours=36.0,
        )
        feed._forecast_cache["KLGA:2026-03-15"] = _CacheEntry(snapshot)
        time.sleep(0.05)
        assert feed.get_cached_forecast("KLGA", "2026-03-15") is None

    def test_forecast_age_minutes(self):
        feed = WeatherFeedManager()
        assert feed.get_forecast_age_minutes("KLGA", "2026-03-15") is None
        snapshot = ForecastSnapshot(
            station_id="KLGA", target_date="2026-03-15",
            forecast_high_f=44.0, lead_hours=36.0,
        )
        feed._forecast_cache["KLGA:2026-03-15"] = _CacheEntry(snapshot)
        age = feed.get_forecast_age_minutes("KLGA", "2026-03-15")
        assert age is not None
        assert age < 1.0

    def test_evict_stale(self):
        feed = WeatherFeedManager(forecast_cache_ttl_seconds=0.01)
        snapshot = ForecastSnapshot(
            station_id="KLGA", target_date="2026-03-15",
            forecast_high_f=44.0, lead_hours=36.0,
        )
        feed._forecast_cache["KLGA:2026-03-15"] = _CacheEntry(snapshot)
        time.sleep(0.05)
        feed.evict_stale()
        assert len(feed._forecast_cache) == 0


# ===========================================================================
# Health Reporting
# ===========================================================================

class TestHealthReporting:
    def test_initial_health(self):
        h = WeatherFeedManager().health
        assert h["open_meteo_last_success"] is None
        assert h["open_meteo_errors"] == 0
        assert h["forecast_cache_size"] == 0

    def test_health_reflects_cache(self):
        feed = WeatherFeedManager()
        feed._forecast_cache["k1"] = _CacheEntry(ForecastSnapshot(
            station_id="KLGA", target_date="2026-03-15",
            forecast_high_f=44.0, lead_hours=36.0,
        ))
        assert feed.health["forecast_cache_size"] == 1


# ===========================================================================
# Network Failure Handling (async, using asyncio.run)
# ===========================================================================

class TestNetworkFailures:
    def test_open_meteo_http_error(self):
        async def _run():
            feed = WeatherFeedManager()
            feed._session = _mock_session_get(MockResponse(500, text_data="Server Error"))
            station = STATION_REGISTRY["KLGA"]
            result = await feed._fetch_open_meteo_forecast(station, "2026-03-15")
            assert result is None
            assert feed._health["open_meteo_errors"] == 1
        asyncio.run(_run())

    def test_open_meteo_network_error(self):
        async def _run():
            feed = WeatherFeedManager()
            feed._session = _mock_session_get_error(Exception("Connection refused"))
            station = STATION_REGISTRY["KLGA"]
            result = await feed._fetch_open_meteo_forecast(station, "2026-03-15")
            assert result is None
            assert "Connection refused" in feed._health["open_meteo_last_error"]
        asyncio.run(_run())

    def test_nws_http_error(self):
        async def _run():
            feed = WeatherFeedManager()
            feed._session = _mock_session_get(MockResponse(404))
            result = await feed._fetch_nws_observation("KLGA")
            assert result is None
            assert feed._health["nws_errors"] == 1
        asyncio.run(_run())

    def test_nws_network_error(self):
        async def _run():
            feed = WeatherFeedManager()
            feed._session = _mock_session_get_error(Exception("Timeout"))
            result = await feed._fetch_nws_observation("KLGA")
            assert result is None
            assert feed._health["nws_errors"] == 1
        asyncio.run(_run())

    def test_no_session_open_meteo(self):
        async def _run():
            feed = WeatherFeedManager()
            feed._session = None
            station = STATION_REGISTRY["KLGA"]
            result = await feed._fetch_open_meteo_forecast(station, "2026-03-15")
            assert result is None
        asyncio.run(_run())

    def test_no_session_nws(self):
        async def _run():
            feed = WeatherFeedManager()
            feed._session = None
            result = await feed._fetch_nws_observation("KLGA")
            assert result is None
        asyncio.run(_run())


# ===========================================================================
# get_forecast integration (cache miss → API → cache)
# ===========================================================================

class TestGetForecastIntegration:
    def test_unknown_station_returns_none(self):
        async def _run():
            feed = WeatherFeedManager()
            feed._session = MagicMock()
            result = await feed.get_forecast("KZZZ", "2026-03-15")
            assert result is None
        asyncio.run(_run())

    def test_successful_fetch_populates_cache(self):
        async def _run():
            feed = WeatherFeedManager()
            temps = [40.0 + i for i in range(24)]
            resp = MockResponse(200, _make_open_meteo_response("2026-03-20", temps))
            feed._session = _mock_session_get(resp)
            result = await feed.get_forecast("KLGA", "2026-03-20")
            assert result is not None
            assert result.forecast_high_f == 63.0  # 40+23
            # Now cache should be populated
            cached = feed.get_cached_forecast("KLGA", "2026-03-20")
            assert cached is not None
            assert cached.forecast_high_f == 63.0
        asyncio.run(_run())


# ===========================================================================
# Lifecycle
# ===========================================================================

class TestLifecycle:
    def test_start_stop(self):
        async def _run():
            feed = WeatherFeedManager()
            await feed.start()
            assert feed._session is not None
            await feed.stop()
            assert feed._session is None
            assert len(feed._forecast_cache) == 0
        asyncio.run(_run())
