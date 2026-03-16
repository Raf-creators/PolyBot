"""
Auto-Resolver Service Backend API Tests

Tests for the automated forecast resolution service endpoints:
- GET /api/health/auto-resolver - Health and status
- POST /api/auto-resolver/run - Manual trigger
- GET /api/strategies/weather/health - Weather health includes auto_resolver
- GET /api/analytics/global - Global analytics includes auto_resolver health & forecast_quality

Features verified:
- auto_resolver health object fields: running, interval_hours, total_runs, pending_records, etc.
- Manual trigger returns {resolved, pending, skipped, errors}
- forecast_quality shows: global_mae_f (~1.7F), resolved_forecasts (10), 5 stations
- error_distribution has multiple bins
- Regression tests for existing endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://edge-trading-hub-1.preview.emergentagent.com"


class TestAutoResolverHealth:
    """Tests for GET /api/health/auto-resolver endpoint"""
    
    def test_auto_resolver_health_returns_200(self):
        """Auto-resolver health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/health/auto-resolver")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/health/auto-resolver returns 200")
    
    def test_auto_resolver_health_has_required_fields(self):
        """Health response has all required fields"""
        response = requests.get(f"{BASE_URL}/api/health/auto-resolver")
        data = response.json()
        
        required_fields = [
            "running", "interval_hours", "total_runs", "total_resolved",
            "total_skipped", "total_errors", "last_run_at", "last_run_resolved",
            "last_run_pending", "last_run_duration_s", "last_error", "pending_records"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"PASS: Health response has all {len(required_fields)} required fields")
    
    def test_auto_resolver_is_running(self):
        """Auto-resolver shows running=true"""
        response = requests.get(f"{BASE_URL}/api/health/auto-resolver")
        data = response.json()
        
        assert data["running"] == True, f"Expected running=True, got {data['running']}"
        print("PASS: Auto-resolver running=true")
    
    def test_auto_resolver_interval_hours(self):
        """Auto-resolver interval is configurable (default 6h)"""
        response = requests.get(f"{BASE_URL}/api/health/auto-resolver")
        data = response.json()
        
        assert data["interval_hours"] == 6, f"Expected interval_hours=6, got {data['interval_hours']}"
        print("PASS: Auto-resolver interval_hours=6")


class TestAutoResolverManualTrigger:
    """Tests for POST /api/auto-resolver/run endpoint"""
    
    def test_manual_trigger_returns_200(self):
        """Manual trigger endpoint returns 200"""
        response = requests.post(f"{BASE_URL}/api/auto-resolver/run")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: POST /api/auto-resolver/run returns 200")
    
    def test_manual_trigger_response_format(self):
        """Manual trigger returns {resolved, pending, skipped, errors}"""
        response = requests.post(f"{BASE_URL}/api/auto-resolver/run")
        data = response.json()
        
        required_fields = ["resolved", "pending", "skipped", "errors"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], int), f"Field {field} should be int, got {type(data[field])}"
        
        print(f"PASS: Manual trigger response has correct format: {data}")
    
    def test_manual_trigger_idempotent(self):
        """Repeated manual triggers are safe (idempotent)"""
        # First call
        response1 = requests.post(f"{BASE_URL}/api/auto-resolver/run")
        data1 = response1.json()
        
        # Second call
        response2 = requests.post(f"{BASE_URL}/api/auto-resolver/run")
        data2 = response2.json()
        
        # Both should succeed and return same result (no pending records to resolve)
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert data1 == data2, "Idempotent calls should return same result"
        
        print(f"PASS: Manual trigger is idempotent: {data1}")
    
    def test_no_pending_returns_zeros(self):
        """With no pending records, returns resolved=0 pending=0"""
        response = requests.post(f"{BASE_URL}/api/auto-resolver/run")
        data = response.json()
        
        # Since all resolvable records were already resolved, should return zeros
        assert data["resolved"] == 0, f"Expected resolved=0, got {data['resolved']}"
        assert data["pending"] == 0, f"Expected pending=0 (all resolved), got {data['pending']}"
        
        print(f"PASS: No pending records: resolved={data['resolved']}, pending={data['pending']}")


class TestWeatherHealthWithAutoResolver:
    """Tests for GET /api/strategies/weather/health including auto_resolver"""
    
    def test_weather_health_returns_200(self):
        """Weather health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/weather/health returns 200")
    
    def test_weather_health_includes_auto_resolver(self):
        """Weather health includes auto_resolver object"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        
        assert "auto_resolver" in data, "Weather health missing auto_resolver field"
        
        auto_resolver = data["auto_resolver"]
        assert "running" in auto_resolver
        assert "interval_hours" in auto_resolver
        assert "total_runs" in auto_resolver
        
        print(f"PASS: Weather health includes auto_resolver: running={auto_resolver['running']}, interval={auto_resolver['interval_hours']}h")


class TestGlobalAnalyticsWithAutoResolver:
    """Tests for GET /api/analytics/global including auto_resolver health and forecast_quality"""
    
    def test_global_analytics_returns_200(self):
        """Global analytics endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        assert response.status_code == 200
        print("PASS: GET /api/analytics/global returns 200")
    
    def test_global_analytics_includes_auto_resolver(self):
        """Global analytics includes auto_resolver health"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        data = response.json()
        
        assert "auto_resolver" in data, "Global analytics missing auto_resolver"
        
        auto_resolver = data["auto_resolver"]
        assert auto_resolver["running"] == True
        assert auto_resolver["interval_hours"] == 6
        
        print(f"PASS: Global analytics includes auto_resolver: {auto_resolver['running']}")
    
    def test_forecast_quality_resolved_forecasts(self):
        """Forecast quality shows resolved_forecasts=10 (9 auto-resolved + 1 previous)"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        data = response.json()
        
        forecast = data.get("forecast_quality", {})
        resolved = forecast.get("resolved_forecasts", 0)
        
        # Should have 10 resolved (9 auto-resolved + 1 previously resolved for KLGA)
        assert resolved == 10, f"Expected resolved_forecasts=10, got {resolved}"
        
        print(f"PASS: forecast_quality.resolved_forecasts={resolved}")
    
    def test_forecast_quality_five_stations(self):
        """Forecast quality shows data for 5 stations: KATL, KDFW, KLGA, KMIA, KORD"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        data = response.json()
        
        forecast = data.get("forecast_quality", {})
        station_metrics = forecast.get("station_metrics", {})
        
        expected_stations = {"KATL", "KDFW", "KLGA", "KMIA", "KORD"}
        actual_stations = set(station_metrics.keys())
        
        assert expected_stations == actual_stations, f"Expected stations {expected_stations}, got {actual_stations}"
        
        print(f"PASS: forecast_quality has 5 stations: {list(actual_stations)}")
    
    def test_forecast_quality_improved_mae(self):
        """Forecast quality shows improved global_mae_f (~1.7F, was 4.3F)"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        data = response.json()
        
        forecast = data.get("forecast_quality", {})
        mae = forecast.get("global_mae_f")
        
        # MAE should be around 1.7F (improved from 4.3F)
        assert mae is not None, "global_mae_f is None"
        assert mae < 3.0, f"Expected improved MAE < 3.0F, got {mae}F"
        
        print(f"PASS: forecast_quality.global_mae_f={mae}F (improved from 4.3F)")
    
    def test_forecast_quality_error_distribution(self):
        """Error distribution has multiple bins (was just 1 before)"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        data = response.json()
        
        forecast = data.get("forecast_quality", {})
        error_dist = forecast.get("error_distribution", [])
        
        # Should have multiple bins with counts
        assert len(error_dist) > 1, f"Expected multiple error bins, got {len(error_dist)}"
        
        # Count bins with actual data (count > 0)
        bins_with_data = [b for b in error_dist if b.get("count", 0) > 0]
        assert len(bins_with_data) > 1, f"Expected multiple bins with data, got {len(bins_with_data)}"
        
        print(f"PASS: error_distribution has {len(error_dist)} bins, {len(bins_with_data)} with data")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""
    
    def test_status_returns_200(self):
        """GET /api/status returns 200"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        print("PASS: Regression - GET /api/status returns 200")
    
    def test_health_returns_200(self):
        """GET /api/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("PASS: Regression - GET /api/health returns 200")
    
    def test_accuracy_history_returns_200(self):
        """GET /api/strategies/weather/accuracy/history returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/history")
        assert response.status_code == 200
        print("PASS: Regression - GET /api/strategies/weather/accuracy/history returns 200")
    
    def test_accuracy_calibration_returns_200(self):
        """GET /api/strategies/weather/accuracy/calibration returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/calibration")
        assert response.status_code == 200
        print("PASS: Regression - GET /api/strategies/weather/accuracy/calibration returns 200")


class TestStationMetricsDetail:
    """Detailed tests for station metrics after auto-resolution"""
    
    def test_each_station_has_required_fields(self):
        """Each station has required metric fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        data = response.json()
        
        station_metrics = data.get("forecast_quality", {}).get("station_metrics", {})
        
        required_fields = [
            "station_id", "sample_count", "mean_abs_error_f", "mean_bias_f",
            "max_abs_error_f", "calibration_meaningful"
        ]
        
        for station_id, metrics in station_metrics.items():
            for field in required_fields:
                assert field in metrics, f"Station {station_id} missing field: {field}"
        
        print(f"PASS: All {len(station_metrics)} stations have required fields")
    
    def test_each_station_has_samples(self):
        """Each station has sample_count >= 1"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        data = response.json()
        
        station_metrics = data.get("forecast_quality", {}).get("station_metrics", {})
        
        for station_id, metrics in station_metrics.items():
            sample_count = metrics.get("sample_count", 0)
            assert sample_count >= 1, f"Station {station_id} has no samples"
            print(f"  {station_id}: {sample_count} samples, MAE={metrics.get('mean_abs_error_f', 0):.2f}F")
        
        print(f"PASS: All stations have samples")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
