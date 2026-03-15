"""
Test suite for Historical Calibration Bootstrap (P1) feature.

Tests:
1. POST /api/strategies/weather/calibration/run - runs calibration for stations
2. GET /api/strategies/weather/calibration/status - returns calibration status
3. GET /api/strategies/weather/calibration/{station_id} - returns specific station calibration
4. POST /api/strategies/weather/calibration/reload - reloads calibrations into WeatherTrader
5. Weather health shows calibration_status with using_defaults=false after calibration
6. Existing weather endpoints still work (regression)
7. Shadow mode / accuracy endpoints still work (regression)
8. Demo mode endpoints still work (regression)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCalibrationRunEndpoint:
    """POST /api/strategies/weather/calibration/run - runs calibration for specified stations"""

    def test_run_calibration_single_station(self):
        """Test running calibration for a single station (KLGA)"""
        response = requests.post(
            f"{BASE_URL}/api/strategies/weather/calibration/run",
            json={"station_ids": ["KLGA"], "lookback_days": 90}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify status
        assert data.get("status") == "completed"
        assert data.get("stations_processed") == 1
        
        # Verify KLGA result
        results = data.get("results", {})
        assert "KLGA" in results
        klga = results["KLGA"]
        assert klga.get("status") == "calibrated"
        assert klga.get("sample_count", 0) >= 80  # Should have ~91 samples
        assert "base_sigma_f" in klga
        assert "mean_bias_f" in klga
        assert "sigma_by_lead" in klga
        print(f"KLGA calibration: samples={klga['sample_count']}, base_sigma={klga['base_sigma_f']}, bias={klga['mean_bias_f']}")

    def test_run_calibration_returns_sigma_by_lead(self):
        """Test that sigma_by_lead contains all lead brackets"""
        response = requests.post(
            f"{BASE_URL}/api/strategies/weather/calibration/run",
            json={"station_ids": ["KORD"], "lookback_days": 90}
        )
        assert response.status_code == 200
        data = response.json()
        
        results = data.get("results", {})
        assert "KORD" in results
        sigma_by_lead = results["KORD"].get("sigma_by_lead", {})
        
        # Verify all lead brackets present
        expected_brackets = ["0_24", "24_48", "48_72", "72_120", "120_168"]
        for bracket in expected_brackets:
            assert bracket in sigma_by_lead, f"Missing bracket {bracket}"
            assert isinstance(sigma_by_lead[bracket], (int, float))
            assert sigma_by_lead[bracket] > 0
        print(f"KORD sigma_by_lead: {sigma_by_lead}")

    def test_run_calibration_unknown_station(self):
        """Test that unknown station_id returns error"""
        response = requests.post(
            f"{BASE_URL}/api/strategies/weather/calibration/run",
            json={"station_ids": ["UNKNOWN"]}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should still complete but with errors
        assert data.get("status") == "completed"
        assert len(data.get("errors", [])) > 0
        assert "UNKNOWN" in str(data.get("errors", []))


class TestCalibrationStatusEndpoint:
    """GET /api/strategies/weather/calibration/status - returns total calibrated, last run info"""

    def test_calibration_status_structure(self):
        """Test calibration status returns required fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/status")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "total_stations_calibrated" in data
        assert "total_stations_registered" in data
        assert "last_run" in data
        assert "last_status" in data
        assert "stations" in data
        
        assert data["total_stations_calibrated"] >= 5
        assert data["total_stations_registered"] >= 5
        assert data["last_status"] == "completed"
        print(f"Calibration status: {data['total_stations_calibrated']}/{data['total_stations_registered']} stations calibrated")

    def test_calibration_status_station_details(self):
        """Test that station details are returned correctly"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/status")
        assert response.status_code == 200
        data = response.json()
        
        stations = data.get("stations", {})
        assert len(stations) >= 5
        
        # Verify station structure
        for station_id, info in stations.items():
            assert "station_id" in info
            assert "sample_count" in info
            assert "calibrated_at" in info
            assert "base_sigma_0_24" in info
            assert "base_sigma_48_72" in info
            assert "mean_bias_f" in info
            assert "ready" in info
            assert info["sample_count"] >= 30  # Should have adequate samples
            assert info["ready"] == True  # All calibrated stations should be ready
        print(f"Station details verified for: {list(stations.keys())}")


class TestStationCalibrationEndpoint:
    """GET /api/strategies/weather/calibration/{station_id} - returns specific station calibration"""

    def test_get_klga_calibration(self):
        """Test getting KLGA calibration data"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/KLGA")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert data.get("station_id") == "KLGA"
        assert "calibrated_at" in data
        assert "sample_count" in data
        assert "sigma_by_lead_hours" in data
        assert "seasonal_factors" in data
        assert "station_type_factor" in data
        assert "mean_bias_f" in data
        
        # Verify sigma_by_lead_hours
        sigma = data["sigma_by_lead_hours"]
        assert "0_24" in sigma
        assert "24_48" in sigma
        assert "48_72" in sigma
        assert "72_120" in sigma
        assert "120_168" in sigma
        
        # Verify seasonal_factors
        seasons = data["seasonal_factors"]
        assert "winter" in seasons
        assert "spring" in seasons
        assert "summer" in seasons
        assert "fall" in seasons
        
        print(f"KLGA: sample_count={data['sample_count']}, sigma_0_24={sigma['0_24']}, bias={data['mean_bias_f']}")

    def test_get_nonexistent_station_calibration(self):
        """Test getting calibration for non-existent station returns 404"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/NONEXISTENT")
        assert response.status_code == 404

    def test_get_multiple_stations_calibration(self):
        """Test getting calibration for multiple stations"""
        stations = ["KLGA", "KORD", "KATL", "KDFW", "KMIA"]
        for station_id in stations:
            response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/{station_id}")
            assert response.status_code == 200
            data = response.json()
            assert data.get("station_id") == station_id
            assert data.get("sample_count", 0) >= 80
        print(f"Successfully retrieved calibration for all {len(stations)} stations")


class TestCalibrationReloadEndpoint:
    """POST /api/strategies/weather/calibration/reload - reloads calibrations into WeatherTrader"""

    def test_reload_calibrations(self):
        """Test reloading calibrations from MongoDB"""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/calibration/reload")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "reloaded"
        assert "calibrations_loaded" in data
        assert "stations" in data
        assert data["calibrations_loaded"] >= 5
        assert len(data["stations"]) >= 5
        print(f"Reloaded {data['calibrations_loaded']} calibrations: {data['stations']}")


class TestWeatherHealthCalibrationStatus:
    """After calibration, weather health shows using_defaults=false"""

    def test_weather_health_calibration_status(self):
        """Test that weather health shows calibrated status"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        
        cal_status = data.get("calibration_status", {})
        assert "using_defaults" in cal_status
        assert "calibrated_stations" in cal_status
        assert "calibration_source" in cal_status
        
        # After calibration, using_defaults should be False
        assert cal_status["using_defaults"] == False
        assert cal_status["calibration_source"] == "historical_calibration"
        assert len(cal_status["calibrated_stations"]) >= 5
        print(f"Weather health calibration_status: using_defaults={cal_status['using_defaults']}, source={cal_status['calibration_source']}")


class TestRegressionExistingWeatherEndpoints:
    """Verify existing weather endpoints still work"""

    def test_weather_signals(self):
        """GET /api/strategies/weather/signals still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        assert "total_tradable" in data
        assert "total_rejected" in data

    def test_weather_executions(self):
        """GET /api/strategies/weather/executions still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/executions")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "completed" in data

    def test_weather_forecasts(self):
        """GET /api/strategies/weather/forecasts still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/forecasts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_weather_stations(self):
        """GET /api/strategies/weather/stations still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/stations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_weather_config(self):
        """GET /api/strategies/weather/config still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "min_edge_bps" in data


class TestRegressionShadowModeEndpoints:
    """Verify shadow mode / accuracy endpoints still work"""

    def test_shadow_summary(self):
        """GET /api/strategies/weather/shadow-summary still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/shadow-summary")
        assert response.status_code == 200
        data = response.json()
        assert "execution_mode" in data
        assert "is_shadow" in data
        assert "config_snapshot" in data
        assert "operational_stats" in data

    def test_accuracy_history(self):
        """GET /api/strategies/weather/accuracy/history still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_accuracy_calibration(self):
        """GET /api/strategies/weather/accuracy/calibration still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/calibration")
        assert response.status_code == 200
        data = response.json()
        assert "total_records" in data
        assert "calibration_status" in data

    def test_accuracy_unresolved(self):
        """GET /api/strategies/weather/accuracy/unresolved still works"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/unresolved")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestRegressionDemoModeEndpoints:
    """Verify demo mode endpoints still work"""

    def test_demo_weather_signals(self):
        """GET /api/demo/strategies/weather/signals still works"""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/signals")
        assert response.status_code == 200

    def test_demo_weather_health(self):
        """GET /api/demo/strategies/weather/health still works"""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/health")
        assert response.status_code == 200

    def test_demo_weather_shadow_summary(self):
        """GET /api/demo/strategies/weather/shadow-summary still works"""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/shadow-summary")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
