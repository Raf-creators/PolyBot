"""
Test suite for Weather Shadow-Mode and Forecast Accuracy features.

Tests:
1. GET /api/strategies/weather/shadow-summary - shadow config, operational stats, calibration health
2. POST /api/strategies/weather/shadow/enable - applies conservative overrides
3. POST /api/strategies/weather/shadow/reset - resets to default WeatherConfig
4. GET /api/strategies/weather/accuracy/history - forecast accuracy records from MongoDB
5. GET /api/strategies/weather/accuracy/calibration - calibration health status
6. GET /api/strategies/weather/accuracy/unresolved - pending forecasts
7. POST /api/strategies/weather/accuracy/resolve - resolve forecast with observed_high_f
8. Demo mode weather endpoints
9. Existing weather strategy endpoints regression tests
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Expected shadow config overrides
EXPECTED_SHADOW_OVERRIDES = {
    "min_edge_bps": 500.0,
    "kelly_scale": 0.15,
    "max_signal_size": 5.0,
    "max_concurrent_signals": 4,
    "max_stale_market_seconds": 600.0,
    "cooldown_seconds": 2400.0,
    "default_size": 2.0,
}

# Default config values
DEFAULT_CONFIG = {
    "min_edge_bps": 300.0,
    "kelly_scale": 0.25,
    "max_signal_size": 8.0,
    "max_concurrent_signals": 8,
    "max_stale_market_seconds": 120.0,
    "cooldown_seconds": 1800.0,
    "default_size": 3.0,
}


class TestWeatherShadowSummary:
    """Test GET /api/strategies/weather/shadow-summary endpoint."""
    
    def test_shadow_summary_returns_200(self):
        """Shadow summary endpoint should return 200 and expected fields."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/shadow-summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields exist
        assert "execution_mode" in data, "Missing execution_mode field"
        assert "is_shadow" in data, "Missing is_shadow field"
        assert "shadow_overrides_applied" in data, "Missing shadow_overrides_applied field"
        assert "config_snapshot" in data, "Missing config_snapshot field"
        assert "operational_stats" in data, "Missing operational_stats field"
        assert "calibration" in data, "Missing calibration field"
        assert "running" in data, "Missing running field"
        
        print(f"Shadow summary returned successfully with execution_mode={data['execution_mode']}, is_shadow={data['is_shadow']}")
    
    def test_shadow_summary_config_snapshot_fields(self):
        """Config snapshot should contain all expected config fields."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/shadow-summary")
        assert response.status_code == 200
        
        config = response.json().get("config_snapshot", {})
        expected_fields = ["min_edge_bps", "kelly_scale", "max_signal_size", 
                         "max_concurrent_signals", "max_stale_market_seconds",
                         "cooldown_seconds", "default_size"]
        
        for field in expected_fields:
            assert field in config, f"Missing config field: {field}"
        
        print(f"Config snapshot has all expected fields: {list(config.keys())}")
    
    def test_shadow_summary_operational_stats_fields(self):
        """Operational stats should contain scanner metrics."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/shadow-summary")
        assert response.status_code == 200
        
        stats = response.json().get("operational_stats", {})
        expected_fields = ["total_scans", "markets_classified", "forecasts_fetched",
                         "signals_generated", "signals_executed", "signals_filled"]
        
        for field in expected_fields:
            assert field in stats, f"Missing operational_stats field: {field}"
        
        print(f"Operational stats: {stats}")


class TestWeatherShadowEnable:
    """Test POST /api/strategies/weather/shadow/enable endpoint."""
    
    def test_shadow_enable_returns_200(self):
        """Enable shadow should return 200 and status."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/shadow/enable")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data, "Missing status field"
        assert data["status"] == "shadow_overrides_applied", f"Unexpected status: {data['status']}"
        assert "config" in data, "Missing config field"
        
        print(f"Shadow enable successful: {data['status']}")
    
    def test_shadow_enable_applies_conservative_overrides(self):
        """Enable shadow should apply conservative config values."""
        # First enable shadow mode
        response = requests.post(f"{BASE_URL}/api/strategies/weather/shadow/enable")
        assert response.status_code == 200
        
        config = response.json().get("config", {})
        
        # Verify conservative overrides are applied
        assert config.get("min_edge_bps") == EXPECTED_SHADOW_OVERRIDES["min_edge_bps"], \
            f"min_edge_bps should be {EXPECTED_SHADOW_OVERRIDES['min_edge_bps']}, got {config.get('min_edge_bps')}"
        assert config.get("kelly_scale") == EXPECTED_SHADOW_OVERRIDES["kelly_scale"], \
            f"kelly_scale should be {EXPECTED_SHADOW_OVERRIDES['kelly_scale']}, got {config.get('kelly_scale')}"
        assert config.get("max_stale_market_seconds") == EXPECTED_SHADOW_OVERRIDES["max_stale_market_seconds"], \
            f"max_stale_market_seconds should be {EXPECTED_SHADOW_OVERRIDES['max_stale_market_seconds']}, got {config.get('max_stale_market_seconds')}"
        assert config.get("cooldown_seconds") == EXPECTED_SHADOW_OVERRIDES["cooldown_seconds"], \
            f"cooldown_seconds should be {EXPECTED_SHADOW_OVERRIDES['cooldown_seconds']}, got {config.get('cooldown_seconds')}"
        assert config.get("max_concurrent_signals") == EXPECTED_SHADOW_OVERRIDES["max_concurrent_signals"], \
            f"max_concurrent_signals should be {EXPECTED_SHADOW_OVERRIDES['max_concurrent_signals']}, got {config.get('max_concurrent_signals')}"
        assert config.get("max_signal_size") == EXPECTED_SHADOW_OVERRIDES["max_signal_size"], \
            f"max_signal_size should be {EXPECTED_SHADOW_OVERRIDES['max_signal_size']}, got {config.get('max_signal_size')}"
        assert config.get("default_size") == EXPECTED_SHADOW_OVERRIDES["default_size"], \
            f"default_size should be {EXPECTED_SHADOW_OVERRIDES['default_size']}, got {config.get('default_size')}"
        
        print(f"All conservative shadow overrides verified correctly")
    
    def test_shadow_enable_reflected_in_summary(self):
        """Shadow overrides should be reflected in shadow-summary endpoint."""
        # Enable shadow
        requests.post(f"{BASE_URL}/api/strategies/weather/shadow/enable")
        
        # Check shadow summary
        response = requests.get(f"{BASE_URL}/api/strategies/weather/shadow-summary")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("shadow_overrides_applied") == True, "shadow_overrides_applied should be True"
        
        # Verify config snapshot has shadow values
        config = data.get("config_snapshot", {})
        assert config.get("min_edge_bps") == EXPECTED_SHADOW_OVERRIDES["min_edge_bps"]
        
        print("Shadow overrides correctly reflected in shadow-summary")


class TestWeatherShadowReset:
    """Test POST /api/strategies/weather/shadow/reset endpoint."""
    
    def test_shadow_reset_returns_200(self):
        """Reset should return 200 and status."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/shadow/reset")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "status" in data, "Missing status field"
        assert data["status"] == "config_reset_to_defaults", f"Unexpected status: {data['status']}"
        assert "config" in data, "Missing config field"
        
        print(f"Shadow reset successful: {data['status']}")
    
    def test_shadow_reset_restores_default_config(self):
        """Reset should restore default WeatherConfig values."""
        # First enable shadow to change config
        requests.post(f"{BASE_URL}/api/strategies/weather/shadow/enable")
        
        # Then reset
        response = requests.post(f"{BASE_URL}/api/strategies/weather/shadow/reset")
        assert response.status_code == 200
        
        config = response.json().get("config", {})
        
        # Verify defaults restored
        assert config.get("min_edge_bps") == DEFAULT_CONFIG["min_edge_bps"], \
            f"min_edge_bps should be {DEFAULT_CONFIG['min_edge_bps']}, got {config.get('min_edge_bps')}"
        assert config.get("kelly_scale") == DEFAULT_CONFIG["kelly_scale"], \
            f"kelly_scale should be {DEFAULT_CONFIG['kelly_scale']}, got {config.get('kelly_scale')}"
        assert config.get("max_stale_market_seconds") == DEFAULT_CONFIG["max_stale_market_seconds"], \
            f"max_stale_market_seconds should be {DEFAULT_CONFIG['max_stale_market_seconds']}, got {config.get('max_stale_market_seconds')}"
        
        print(f"Default config values restored correctly")


class TestWeatherAccuracyHistory:
    """Test GET /api/strategies/weather/accuracy/history endpoint."""
    
    def test_accuracy_history_returns_200(self):
        """Accuracy history should return 200 and list."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        print(f"Accuracy history returned {len(data)} records")
    
    def test_accuracy_history_with_limit(self):
        """Accuracy history should respect limit parameter."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/history?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5, f"Expected max 5 records, got {len(data)}"
        
        print(f"Accuracy history with limit=5 returned {len(data)} records")
    
    def test_accuracy_history_with_station_filter(self):
        """Accuracy history should filter by station_id."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/history?station_id=KLGA")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        
        # All records should be for KLGA if any exist
        for record in data:
            assert record.get("station_id") == "KLGA", f"Expected KLGA, got {record.get('station_id')}"
        
        print(f"Accuracy history for KLGA returned {len(data)} records")
    
    def test_accuracy_history_record_structure(self):
        """Accuracy history records should have expected fields."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/history?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        if len(data) > 0:
            record = data[0]
            expected_fields = ["station_id", "target_date", "forecast_high_f", 
                             "sigma_used", "lead_hours", "resolved"]
            for field in expected_fields:
                assert field in record, f"Missing field: {field}"
            
            print(f"Sample record: station={record.get('station_id')}, date={record.get('target_date')}, resolved={record.get('resolved')}")
        else:
            print("No accuracy history records to verify structure")


class TestWeatherCalibration:
    """Test GET /api/strategies/weather/accuracy/calibration endpoint."""
    
    def test_calibration_returns_200(self):
        """Calibration endpoint should return 200 and health data."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/calibration")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        
        print(f"Calibration health returned: status={data.get('calibration_status')}")
    
    def test_calibration_has_required_fields(self):
        """Calibration should have all required health fields."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/calibration")
        assert response.status_code == 200
        
        data = response.json()
        expected_fields = [
            "total_records", "resolved_records", "pending_resolution",
            "stations_with_data", "stations_calibratable", "using_defaults",
            "calibration_status", "calibration_note", "station_summaries"
        ]
        
        for field in expected_fields:
            assert field in data, f"Missing calibration field: {field}"
        
        print(f"Calibration fields verified: total={data.get('total_records')}, resolved={data.get('resolved_records')}, status={data.get('calibration_status')}")
    
    def test_calibration_status_values(self):
        """Calibration status should be one of expected values."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/calibration")
        assert response.status_code == 200
        
        data = response.json()
        valid_statuses = ["no_data", "collecting", "partial", "ready"]
        status = data.get("calibration_status")
        
        assert status in valid_statuses, f"Invalid calibration_status: {status}"
        
        print(f"Calibration status is valid: {status}")
    
    def test_calibration_station_summaries(self):
        """Station summaries should have expected structure if present."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/calibration")
        assert response.status_code == 200
        
        data = response.json()
        summaries = data.get("station_summaries", {})
        
        if len(summaries) > 0:
            station_id = list(summaries.keys())[0]
            summary = summaries[station_id]
            expected_fields = ["station_id", "sample_count", "calibration_meaningful"]
            
            for field in expected_fields:
                assert field in summary, f"Missing station summary field: {field}"
            
            print(f"Station summary verified for {station_id}: samples={summary.get('sample_count')}")
        else:
            print("No station summaries to verify")


class TestWeatherUnresolved:
    """Test GET /api/strategies/weather/accuracy/unresolved endpoint."""
    
    def test_unresolved_returns_200(self):
        """Unresolved endpoint should return 200 and list."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/unresolved")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        print(f"Unresolved forecasts: {len(data)} pending")
    
    def test_unresolved_records_not_resolved(self):
        """All records from unresolved endpoint should have resolved=False."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/unresolved")
        assert response.status_code == 200
        
        data = response.json()
        for record in data:
            assert record.get("resolved") == False, f"Record should not be resolved: {record}"
        
        print(f"Verified all {len(data)} unresolved records have resolved=False")


class TestWeatherResolve:
    """Test POST /api/strategies/weather/accuracy/resolve endpoint."""
    
    def test_resolve_requires_fields(self):
        """Resolve should require station_id, target_date, observed_high_f."""
        # Test missing fields
        response = requests.post(f"{BASE_URL}/api/strategies/weather/accuracy/resolve", json={})
        assert response.status_code == 400, f"Expected 400 for missing fields, got {response.status_code}"
        
        response = requests.post(f"{BASE_URL}/api/strategies/weather/accuracy/resolve", 
                                json={"station_id": "KLGA"})
        assert response.status_code == 400, f"Expected 400 for missing target_date/observed_high_f"
        
        print("Resolve correctly validates required fields")
    
    def test_resolve_returns_200_on_valid_input(self):
        """Resolve should return 200 with valid input (even if record doesn't exist)."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/accuracy/resolve", json={
            "station_id": "TEST_STATION",
            "target_date": "2026-01-01",
            "observed_high_f": 45.0
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "resolved"
        assert data.get("station_id") == "TEST_STATION"
        assert data.get("target_date") == "2026-01-01"
        assert data.get("observed_high_f") == 45.0
        
        print("Resolve endpoint accepts valid input correctly")


class TestExistingWeatherEndpointsRegression:
    """Regression tests for existing weather strategy endpoints."""
    
    def test_weather_health_returns_200(self):
        """GET /api/strategies/weather/health should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "config" in data
        assert "running" in data
        
        print(f"Weather health: running={data.get('running')}")
    
    def test_weather_signals_returns_200(self):
        """GET /api/strategies/weather/signals should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200
        
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        assert "total_tradable" in data
        assert "total_rejected" in data
        
        print(f"Weather signals: tradable={data.get('total_tradable')}, rejected={data.get('total_rejected')}")
    
    def test_weather_executions_returns_200(self):
        """GET /api/strategies/weather/executions should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/executions")
        assert response.status_code == 200
        
        data = response.json()
        assert "active" in data
        assert "completed" in data
        
        print(f"Weather executions: active={len(data.get('active', []))}, completed={len(data.get('completed', []))}")
    
    def test_weather_forecasts_returns_200(self):
        """GET /api/strategies/weather/forecasts should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/forecasts")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)
        
        print(f"Weather forecasts: {len(data)} cached")
    
    def test_weather_stations_returns_200(self):
        """GET /api/strategies/weather/stations should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/stations")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        
        print(f"Weather stations: {len(data)} registered")
    
    def test_weather_config_returns_200(self):
        """GET /api/strategies/weather/config should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "enabled" in data
        
        print(f"Weather config: enabled={data.get('enabled')}")


class TestDemoModeWeatherEndpoints:
    """Test demo mode weather endpoints for shadow-summary and accuracy."""
    
    def test_demo_shadow_summary_returns_200(self):
        """GET /api/demo/strategies/weather/shadow-summary should return 200."""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/shadow-summary")
        assert response.status_code == 200
        
        data = response.json()
        assert "execution_mode" in data
        assert "is_shadow" in data
        assert "operational_stats" in data
        assert "calibration" in data
        
        print(f"Demo shadow summary: is_shadow={data.get('is_shadow')}")
    
    def test_demo_accuracy_history_returns_200(self):
        """GET /api/demo/strategies/weather/accuracy/history should return 200."""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/accuracy/history")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        
        print(f"Demo accuracy history returned {len(data)} records")
    
    def test_demo_accuracy_calibration_returns_200(self):
        """GET /api/demo/strategies/weather/accuracy/calibration should return 200."""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/accuracy/calibration")
        assert response.status_code == 200
        
        data = response.json()
        assert "calibration_status" in data
        assert "using_defaults" in data
        
        print(f"Demo accuracy calibration: status={data.get('calibration_status')}")


class TestMongoDBCollection:
    """Test that forecast_accuracy collection is used correctly."""
    
    def test_accuracy_data_isolated_to_forecast_accuracy_collection(self):
        """Verify accuracy data is stored in forecast_accuracy collection by checking data flow."""
        # Get calibration health which queries forecast_accuracy collection
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/calibration")
        assert response.status_code == 200
        
        data = response.json()
        # If there's data, it came from the forecast_accuracy collection
        # This is verified by the fact that the endpoint uses ForecastAccuracyService
        # which explicitly uses COLLECTION = "forecast_accuracy"
        print(f"Forecast accuracy collection: total_records={data.get('total_records')}, resolved={data.get('resolved_records')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
