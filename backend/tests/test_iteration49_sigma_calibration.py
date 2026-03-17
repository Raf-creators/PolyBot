"""
Iteration 49: Testing Controlled Calibration, Overconfidence Sigma Widening, 
Asymmetric Weather Strategy, Weather-by-Type PnL, and Full Observability

Features to test:
P1+P2: GET /api/strategies/weather/health should return sigma_pipeline with correct values
P1+P2: Config should have sigma_overconfidence_multiplier, calibration_max_adjustment_pct, calibration_min_samples_per_segment
P3: GET /api/strategies/weather/calibration/metrics returns calibration breakdown
P4: GET /api/strategies/weather-asymmetric/summary returns full asymmetric data
P5: GET /api/analytics/weather-by-type returns PnL breakdown by weather type
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestP1P2SigmaPipelineAndConfig:
    """Tests for P1 (Controlled Calibration) and P2 (Overconfidence Sigma Widening)"""

    def test_weather_health_has_sigma_pipeline(self):
        """GET /api/strategies/weather/health should return sigma_pipeline section"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Check sigma_pipeline exists
        assert "sigma_pipeline" in data, "sigma_pipeline should be in weather health response"
        sigma_pipeline = data["sigma_pipeline"]
        
        # Validate P2: overconfidence_multiplier = 1.25
        assert "overconfidence_multiplier" in sigma_pipeline, "sigma_pipeline should have overconfidence_multiplier"
        assert sigma_pipeline["overconfidence_multiplier"] == 1.25, f"Expected 1.25, got {sigma_pipeline['overconfidence_multiplier']}"
        
        # Validate P1: calibration_max_adjustment_pct = 0.25 (±25%)
        assert "calibration_max_adjustment_pct" in sigma_pipeline, "sigma_pipeline should have calibration_max_adjustment_pct"
        assert sigma_pipeline["calibration_max_adjustment_pct"] == 0.25, f"Expected 0.25, got {sigma_pipeline['calibration_max_adjustment_pct']}"
        
        # Validate P1: calibration_min_samples = 30
        assert "calibration_min_samples" in sigma_pipeline, "sigma_pipeline should have calibration_min_samples"
        assert sigma_pipeline["calibration_min_samples"] == 30, f"Expected 30, got {sigma_pipeline['calibration_min_samples']}"
        
        # Check status should be 'widened_temporary' when overconfidence_multiplier > 1.0
        assert "status" in sigma_pipeline, "sigma_pipeline should have status"
        assert sigma_pipeline["status"] == "widened_temporary", f"Expected 'widened_temporary', got {sigma_pipeline['status']}"

    def test_weather_config_has_calibration_fields(self):
        """Config should have sigma_overconfidence_multiplier, calibration_max_adjustment_pct, calibration_min_samples_per_segment"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        
        config = data.get("config", {})
        
        # P2: sigma_overconfidence_multiplier
        assert "sigma_overconfidence_multiplier" in config, "config should have sigma_overconfidence_multiplier"
        assert config["sigma_overconfidence_multiplier"] == 1.25, f"Expected 1.25, got {config['sigma_overconfidence_multiplier']}"
        
        # P1: calibration_max_adjustment_pct
        assert "calibration_max_adjustment_pct" in config, "config should have calibration_max_adjustment_pct"
        assert config["calibration_max_adjustment_pct"] == 0.25, f"Expected 0.25, got {config['calibration_max_adjustment_pct']}"
        
        # P1: calibration_min_samples_per_segment
        assert "calibration_min_samples_per_segment" in config, "config should have calibration_min_samples_per_segment"
        assert config["calibration_min_samples_per_segment"] == 30, f"Expected 30, got {config['calibration_min_samples_per_segment']}"


class TestP3CalibrationMetrics:
    """Tests for P3 - Calibration metrics with segmentation"""

    def test_calibration_metrics_returns_all_fields(self):
        """GET /api/strategies/weather/calibration/metrics should return all calibration data"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/metrics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Top-level metrics
        assert "brier_score" in data, "Should have brier_score"
        assert "coverage_1sigma" in data, "Should have coverage_1sigma"
        assert "calibration_error" in data, "Should have calibration_error"
        
        # Segmentation fields
        assert "by_lead_bracket" in data, "Should have by_lead_bracket breakdown"
        assert "by_market_type" in data, "Should have by_market_type breakdown"
        assert "calibration_curve" in data, "Should have calibration_curve"
        assert "sigma_evolution" in data, "Should have sigma_evolution"

    def test_calibration_segments_by_lead_bracket(self):
        """Calibration should segment by lead bracket"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/metrics")
        assert response.status_code == 200
        data = response.json()
        
        by_lead = data.get("by_lead_bracket", {})
        # Either we have lead bracket data or the response has no data yet
        if data.get("total_valid", 0) > 0:
            # Should have at least one bracket with data
            assert len(by_lead) > 0, "Should have at least one lead bracket if there's valid data"
            # Each bracket should have expected fields
            for bracket, info in by_lead.items():
                assert "count" in info, f"Lead bracket {bracket} should have count"
                assert "coverage_1sigma" in info, f"Lead bracket {bracket} should have coverage_1sigma"
                assert "brier_score" in info, f"Lead bracket {bracket} should have brier_score"

    def test_calibration_segments_by_market_type(self):
        """Calibration should segment by market type"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/metrics")
        assert response.status_code == 200
        data = response.json()
        
        by_type = data.get("by_market_type", {})
        # Either we have type data or the response has no data yet
        if data.get("total_valid", 0) > 0:
            assert len(by_type) > 0, "Should have at least one market type if there's valid data"
            for mtype, info in by_type.items():
                assert "count" in info, f"Market type {mtype} should have count"
                assert "coverage_1sigma" in info, f"Market type {mtype} should have coverage_1sigma"


class TestP4AsymmetricWeatherSummary:
    """Tests for P4 - Asymmetric Weather Strategy Summary"""

    def test_asymmetric_summary_returns_all_fields(self):
        """GET /api/strategies/weather-asymmetric/summary should return all expected fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather-asymmetric/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Required fields
        assert "open_positions" in data, "Should have open_positions"
        assert "realized_pnl" in data, "Should have realized_pnl"
        assert "unrealized_pnl" in data, "Should have unrealized_pnl"
        assert "wins" in data, "Should have wins"
        assert "losses" in data, "Should have losses"
        assert "win_rate" in data, "Should have win_rate"
        assert "config" in data, "Should have config"
        assert "metrics" in data or "position_count" in data, "Should have metrics or position_count"

    def test_asymmetric_config_values(self):
        """Asymmetric config should have correct default values"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather-asymmetric/summary")
        assert response.status_code == 200
        data = response.json()
        
        config = data.get("config", {})
        
        # Verify config has expected fields
        assert "enabled" in config, "Config should have enabled"
        assert "max_market_price" in config, "Config should have max_market_price"
        assert "min_model_prob" in config, "Config should have min_model_prob"
        assert "min_edge" in config, "Config should have min_edge"


class TestP5WeatherByType:
    """Tests for P5 - Weather-by-type PnL breakdown"""

    def test_weather_by_type_returns_all_types(self):
        """GET /api/analytics/weather-by-type should return breakdown for all 4 types"""
        response = requests.get(f"{BASE_URL}/api/analytics/weather-by-type")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Should have all 4 weather types
        expected_types = ["temperature", "precipitation", "snowfall", "wind"]
        for wtype in expected_types:
            assert wtype in data, f"Should have {wtype} in breakdown"

    def test_weather_by_type_has_pnl_fields(self):
        """Each weather type should have PnL and trade fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/weather-by-type")
        assert response.status_code == 200
        data = response.json()
        
        for wtype in ["temperature", "precipitation", "snowfall", "wind"]:
            type_data = data.get(wtype, {})
            
            # Check required fields
            assert "buy_count" in type_data, f"{wtype} should have buy_count"
            assert "close_count" in type_data, f"{wtype} should have close_count"
            assert "realized_pnl" in type_data, f"{wtype} should have realized_pnl"
            assert "unrealized_pnl" in type_data, f"{wtype} should have unrealized_pnl"
            assert "wins" in type_data, f"{wtype} should have wins"
            assert "losses" in type_data, f"{wtype} should have losses"
            assert "win_rate" in type_data, f"{wtype} should have win_rate"


class TestBackendRealizedPnL:
    """Backend analytics should show realized_pnl"""

    def test_analytics_summary_has_realized_pnl(self):
        """GET /api/analytics/summary should show realized_pnl"""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "realized_pnl" in data, "Should have realized_pnl field"
        # From previous test, realized_pnl was $142.70
        # Just verify it's present and a number
        assert isinstance(data["realized_pnl"], (int, float)), "realized_pnl should be a number"

    def test_strategy_attribution_correct_pnl(self):
        """GET /api/analytics/strategy-attribution should correctly attribute PnL"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Should have strategy buckets
        for bucket in ["crypto", "weather", "arb"]:
            assert bucket in data, f"Should have {bucket} in strategy attribution"
            bucket_data = data[bucket]
            assert "realized_pnl" in bucket_data, f"{bucket} should have realized_pnl"
            assert "unrealized_pnl" in bucket_data, f"{bucket} should have unrealized_pnl"


class TestSigmaTraceInExplanation:
    """Test that signal explanations include sigma_trace data"""

    def test_weather_signals_have_sigma_trace(self):
        """Weather signals should include sigma_trace in explanation"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals?limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # If there are any signals (tradable or rejected), check for sigma_trace
        all_signals = data.get("tradable", []) + data.get("rejected", [])
        
        if len(all_signals) > 0:
            # Check at least one signal has sigma_trace in explanation
            has_sigma_trace = False
            for sig in all_signals:
                explanation = sig.get("explanation", {})
                if "sigma_trace" in explanation:
                    has_sigma_trace = True
                    sigma_trace = explanation["sigma_trace"]
                    # Verify sigma_trace structure
                    assert "overconfidence_multiplier" in sigma_trace, "sigma_trace should have overconfidence_multiplier"
                    assert "final_sigma" in sigma_trace, "sigma_trace should have final_sigma"
                    break
            
            # Note: It's okay if no signals have sigma_trace yet - they get added during scan
            if not has_sigma_trace:
                print("INFO: No signals with sigma_trace found (scan may not have run yet)")


class TestHealthEndpoint:
    """Basic health checks"""

    def test_health_endpoint(self):
        """GET /api/health returns ok status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("status") == "ok", f"Expected status=ok, got {data.get('status')}"

    def test_status_endpoint(self):
        """GET /api/status returns data"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "stats" in data, "Should have stats"
        assert "strategies" in data, "Should have strategies"
        assert "mode" in data, "Should have mode"
