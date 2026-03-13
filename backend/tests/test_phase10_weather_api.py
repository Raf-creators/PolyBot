"""API endpoint tests for Phase 10 Step 6: weather strategy server integration.

Tests all 7 weather-related API endpoints using curl-equivalent HTTP calls.
Uses the running server — not mocked.
"""

import pytest
import requests
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

API_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip(),
)


class TestWeatherAPIEndpoints:
    def test_health(self):
        r = requests.get(f"{API_URL}/api/strategies/weather/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "total_scans" in data
        assert "running" in data
        assert "feed_health" in data
        assert "stations" in data

    def test_config(self):
        r = requests.get(f"{API_URL}/api/strategies/weather/config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "enabled" in data
        assert "scan_interval" in data
        assert "min_edge_bps" in data
        assert "kelly_scale" in data

    def test_stations(self):
        r = requests.get(f"{API_URL}/api/strategies/weather/stations", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 8
        ids = [s["station_id"] for s in data]
        assert "KLGA" in ids
        assert "KORD" in ids

    def test_signals(self):
        r = requests.get(f"{API_URL}/api/strategies/weather/signals", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "tradable" in data
        assert "rejected" in data
        assert isinstance(data["tradable"], list)

    def test_executions(self):
        r = requests.get(f"{API_URL}/api/strategies/weather/executions", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "active" in data
        assert "completed" in data

    def test_forecasts(self):
        r = requests.get(f"{API_URL}/api/strategies/weather/forecasts", timeout=10)
        assert r.status_code == 200
        # Empty dict when no markets classified
        assert isinstance(r.json(), dict)

    def test_config_strategies_includes_weather(self):
        r = requests.get(f"{API_URL}/api/config/strategies", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "weather_trader" in data
        assert data["weather_trader"]["enabled"] is True
