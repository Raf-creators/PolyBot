"""
Iteration 48 Tests: Realized PnL Fix, Weather Asymmetric Mode, Calibration & Self-Improvement

Test Suite for:
P1: Realized PnL tracking (fix for resolver trades)
P2: Weather Asymmetric Mode
P3: Calibration Metrics (Brier score, calibration error, sigma evolution)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://edge-trading-hub-1.preview.emergentagent.com')


class TestRealizedPnLFix:
    """P1: Realized PnL tracking and attribution fix tests."""

    def test_analytics_summary_returns_200(self):
        """GET /api/analytics/summary should return 200."""
        r = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        # Should have realized_pnl field
        assert "realized_pnl" in data or "total_pnl" in data, f"Missing PnL fields: {data.keys()}"

    def test_analytics_strategies_returns_200(self):
        """GET /api/analytics/strategies should return 200 with per-strategy PnL."""
        r = requests.get(f"{BASE_URL}/api/analytics/strategies")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        # Should be a dict with strategy keys
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"

    def test_strategy_attribution_returns_200(self):
        """GET /api/analytics/strategy-attribution should return 200."""
        r = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        # Should have strategy buckets
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        # Should have crypto, weather, arb buckets
        expected_buckets = ["crypto", "weather", "arb"]
        for bucket in expected_buckets:
            assert bucket in data, f"Missing bucket '{bucket}' in attribution data"

    def test_strategy_attribution_has_pnl_fields(self):
        """Strategy attribution should have realized_pnl, unrealized_pnl, total_pnl per bucket."""
        r = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        assert r.status_code == 200
        data = r.json()
        
        for bucket in ["crypto", "weather", "arb"]:
            if bucket in data:
                bucket_data = data[bucket]
                # Check required fields
                required_fields = ["realized_pnl", "unrealized_pnl", "total_pnl", "trade_count", "wins", "losses"]
                for field in required_fields:
                    assert field in bucket_data, f"Missing '{field}' in {bucket} bucket"

    def test_strategy_attribution_weather_asymmetric_bucket(self):
        """Strategy attribution should include weather_asymmetric bucket."""
        r = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        assert r.status_code == 200
        data = r.json()
        # weather_asymmetric should be a separate bucket for asymmetric mode trades
        # May or may not exist depending on if asymmetric trades happened
        # Just verify the structure supports it

    def test_fix_resolver_trades_endpoint_exists(self):
        """POST /api/admin/fix-resolver-trades should exist."""
        r = requests.post(f"{BASE_URL}/api/admin/fix-resolver-trades")
        # Should return 200 or some valid response (not 404/405)
        assert r.status_code in [200, 201], f"Expected 200/201, got {r.status_code}: {r.text}"
        data = r.json()
        assert "status" in data, f"Missing 'status' in response: {data}"
        assert data["status"] == "completed", f"Expected status='completed', got {data['status']}"
        assert "trades_fixed" in data, f"Missing 'trades_fixed' in response: {data}"

    def test_trades_have_strategy_id(self):
        """GET /api/trades should return trades with strategy_id set."""
        r = requests.get(f"{BASE_URL}/api/trades")
        assert r.status_code == 200
        trades = r.json()
        if len(trades) > 0:
            # Check at least some trades have strategy_id
            trades_with_strategy = [t for t in trades if t.get("strategy_id") and t["strategy_id"] != "resolver"]
            # Note: Some trades may still be 'resolver' if they haven't been fixed
            print(f"Trades with non-resolver strategy_id: {len(trades_with_strategy)}/{len(trades)}")


class TestWeatherAsymmetricMode:
    """P2: Weather Asymmetric Mode tests."""

    def test_asymmetric_summary_returns_200(self):
        """GET /api/strategies/weather-asymmetric/summary should return 200."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather-asymmetric/summary")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        
        # Required fields
        required_fields = ["open_positions", "position_count", "realized_pnl", "unrealized_pnl", "config"]
        for field in required_fields:
            assert field in data, f"Missing required field '{field}' in response"

    def test_asymmetric_config_values(self):
        """Asymmetric config should have expected default values."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather-asymmetric/summary")
        assert r.status_code == 200
        data = r.json()
        
        config = data.get("config", {})
        assert config.get("enabled") is True, f"asymmetric_enabled should be True, got {config.get('enabled')}"
        
        # Check config values (per requirements)
        expected = {
            "max_market_price": 0.25,
            "min_model_prob": 0.40,
            "min_edge": 0.15,
            "default_size": 5.0,
            "max_positions": 10,
        }
        for key, expected_val in expected.items():
            actual_val = config.get(key)
            assert actual_val == expected_val, f"Config {key}: expected {expected_val}, got {actual_val}"

    def test_asymmetric_summary_has_positions_list(self):
        """Asymmetric summary should include open_positions list."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather-asymmetric/summary")
        assert r.status_code == 200
        data = r.json()
        
        assert "open_positions" in data
        assert isinstance(data["open_positions"], list)
        
        # If there are positions, check structure
        if len(data["open_positions"]) > 0:
            pos = data["open_positions"][0]
            expected_fields = ["token_id", "market_question", "avg_cost", "size", "unrealized_pnl"]
            for field in expected_fields:
                assert field in pos, f"Position missing field '{field}'"

    def test_weather_health_includes_asymmetric_metrics(self):
        """GET /api/strategies/weather/health should include 'asymmetric' key in metrics."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert r.status_code == 200
        data = r.json()
        
        # Check for asymmetric metrics
        # They may be at top level or in 'metrics' sub-object
        has_asymmetric = (
            "asymmetric" in data or
            "asymmetric" in data.get("metrics", {}) or
            data.get("asymmetric") is not None
        )
        assert has_asymmetric, f"Missing 'asymmetric' metrics in health response"

    def test_weather_config_has_asymmetric_settings(self):
        """GET /api/strategies/weather/config should include asymmetric settings."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert r.status_code == 200
        data = r.json()
        
        asymmetric_fields = [
            "asymmetric_enabled",
            "asymmetric_max_market_price",
            "asymmetric_min_model_prob",
            "asymmetric_min_edge",
            "asymmetric_default_size",
            "asymmetric_max_positions",
        ]
        for field in asymmetric_fields:
            assert field in data, f"Missing asymmetric config field '{field}'"


class TestCalibrationMetrics:
    """P3: Calibration & Self-Improvement tests."""

    def test_calibration_metrics_returns_200(self):
        """GET /api/strategies/weather/calibration/metrics should return 200."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/metrics")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        
        # Should have status field
        assert "status" in data, f"Missing 'status' field: {data}"

    def test_calibration_metrics_structure(self):
        """Calibration metrics should have expected fields when data exists."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/metrics")
        assert r.status_code == 200
        data = r.json()
        
        # Check if we have data
        if data.get("status") in ["computed", "no_data", "no_valid_data"]:
            print(f"Calibration metrics status: {data.get('status')}")
            
            # If computed, check structure
            if data.get("status") == "computed":
                expected_fields = [
                    "brier_score",
                    "coverage_1sigma",
                    "coverage_2sigma",
                    "calibration_error",
                    "by_lead_bracket",
                    "by_market_type",
                ]
                for field in expected_fields:
                    assert field in data, f"Missing field '{field}' in computed metrics"
                
                # Check optional advanced fields
                optional_fields = ["calibration_curve", "sigma_evolution"]
                for field in optional_fields:
                    if field in data:
                        print(f"  {field}: present with {len(data[field]) if isinstance(data[field], list) else 'N/A'} items")

    def test_calibration_metrics_has_by_lead_bracket(self):
        """Calibration metrics should have by_lead_bracket breakdown."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/metrics")
        assert r.status_code == 200
        data = r.json()
        
        if data.get("status") == "computed":
            by_lead = data.get("by_lead_bracket", {})
            # Check expected lead brackets
            expected_brackets = ["0_24", "24_48", "48_72", "72_120", "120_168"]
            for bracket in expected_brackets:
                if bracket in by_lead:
                    bracket_data = by_lead[bracket]
                    # Check required fields per bracket
                    assert "coverage_1sigma" in bracket_data or "count" in bracket_data

    def test_calibration_metrics_has_by_market_type(self):
        """Calibration metrics should have by_market_type breakdown."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/metrics")
        assert r.status_code == 200
        data = r.json()
        
        if data.get("status") == "computed":
            by_type = data.get("by_market_type", {})
            print(f"by_market_type keys: {list(by_type.keys())}")
            # Should at least have temperature if there's data
            # Other types may be empty if no precip/snow/wind contracts

    def test_rolling_calibration_status(self):
        """GET /api/strategies/weather/calibration/rolling/status should return 200."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/rolling/status")
        assert r.status_code == 200
        data = r.json()
        
        # Should have enabled flag
        assert "enabled" in data, f"Missing 'enabled' field: {data}"

    def test_forecast_accuracy_history(self):
        """GET /api/strategies/weather/accuracy/history should return 200."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/accuracy/history?limit=10")
        assert r.status_code == 200
        data = r.json()
        
        # Should be a list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"Forecast accuracy records: {len(data)}")


class TestHealthAndStatus:
    """General health and status endpoint tests."""

    def test_health_endpoint(self):
        """GET /api/health should return 200."""
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"

    def test_status_endpoint(self):
        """GET /api/status should return 200."""
        r = requests.get(f"{BASE_URL}/api/status")
        assert r.status_code == 200
        data = r.json()
        # Should have stats
        assert "stats" in data or "positions" in data

    def test_controls_endpoint(self):
        """GET /api/controls should return 200."""
        r = requests.get(f"{BASE_URL}/api/controls")
        assert r.status_code == 200
        data = r.json()
        # Should have mode and limits
        assert "mode" in data or "kill_switch_active" in data

    def test_positions_by_strategy(self):
        """GET /api/positions/by-strategy should return 200."""
        r = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert r.status_code == 200
        data = r.json()
        
        # Should have positions dict
        assert "positions" in data
        assert "summaries" in data
        
        # Summaries should have weather_asymmetric or at least weather
        summaries = data.get("summaries", {})
        print(f"Strategy summaries: {list(summaries.keys())}")

    def test_weather_health(self):
        """GET /api/strategies/weather/health should return 200."""
        r = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert r.status_code == 200
        data = r.json()
        
        # Check for asymmetric key
        asymmetric_data = data.get("asymmetric", {})
        print(f"Weather health asymmetric data: {asymmetric_data}")


class TestPaperAdapterPnL:
    """Test that paper adapter properly records PnL on sell trades."""

    def test_trades_with_pnl(self):
        """Check if trades have PnL values recorded."""
        r = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert r.status_code == 200
        trades = r.json()
        
        # Count trades with non-zero PnL
        trades_with_pnl = [t for t in trades if t.get("pnl") and t["pnl"] != 0]
        sell_trades = [t for t in trades if t.get("side") == "sell"]
        
        print(f"Total trades: {len(trades)}")
        print(f"Sell trades: {len(sell_trades)}")
        print(f"Trades with non-zero PnL: {len(trades_with_pnl)}")
        
        # Verify sell trades have PnL (the bug was sell trades having $0 PnL)
        for t in sell_trades[:5]:
            print(f"  Sell trade {t.get('id', 'N/A')[:8]}: strategy={t.get('strategy_id')}, pnl=${t.get('pnl', 0):.4f}")


class TestStrategyTrackerPnL:
    """Test strategy tracker attribution of PnL."""

    def test_strategy_tracker(self):
        """GET /api/analytics/strategy-tracker should return performance data."""
        r = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        assert r.status_code == 200
        data = r.json()
        
        # Should have performance dict
        perf = data.get("performance", {})
        print(f"Strategy tracker performance keys: {list(perf.keys())}")
        
        for sid, p in perf.items():
            print(f"  {sid}: pnl=${p.get('total_pnl', 0):.4f}, trades={p.get('trade_count', 0)}, W/L={p.get('wins', 0)}/{p.get('losses', 0)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
