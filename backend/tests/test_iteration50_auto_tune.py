"""
Iteration 50: Auto-Tune Framework Testing

Tests for the sigma overconfidence multiplier auto-tuning framework:
- GET /api/strategies/weather/calibration/auto-tune status endpoint
- POST /api/strategies/weather/calibration/auto-tune/apply endpoint (should return 400 when disabled)
- GET /api/strategies/weather/health with sigma_pipeline.auto_tune section
- Config verification for auto-tune fields
- Frontend-facing fields: management_mode, mode_label, coverage_1sigma, etc.

Auto-tune is DISABLED by default (auto_tune_enabled=false).
System has 5 resolved samples (needs 30 minimum for full recommendations).
"""

import pytest
import requests
import os

# Use the production URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://edge-trading-hub-1.preview.emergentagent.com').rstrip('/')


class TestAutoTuneStatusEndpoint:
    """GET /api/strategies/weather/calibration/auto-tune tests"""
    
    def test_auto_tune_endpoint_returns_200(self):
        """Verify auto-tune status endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/strategies/weather/calibration/auto-tune returns 200")
    
    def test_auto_tune_has_required_fields(self):
        """Verify auto-tune response has all required fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune")
        data = response.json()
        
        required_fields = [
            "status",
            "current_multiplier",
            "recommended_multiplier",
            "management_mode",
            "auto_tune_enabled",
            "mode_label",
            "coverage_1sigma",
            "total_valid",
            "min_samples_required"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        print(f"PASS: Auto-tune response has all {len(required_fields)} required fields")
        print(f"  Fields present: {list(data.keys())}")
    
    def test_auto_tune_status_insufficient_data(self):
        """With only 5 samples (needs 30), status should be insufficient_data"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune")
        data = response.json()
        
        # Should be insufficient_data because we have 5 samples but need 30
        assert data.get("status") == "insufficient_data", \
            f"Expected status='insufficient_data', got '{data.get('status')}'"
        
        total_valid = data.get("total_valid", 0)
        min_samples = data.get("min_samples_required", 30)
        
        print(f"PASS: Auto-tune status is 'insufficient_data' (have {total_valid}/{min_samples} samples)")
    
    def test_management_mode_is_manual(self):
        """Management mode should be 'manual' when auto_tune_enabled=false"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune")
        data = response.json()
        
        assert data.get("management_mode") == "manual", \
            f"Expected management_mode='manual', got '{data.get('management_mode')}'"
        
        assert data.get("auto_tune_enabled") == False, \
            f"Expected auto_tune_enabled=False, got {data.get('auto_tune_enabled')}"
        
        print(f"PASS: management_mode='manual', auto_tune_enabled=False")
    
    def test_current_multiplier_is_125(self):
        """Current multiplier should be 1.25 (the default overconfidence multiplier)"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune")
        data = response.json()
        
        current = data.get("current_multiplier", 0)
        assert current == 1.25, f"Expected current_multiplier=1.25, got {current}"
        
        # Recommended should also be current when insufficient data or auto-tune disabled
        recommended = data.get("recommended_multiplier", 0)
        assert recommended == current, \
            f"With insufficient data, recommended should equal current ({recommended} vs {current})"
        
        print(f"PASS: current_multiplier={current}, recommended_multiplier={recommended}")
    
    def test_mode_label_describes_manual_mode(self):
        """Mode label should explain manual mode"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune")
        data = response.json()
        
        mode_label = data.get("mode_label", "")
        assert "manual" in mode_label.lower() or "operator" in mode_label.lower(), \
            f"Mode label should describe manual mode, got: '{mode_label}'"
        
        print(f"PASS: mode_label='{mode_label}'")


class TestAutoTuneApplyEndpoint:
    """POST /api/strategies/weather/calibration/auto-tune/apply tests"""
    
    def test_apply_returns_400_when_disabled(self):
        """POST apply should return 400 when auto-tune is disabled"""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune/apply")
        
        assert response.status_code == 400, \
            f"Expected 400 (auto-tune disabled), got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should mention that auto-tune is disabled
        detail = data.get("detail", "")
        assert "disable" in detail.lower() or "enable" in detail.lower(), \
            f"Error should mention auto-tune is disabled, got: '{detail}'"
        
        print(f"PASS: POST apply returns 400 with message: '{detail}'")


class TestWeatherHealthAutoTune:
    """GET /api/strategies/weather/health auto_tune section tests"""
    
    def test_health_has_auto_tune_section(self):
        """Weather health should include sigma_pipeline.auto_tune"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "sigma_pipeline" in data, "Missing sigma_pipeline in health"
        
        sigma_pipeline = data["sigma_pipeline"]
        assert "auto_tune" in sigma_pipeline, "Missing auto_tune in sigma_pipeline"
        
        auto_tune = sigma_pipeline["auto_tune"]
        print(f"PASS: Health has sigma_pipeline.auto_tune: {auto_tune}")
    
    def test_auto_tune_config_fields(self):
        """Verify auto_tune section has all config fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        
        auto_tune = data.get("sigma_pipeline", {}).get("auto_tune", {})
        
        required_fields = {
            "enabled": False,  # Should be disabled by default
            "step_size": 0.05,
            "min_multiplier": 1.0,
            "max_multiplier": 1.5,
            "target_coverage": 0.6827,
            "min_samples": 30,
            "mode": "manual"  # Should be 'manual' when disabled
        }
        
        for field, expected_value in required_fields.items():
            assert field in auto_tune, f"Missing auto_tune.{field}"
            actual = auto_tune[field]
            
            # For floats, use approximate comparison
            if isinstance(expected_value, float):
                assert abs(actual - expected_value) < 0.01, \
                    f"auto_tune.{field}: expected {expected_value}, got {actual}"
            else:
                assert actual == expected_value, \
                    f"auto_tune.{field}: expected {expected_value}, got {actual}"
        
        print(f"PASS: auto_tune config verified:")
        for field, value in required_fields.items():
            print(f"  {field}={auto_tune.get(field)}")


class TestWeatherConfigAutoTune:
    """GET /api/config/strategies weather_trader auto_tune config tests"""
    
    def test_config_has_auto_tune_fields(self):
        """Weather trader config should have all auto-tune fields"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200
        
        data = response.json()
        weather_config = data.get("weather_trader", {})
        
        auto_tune_fields = {
            "auto_tune_enabled": False,
            "auto_tune_step_size": 0.05,
            "auto_tune_min_multiplier": 1.0,
            "auto_tune_max_multiplier": 1.5,
            "auto_tune_target_coverage": 0.6827,
            "auto_tune_min_samples": 30
        }
        
        for field, expected in auto_tune_fields.items():
            assert field in weather_config, f"Missing config field: {field}"
            actual = weather_config[field]
            if isinstance(expected, float):
                assert abs(actual - expected) < 0.01, \
                    f"Config {field}: expected {expected}, got {actual}"
            else:
                assert actual == expected, \
                    f"Config {field}: expected {expected}, got {actual}"
        
        print("PASS: Weather config has all auto-tune fields with correct defaults")


class TestExistingEndpointsStillWork:
    """Verify existing endpoints still work correctly"""
    
    def test_analytics_summary_realized_pnl(self):
        """GET /api/analytics/summary should show correct realized PnL > 0"""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200
        
        data = response.json()
        realized_pnl = data.get("realized_pnl", 0)
        
        # Based on previous tests, realized PnL should be > 0
        assert realized_pnl > 0, f"Expected realized_pnl > 0, got {realized_pnl}"
        
        print(f"PASS: Realized PnL = ${realized_pnl:.2f}")
    
    def test_calibration_metrics_still_work(self):
        """GET /api/strategies/weather/calibration/metrics should return valid data"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/metrics")
        assert response.status_code == 200
        
        data = response.json()
        
        # Should have brier_score and coverage
        if data.get("status") == "computed":
            assert "brier_score" in data, "Missing brier_score"
            assert "coverage_1sigma" in data, "Missing coverage_1sigma"
            print(f"PASS: Calibration metrics: brier={data.get('brier_score')}, "
                  f"coverage_1sigma={data.get('coverage_1sigma')}")
        else:
            print(f"INFO: Calibration metrics status = {data.get('status')}")


class TestAutoTuneIntegration:
    """Integration tests for complete auto-tune flow"""
    
    def test_full_auto_tune_response_structure(self):
        """Verify complete auto-tune response matches expected structure"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune")
        data = response.json()
        
        # Verify nested structure
        expected_structure = {
            "status": str,
            "current_multiplier": (int, float),
            "recommended_multiplier": (int, float),
            "management_mode": str,
            "auto_tune_enabled": bool,
            "mode_label": str,
            "total_valid": int,
            "min_samples_required": int,
            "step_size": (int, float)
        }
        
        for field, expected_type in expected_structure.items():
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], expected_type), \
                f"Field {field} has wrong type: expected {expected_type}, got {type(data[field])}"
        
        print("PASS: Auto-tune response structure is correct")
        print(f"  Full response: {data}")
    
    def test_coverage_trend_present_when_data_available(self):
        """If there are valid samples, coverage_1sigma should be present"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/auto-tune")
        data = response.json()
        
        total_valid = data.get("total_valid", 0)
        
        if total_valid > 0:
            # If we have samples, we should have coverage data
            assert "coverage_1sigma" in data, "Should have coverage_1sigma with valid samples"
            coverage = data.get("coverage_1sigma")
            if coverage is not None:
                print(f"PASS: Coverage 1σ = {coverage:.1%} (based on {total_valid} samples)")
        else:
            print(f"INFO: No valid samples yet ({total_valid})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
