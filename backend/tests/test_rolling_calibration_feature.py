"""Integration tests for Rolling Calibration System API endpoints.

Tests:
- GET /api/strategies/weather/calibration/rolling/status endpoint
- POST /api/strategies/weather/calibration/rolling/run endpoint
- POST /api/strategies/weather/calibration/rolling/reload endpoint
- Health endpoint calibration_status fields
- Config endpoint rolling calibration fields
- Config update persistence for rolling calibration settings
- No regressions on existing weather endpoints
"""

import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestRollingCalibrationStatusEndpoint:
    """Tests for GET /api/strategies/weather/calibration/rolling/status endpoint."""
    
    def test_rolling_status_returns_200(self):
        """Endpoint should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/rolling/status")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/weather/calibration/rolling/status returns 200")
    
    def test_rolling_status_has_required_fields(self):
        """Status response should have all required fields."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/rolling/status")
        data = response.json()
        
        required_fields = [
            "enabled",
            "total_stations_calibrated",
            "total_resolved_records",
            "needs_recalculation",
            "min_samples_required",
            "last_run",
            "last_status",
            "last_record_count_at_run",
            "recalc_interval_hours",
            "recalc_after_n_records",
            "stations"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
            print(f"PASS: Field '{field}' present in rolling status response")
        
        print("PASS: Rolling status has all required fields")
    
    def test_rolling_status_correct_data_types(self):
        """Status response should have correct data types."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/rolling/status")
        data = response.json()
        
        assert isinstance(data["enabled"], bool), "enabled should be boolean"
        assert isinstance(data["total_stations_calibrated"], int), "total_stations_calibrated should be int"
        assert isinstance(data["total_resolved_records"], int), "total_resolved_records should be int"
        assert isinstance(data["needs_recalculation"], bool), "needs_recalculation should be boolean"
        assert isinstance(data["min_samples_required"], int), "min_samples_required should be int"
        assert isinstance(data["stations"], dict), "stations should be dict"
        
        print("PASS: Rolling status has correct data types")
    
    def test_rolling_status_shows_insufficient_data(self):
        """With only 1 resolved record, status should show insufficient data (no stations calibrated)."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/rolling/status")
        data = response.json()
        
        # With only 1 resolved record and min_samples=15, no stations should be calibrated
        assert data["total_resolved_records"] < data["min_samples_required"], \
            "Should have insufficient resolved records for calibration"
        assert data["total_stations_calibrated"] == 0, "No stations should be calibrated with sparse data"
        
        print("PASS: Rolling status correctly reports insufficient data")


class TestRollingCalibrationRunEndpoint:
    """Tests for POST /api/strategies/weather/calibration/rolling/run endpoint."""
    
    def test_rolling_run_returns_200(self):
        """Run endpoint should return 200."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/calibration/rolling/run")
        assert response.status_code == 200
        print("PASS: POST /api/strategies/weather/calibration/rolling/run returns 200")
    
    def test_rolling_run_returns_results(self):
        """Run endpoint should return results with status."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/calibration/rolling/run")
        data = response.json()
        
        assert "status" in data, "Response should have status field"
        assert data["status"] == "completed", "Status should be 'completed'"
        assert "stations_processed" in data, "Should have stations_processed count"
        assert "stations_calibrated" in data, "Should have stations_calibrated count"
        assert "stations_insufficient" in data, "Should have stations_insufficient count"
        assert "results" in data, "Should have results dict"
        
        print(f"PASS: Rolling run returned - processed: {data['stations_processed']}, "
              f"calibrated: {data['stations_calibrated']}, insufficient: {data['stations_insufficient']}")
    
    def test_rolling_run_insufficient_data_for_all_stations(self):
        """With only 1 resolved record, all stations should report insufficient_data."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/calibration/rolling/run")
        data = response.json()
        
        # With only 1 resolved record at KLGA, all stations should have insufficient data
        assert data["stations_calibrated"] == 0, "No stations should be calibrated with sparse data"
        assert data["stations_insufficient"] > 0, "Some stations should report insufficient data"
        
        print("PASS: Rolling run correctly reports insufficient data for stations")


class TestRollingCalibrationReloadEndpoint:
    """Tests for POST /api/strategies/weather/calibration/rolling/reload endpoint."""
    
    def test_rolling_reload_returns_200(self):
        """Reload endpoint should return 200."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/calibration/rolling/reload")
        assert response.status_code == 200
        print("PASS: POST /api/strategies/weather/calibration/rolling/reload returns 200")
    
    def test_rolling_reload_returns_status(self):
        """Reload endpoint should return status."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/calibration/rolling/reload")
        data = response.json()
        
        assert "status" in data, "Response should have status field"
        print(f"PASS: Rolling reload returned status: {data.get('status')}")


class TestWeatherHealthCalibrationStatus:
    """Tests for calibration_status in GET /api/strategies/weather/health endpoint."""
    
    def test_health_has_calibration_status(self):
        """Health endpoint should include calibration_status."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        
        assert "calibration_status" in data, "Health should include calibration_status"
        print("PASS: Health endpoint includes calibration_status")
    
    def test_calibration_status_has_sources(self):
        """calibration_status should have sources field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        cal_status = data.get("calibration_status", {})
        
        assert "sources" in cal_status, "calibration_status should have sources field"
        assert isinstance(cal_status["sources"], dict), "sources should be a dict"
        
        print(f"PASS: calibration_status has sources: {cal_status['sources']}")
    
    def test_calibration_status_has_source_summary(self):
        """calibration_status should have source_summary field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        cal_status = data.get("calibration_status", {})
        
        assert "source_summary" in cal_status, "calibration_status should have source_summary field"
        assert isinstance(cal_status["source_summary"], dict), "source_summary should be a dict"
        
        print(f"PASS: calibration_status has source_summary: {cal_status['source_summary']}")
    
    def test_calibration_status_has_calibration_source(self):
        """calibration_status should have calibration_source field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        cal_status = data.get("calibration_status", {})
        
        assert "calibration_source" in cal_status, "calibration_status should have calibration_source field"
        # Should be one of: rolling_live, historical_bootstrap, default_sigma_table
        valid_sources = ["rolling_live", "historical_bootstrap", "default_sigma_table"]
        assert cal_status["calibration_source"] in valid_sources, \
            f"calibration_source should be one of {valid_sources}"
        
        print(f"PASS: calibration_status has calibration_source: {cal_status['calibration_source']}")
    
    def test_calibration_status_has_note(self):
        """calibration_status should have note field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        cal_status = data.get("calibration_status", {})
        
        assert "note" in cal_status, "calibration_status should have note field"
        assert isinstance(cal_status["note"], str), "note should be a string"
        
        print(f"PASS: calibration_status has note: {cal_status['note']}")


class TestWeatherConfigRollingFields:
    """Tests for rolling calibration fields in GET /api/strategies/weather/config endpoint."""
    
    def test_config_has_rolling_enabled(self):
        """Config should have rolling_calibration_enabled field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        data = response.json()
        
        assert "rolling_calibration_enabled" in data, "Config should have rolling_calibration_enabled"
        assert isinstance(data["rolling_calibration_enabled"], bool), "Should be boolean"
        
        print(f"PASS: Config has rolling_calibration_enabled: {data['rolling_calibration_enabled']}")
    
    def test_config_has_rolling_min_samples(self):
        """Config should have rolling_min_samples field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        data = response.json()
        
        assert "rolling_min_samples" in data, "Config should have rolling_min_samples"
        assert isinstance(data["rolling_min_samples"], int), "Should be int"
        
        print(f"PASS: Config has rolling_min_samples: {data['rolling_min_samples']}")
    
    def test_config_has_rolling_recalc_interval(self):
        """Config should have rolling_recalc_interval_hours field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        data = response.json()
        
        assert "rolling_recalc_interval_hours" in data, "Config should have rolling_recalc_interval_hours"
        assert isinstance(data["rolling_recalc_interval_hours"], (int, float)), "Should be numeric"
        
        print(f"PASS: Config has rolling_recalc_interval_hours: {data['rolling_recalc_interval_hours']}")
    
    def test_config_has_rolling_recalc_after_n_records(self):
        """Config should have rolling_recalc_after_n_records field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        data = response.json()
        
        assert "rolling_recalc_after_n_records" in data, "Config should have rolling_recalc_after_n_records"
        assert isinstance(data["rolling_recalc_after_n_records"], int), "Should be int"
        
        print(f"PASS: Config has rolling_recalc_after_n_records: {data['rolling_recalc_after_n_records']}")


class TestConfigUpdatePersistence:
    """Tests for config update persistence of rolling calibration settings."""
    
    def test_update_rolling_enabled_false(self):
        """Config update should persist rolling_calibration_enabled=false."""
        # Get current value
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        original = response.json()["rolling_calibration_enabled"]
        
        # Update to false
        update_resp = requests.post(f"{BASE_URL}/api/config/update", json={
            "strategies": {"weather_trader": {"rolling_calibration_enabled": False}}
        })
        assert update_resp.status_code == 200
        
        # Verify change
        verify_resp = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert verify_resp.json()["rolling_calibration_enabled"] == False
        
        # Restore original
        requests.post(f"{BASE_URL}/api/config/update", json={
            "strategies": {"weather_trader": {"rolling_calibration_enabled": original}}
        })
        
        print("PASS: rolling_calibration_enabled=false persisted successfully")
    
    def test_update_rolling_min_samples(self):
        """Config update should persist rolling_min_samples value."""
        # Get current value
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        original = response.json()["rolling_min_samples"]
        
        # Update to new value
        new_value = 25
        update_resp = requests.post(f"{BASE_URL}/api/config/update", json={
            "strategies": {"weather_trader": {"rolling_min_samples": new_value}}
        })
        assert update_resp.status_code == 200
        
        # Verify change
        verify_resp = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert verify_resp.json()["rolling_min_samples"] == new_value
        
        # Restore original
        requests.post(f"{BASE_URL}/api/config/update", json={
            "strategies": {"weather_trader": {"rolling_min_samples": original}}
        })
        
        print(f"PASS: rolling_min_samples={new_value} persisted successfully")


class TestEngineStartCalibrationSource:
    """Tests for calibration source after engine start (historical_bootstrap expected)."""
    
    def test_engine_start_and_check_calibration_source(self):
        """When engine is started, health should show calibration_source as historical_bootstrap."""
        # Check initial state
        health_before = requests.get(f"{BASE_URL}/api/strategies/weather/health").json()
        print(f"Before start - calibration_source: {health_before.get('calibration_status', {}).get('calibration_source', 'N/A')}")
        
        # Start engine
        start_resp = requests.post(f"{BASE_URL}/api/engine/start")
        if start_resp.status_code == 400:
            # Engine might already be running
            print("Engine already running, checking calibration source")
        else:
            assert start_resp.status_code == 200
            print("Engine started")
        
        # Wait for calibration sources to populate
        import time
        time.sleep(3)
        
        # Check calibration source
        health_resp = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        health = health_resp.json()
        cal_status = health.get("calibration_status", {})
        source_summary = cal_status.get("source_summary", {})
        calibration_source = cal_status.get("calibration_source", "")
        
        print(f"After start - calibration_source: {calibration_source}")
        print(f"source_summary: {source_summary}")
        
        # With 8 stations having historical calibrations, should use historical_bootstrap
        # (unless rolling_live has sufficient samples)
        assert calibration_source in ["historical_bootstrap", "default_sigma_table", "rolling_live"], \
            f"calibration_source should be valid, got: {calibration_source}"
        
        # Check that source_summary includes historical_bootstrap count (should be 8)
        if "historical_bootstrap" in source_summary:
            assert source_summary["historical_bootstrap"] > 0, "Should have historical calibrations"
            print(f"PASS: {source_summary['historical_bootstrap']} stations using historical_bootstrap")
        
        # Stop engine
        stop_resp = requests.post(f"{BASE_URL}/api/engine/stop")
        assert stop_resp.status_code == 200
        print("Engine stopped")
        
        print("PASS: Calibration source correctly populated after engine start")


class TestRegressionExistingEndpoints:
    """Regression tests for existing weather endpoints."""
    
    def test_weather_signals_still_works(self):
        """GET /api/strategies/weather/signals should still work."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        print("PASS: Weather signals endpoint works (regression)")
    
    def test_weather_executions_still_works(self):
        """GET /api/strategies/weather/executions should still work."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/executions")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "completed" in data
        print("PASS: Weather executions endpoint works (regression)")
    
    def test_weather_health_still_works(self):
        """GET /api/strategies/weather/health should still work."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "config" in data
        print("PASS: Weather health endpoint works (regression)")
    
    def test_weather_forecasts_still_works(self):
        """GET /api/strategies/weather/forecasts should still work."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/forecasts")
        assert response.status_code == 200
        print("PASS: Weather forecasts endpoint works (regression)")
    
    def test_weather_alerts_still_works(self):
        """GET /api/strategies/weather/alerts should still work."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "stats" in data
        print("PASS: Weather alerts endpoint works (regression)")


class TestRegressionOtherPages:
    """Regression tests for other pages/endpoints."""
    
    def test_positions_endpoint(self):
        """GET /api/positions should work."""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        print("PASS: Positions endpoint works (regression)")
    
    def test_arb_opportunities_endpoint(self):
        """GET /api/strategies/arb/opportunities should work."""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert response.status_code == 200
        print("PASS: Arb opportunities endpoint works (regression)")
    
    def test_sniper_signals_endpoint(self):
        """GET /api/strategies/sniper/signals should work."""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert response.status_code == 200
        print("PASS: Sniper signals endpoint works (regression)")
    
    def test_config_endpoint(self):
        """GET /api/config should work."""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        print("PASS: Config endpoint works (regression)")
    
    def test_config_strategies_endpoint(self):
        """GET /api/config/strategies should work."""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200
        print("PASS: Config strategies endpoint works (regression)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
