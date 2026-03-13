"""Phase 10: Weather API Integration Tests via HTTP
Tests all weather endpoints through the live server to verify response shapes and data.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestWeatherIntegrationHTTP:
    """Weather API HTTP integration tests - validates endpoints via external URL"""

    def test_health_endpoint(self):
        """GET /api/health - returns healthy status"""
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "engine" in data
        assert "mode" in data
        print(f"✓ /api/health: status={data['status']}, engine={data['engine']}, mode={data['mode']}")

    def test_weather_health_endpoint(self):
        """GET /api/strategies/weather/health - returns health data with all required fields"""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert r.status_code == 200
        data = r.json()
        
        # Core metrics present
        assert "total_scans" in data
        assert "running" in data
        assert "feed_health" in data
        assert "config" in data
        assert "calibration_status" in data
        
        # Config fields
        config = data["config"]
        assert "scan_interval" in config
        assert "min_edge_bps" in config
        assert "kelly_scale" in config
        assert "min_confidence" in config
        assert "default_size" in config
        assert "max_signal_size" in config
        
        # Feed health
        feed = data["feed_health"]
        assert isinstance(feed, dict)
        
        # Calibration status
        cal = data["calibration_status"]
        assert "using_defaults" in cal
        assert "note" in cal
        
        # Stations list
        assert "stations" in data
        assert isinstance(data["stations"], list)
        assert len(data["stations"]) == 8  # Should have 8 stations
        
        print(f"✓ /api/strategies/weather/health: scans={data['total_scans']}, running={data['running']}, stations={len(data['stations'])}")

    def test_weather_config_endpoint(self):
        """GET /api/strategies/weather/config - returns config with all WeatherConfig fields"""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert r.status_code == 200
        data = r.json()
        
        # Top level
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)
        
        # Required WeatherConfig fields
        required_fields = [
            "scan_interval", "forecast_refresh_interval", "classification_refresh_interval",
            "min_edge_bps", "min_liquidity", "min_confidence", "max_sigma",
            "min_hours_to_resolution", "max_hours_to_resolution", "max_stale_forecast_minutes",
            "max_stale_market_seconds", "max_spread_sum", "default_size", "max_signal_size",
            "kelly_scale", "max_concurrent_signals", "max_buckets_per_market", "cooldown_seconds"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ /api/strategies/weather/config: enabled={data['enabled']}, min_edge={data['min_edge_bps']}bps, kelly={data['kelly_scale']}")

    def test_weather_stations_endpoint(self):
        """GET /api/strategies/weather/stations - returns 8 stations with required fields"""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/stations")
        assert r.status_code == 200
        data = r.json()
        
        assert isinstance(data, list)
        assert len(data) == 8, f"Expected 8 stations, got {len(data)}"
        
        required_fields = ["station_id", "city", "latitude", "longitude", "timezone"]
        
        for station in data:
            for field in required_fields:
                assert field in station, f"Station missing field: {field}"
        
        # Print station summary
        stations = [s["station_id"] for s in data]
        print(f"✓ /api/strategies/weather/stations: {len(data)} stations - {', '.join(stations)}")

    def test_weather_signals_endpoint(self):
        """GET /api/strategies/weather/signals - returns signal structure (empty when idle)"""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert r.status_code == 200
        data = r.json()
        
        # Structure validation
        assert "tradable" in data
        assert "rejected" in data
        assert "total_tradable" in data
        assert "total_rejected" in data
        
        assert isinstance(data["tradable"], list)
        assert isinstance(data["rejected"], list)
        assert isinstance(data["total_tradable"], int)
        assert isinstance(data["total_rejected"], int)
        
        print(f"✓ /api/strategies/weather/signals: tradable={data['total_tradable']}, rejected={data['total_rejected']}")

    def test_weather_executions_endpoint(self):
        """GET /api/strategies/weather/executions - returns execution structure"""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/executions")
        assert r.status_code == 200
        data = r.json()
        
        assert "active" in data
        assert "completed" in data
        assert isinstance(data["active"], list)
        assert isinstance(data["completed"], list)
        
        print(f"✓ /api/strategies/weather/executions: active={len(data['active'])}, completed={len(data['completed'])}")

    def test_weather_forecasts_endpoint(self):
        """GET /api/strategies/weather/forecasts - returns empty dict when no markets classified"""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/forecasts")
        assert r.status_code == 200
        data = r.json()
        
        # Should be empty dict when engine is idle and no weather markets
        assert isinstance(data, dict)
        
        print(f"✓ /api/strategies/weather/forecasts: {len(data)} forecasts cached")

    def test_config_strategies_endpoint(self):
        """GET /api/config/strategies - includes weather_trader key"""
        r = requests.get(f"{BASE_URL}/api/config/strategies")
        assert r.status_code == 200
        data = r.json()
        
        assert "weather_trader" in data
        wt = data["weather_trader"]
        assert "enabled" in wt
        assert isinstance(wt["enabled"], bool)
        
        # Should have config fields
        assert "scan_interval" in wt
        assert "min_edge_bps" in wt
        assert "kelly_scale" in wt
        
        print(f"✓ /api/config/strategies includes weather_trader: enabled={wt['enabled']}")


class TestRegressionExistingEndpoints:
    """Regression tests for existing pages/endpoints (non-weather)"""
    
    def test_root_endpoint(self):
        """GET /api/ - root endpoint"""
        r = requests.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "online"
        print(f"✓ /api/: status=online, version={data.get('version')}")

    def test_status_endpoint(self):
        """GET /api/status - full status snapshot"""
        r = requests.get(f"{BASE_URL}/api/status")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "mode" in data
        print(f"✓ /api/status: status={data['status']}, mode={data['mode']}")

    def test_config_endpoint(self):
        """GET /api/config - full config"""
        r = requests.get(f"{BASE_URL}/api/config")
        assert r.status_code == 200
        data = r.json()
        assert "trading_mode" in data
        assert "strategies" in data
        assert "strategy_configs" in data
        
        # Verify weather_trader in strategy_configs
        assert "weather_trader" in data["strategy_configs"]
        
        print(f"✓ /api/config: mode={data['trading_mode']}, strategies={list(data['strategy_configs'].keys())}")

    def test_positions_endpoint(self):
        """GET /api/positions - returns positions list"""
        r = requests.get(f"{BASE_URL}/api/positions")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        print(f"✓ /api/positions: {len(data)} positions")

    def test_markets_endpoint(self):
        """GET /api/markets - returns markets list"""
        r = requests.get(f"{BASE_URL}/api/markets")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        print(f"✓ /api/markets: {len(data)} markets")

    def test_arb_opportunities_endpoint(self):
        """GET /api/strategies/arb/opportunities - arb scanner working"""
        r = requests.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert r.status_code == 200
        data = r.json()
        assert "tradable" in data
        assert "rejected" in data
        print(f"✓ /api/strategies/arb/opportunities: tradable={data['total_tradable']}, rejected={data['total_rejected']}")

    def test_arb_health_endpoint(self):
        """GET /api/strategies/arb/health - arb scanner health"""
        r = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert r.status_code == 200
        data = r.json()
        assert "total_scans" in data
        print(f"✓ /api/strategies/arb/health: scans={data['total_scans']}")

    def test_sniper_signals_endpoint(self):
        """GET /api/strategies/sniper/signals - crypto sniper working"""
        r = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert r.status_code == 200
        data = r.json()
        assert "tradable" in data
        assert "rejected" in data
        print(f"✓ /api/strategies/sniper/signals: tradable={data['total_tradable']}, rejected={data['total_rejected']}")

    def test_sniper_health_endpoint(self):
        """GET /api/strategies/sniper/health - sniper health"""
        r = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert r.status_code == 200
        data = r.json()
        assert "total_scans" in data
        print(f"✓ /api/strategies/sniper/health: scans={data['total_scans']}")

    def test_analytics_summary_endpoint(self):
        """GET /api/analytics/summary - analytics working"""
        r = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_pnl" in data
        print(f"✓ /api/analytics/summary: total_pnl={data['total_pnl']}")

    def test_feed_health_endpoint(self):
        """GET /api/health/feeds - feed health"""
        r = requests.get(f"{BASE_URL}/api/health/feeds")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        print(f"✓ /api/health/feeds: {len(data)} metrics")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
