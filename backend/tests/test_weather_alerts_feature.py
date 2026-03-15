"""
Weather Alert System Tests

Tests the new real-time weather signal alerting system for the WeatherTrader strategy.
Features tested:
- GET /api/strategies/weather/alerts endpoint
- Alert stats in weather health endpoint
- Alert config fields in weather config endpoint
- Config update persistence for alert settings
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')


class TestWeatherAlertsEndpoint:
    """Tests for GET /api/strategies/weather/alerts endpoint"""

    def test_alerts_endpoint_returns_200(self):
        """Verify alerts endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/alerts")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/strategies/weather/alerts returns 200")

    def test_alerts_response_shape(self):
        """Verify alerts endpoint returns correct shape: {alerts: [], stats: {...}}"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/alerts")
        assert response.status_code == 200
        data = response.json()
        
        # Check top-level keys
        assert "alerts" in data, "Response should have 'alerts' key"
        assert "stats" in data, "Response should have 'stats' key"
        assert isinstance(data["alerts"], list), "'alerts' should be a list"
        assert isinstance(data["stats"], dict), "'stats' should be a dict"
        print("PASS: alerts endpoint returns {alerts: [], stats: {...}} shape")

    def test_alerts_stats_fields(self):
        """Verify alert stats contains required fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/alerts")
        assert response.status_code == 200
        stats = response.json()["stats"]
        
        required_fields = [
            "total_generated", "total_debounced", "total_telegram_sent",
            "active_cooldowns", "alerts_buffered", "enabled"
        ]
        for field in required_fields:
            assert field in stats, f"Stats missing field: {field}"
        print(f"PASS: alert stats has all required fields: {required_fields}")


class TestWeatherHealthAlertStats:
    """Tests for alert_stats in GET /api/strategies/weather/health"""

    def test_health_includes_alert_stats(self):
        """Verify weather health endpoint includes alert_stats object"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        
        assert "alert_stats" in data, "Health should include 'alert_stats' object"
        assert isinstance(data["alert_stats"], dict), "'alert_stats' should be a dict"
        print("PASS: GET /api/strategies/weather/health includes alert_stats object")

    def test_health_alert_stats_has_enabled_field(self):
        """Verify alert_stats has 'enabled' field"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        alert_stats = response.json()["alert_stats"]
        
        assert "enabled" in alert_stats, "alert_stats should have 'enabled' field"
        assert isinstance(alert_stats["enabled"], bool), "'enabled' should be boolean"
        print("PASS: health alert_stats has 'enabled' field")


class TestWeatherConfigAlertFields:
    """Tests for alert config fields in GET /api/strategies/weather/config"""

    def test_config_includes_weather_alerts_enabled(self):
        """Verify weather config includes weather_alerts_enabled field"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert response.status_code == 200
        data = response.json()
        
        assert "weather_alerts_enabled" in data, "Config should have 'weather_alerts_enabled'"
        assert isinstance(data["weather_alerts_enabled"], bool), "weather_alerts_enabled should be bool"
        print("PASS: weather config includes weather_alerts_enabled field")

    def test_config_includes_min_weather_alert_edge_bps(self):
        """Verify weather config includes min_weather_alert_edge_bps field"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert response.status_code == 200
        data = response.json()
        
        assert "min_weather_alert_edge_bps" in data, "Config should have 'min_weather_alert_edge_bps'"
        assert isinstance(data["min_weather_alert_edge_bps"], (int, float)), "min_weather_alert_edge_bps should be numeric"
        print("PASS: weather config includes min_weather_alert_edge_bps field")

    def test_config_includes_min_weather_alert_price_move_bps(self):
        """Verify weather config includes min_weather_alert_price_move_bps field"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert response.status_code == 200
        data = response.json()
        
        assert "min_weather_alert_price_move_bps" in data, "Config should have 'min_weather_alert_price_move_bps'"
        assert isinstance(data["min_weather_alert_price_move_bps"], (int, float)), "min_weather_alert_price_move_bps should be numeric"
        print("PASS: weather config includes min_weather_alert_price_move_bps field")

    def test_config_includes_weather_alert_cooldown_seconds(self):
        """Verify weather config includes weather_alert_cooldown_seconds field"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert response.status_code == 200
        data = response.json()
        
        assert "weather_alert_cooldown_seconds" in data, "Config should have 'weather_alert_cooldown_seconds'"
        assert isinstance(data["weather_alert_cooldown_seconds"], (int, float)), "weather_alert_cooldown_seconds should be numeric"
        print("PASS: weather config includes weather_alert_cooldown_seconds field")

    def test_config_alert_fields_in_strategy_configs(self):
        """Verify alert fields present in /api/config endpoint strategy_configs.weather_trader"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        
        wt_config = data.get("strategy_configs", {}).get("weather_trader", {})
        required_alert_fields = [
            "weather_alerts_enabled", "min_weather_alert_edge_bps",
            "min_weather_alert_price_move_bps", "weather_alert_cooldown_seconds"
        ]
        for field in required_alert_fields:
            assert field in wt_config, f"/api/config strategy_configs.weather_trader missing {field}"
        print("PASS: /api/config strategy_configs.weather_trader has all alert fields")

    def test_config_alert_fields_in_strategies_endpoint(self):
        """Verify alert fields present in /api/config/strategies endpoint"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200
        data = response.json()
        
        wt_config = data.get("weather_trader", {})
        required_alert_fields = [
            "weather_alerts_enabled", "min_weather_alert_edge_bps",
            "min_weather_alert_price_move_bps", "weather_alert_cooldown_seconds"
        ]
        for field in required_alert_fields:
            assert field in wt_config, f"/api/config/strategies weather_trader missing {field}"
        print("PASS: /api/config/strategies weather_trader has all alert fields")


class TestConfigUpdateAlertSettings:
    """Tests for POST /api/config/update with alert settings"""

    def test_disable_weather_alerts(self):
        """Test disabling weather_alerts_enabled via config update"""
        # First get current state
        orig = requests.get(f"{BASE_URL}/api/strategies/weather/config").json()
        orig_enabled = orig.get("weather_alerts_enabled", True)
        
        # Disable alerts
        response = requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"weather_trader": {"weather_alerts_enabled": False}}}
        )
        assert response.status_code == 200
        assert response.json().get("persisted") == True, "Config should be persisted"
        
        # Verify change persisted
        verify = requests.get(f"{BASE_URL}/api/strategies/weather/config").json()
        assert verify["weather_alerts_enabled"] == False, "weather_alerts_enabled should be False"
        
        # Verify alert_stats in alerts endpoint reflects disabled state
        alerts_resp = requests.get(f"{BASE_URL}/api/strategies/weather/alerts").json()
        assert alerts_resp["stats"]["enabled"] == False, "alerts stats.enabled should be False"
        
        # Restore original state
        requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"weather_trader": {"weather_alerts_enabled": orig_enabled}}}
        )
        print("PASS: POST /api/config/update with weather_alerts_enabled=false disables alerts and persists")

    def test_update_min_weather_alert_edge_bps(self):
        """Test updating min_weather_alert_edge_bps via config update"""
        # Get original value
        orig = requests.get(f"{BASE_URL}/api/strategies/weather/config").json()
        orig_value = orig.get("min_weather_alert_edge_bps", 200)
        
        # Update to new value
        new_value = 500
        response = requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"weather_trader": {"min_weather_alert_edge_bps": new_value}}}
        )
        assert response.status_code == 200
        assert response.json().get("persisted") == True
        
        # Verify change persisted
        verify = requests.get(f"{BASE_URL}/api/strategies/weather/config").json()
        assert verify["min_weather_alert_edge_bps"] == new_value, f"min_weather_alert_edge_bps should be {new_value}"
        
        # Restore original value
        requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"weather_trader": {"min_weather_alert_edge_bps": orig_value}}}
        )
        print("PASS: POST /api/config/update with min_weather_alert_edge_bps=500 updates the value")


class TestExistingWeatherEndpointsRegression:
    """Regression tests to ensure existing weather endpoints still work"""

    def test_weather_signals_endpoint(self):
        """Verify GET /api/strategies/weather/signals still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        print("PASS: GET /api/strategies/weather/signals still works")

    def test_weather_executions_endpoint(self):
        """Verify GET /api/strategies/weather/executions still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/executions")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "completed" in data
        print("PASS: GET /api/strategies/weather/executions still works")

    def test_weather_health_endpoint(self):
        """Verify GET /api/strategies/weather/health still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        # Check existing fields are still present
        assert "running" in data
        assert "config" in data
        print("PASS: GET /api/strategies/weather/health still works")

    def test_weather_forecasts_endpoint(self):
        """Verify GET /api/strategies/weather/forecasts still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/forecasts")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/weather/forecasts still works")

    def test_weather_config_endpoint(self):
        """Verify GET /api/strategies/weather/config still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "min_edge_bps" in data
        print("PASS: GET /api/strategies/weather/config still works")


class TestOtherPagesNoRegression:
    """Regression tests for other pages to ensure no regressions"""

    def test_overview_positions(self):
        """Verify GET /api/positions still works"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        print("PASS: GET /api/positions works (Overview page)")

    def test_arbitrage_opportunities(self):
        """Verify GET /api/strategies/arb/opportunities still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/arb/opportunities works (Arbitrage page)")

    def test_sniper_signals(self):
        """Verify GET /api/strategies/sniper/signals still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/sniper/signals works (Sniper page)")

    def test_settings_config(self):
        """Verify GET /api/config still works"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "trading_mode" in data
        assert "strategies" in data
        print("PASS: GET /api/config works (Settings page)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
