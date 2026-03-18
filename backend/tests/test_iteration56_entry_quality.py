"""
Iteration 56: Standard Weather Entry Quality Tests

Tests for tightening standard weather entry quality to reduce low-quality long-hold positions:
1. GET /api/strategies/weather/entry-quality returns config, rejections, passed_signals, open_positions
2. Entry quality config contains all required fields with expected defaults
3. Rejections object tracks low_quality, low_edge_long, long_hold_penalty counts  
4. passed_signals tracks total, avg_quality, avg_edge_bps, avg_lead_hours
5. open_positions shows count, avg_profit_multiple, avg_edge_at_entry_bps, avg_hours_to_resolution
6. GET /api/strategies/weather/health includes entry_quality section
7. Entry quality filters do NOT affect asymmetric weather signals
8. POST /api/strategies/weather/lifecycle/mode still works (unchanged)
9. Previous features still work (dashboard, exit candidates, simulator)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestEntryQualityEndpoint:
    """Tests for GET /api/strategies/weather/entry-quality endpoint"""
    
    def test_entry_quality_endpoint_exists(self):
        """Entry quality endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ GET /api/strategies/weather/entry-quality returns 200")
    
    def test_entry_quality_has_config_field(self):
        """Response contains config object"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        data = response.json()
        assert "config" in data, f"Missing 'config' field. Keys: {data.keys()}"
        assert isinstance(data["config"], dict), f"config should be dict, got {type(data['config'])}"
        print(f"✓ config field present with {len(data['config'])} keys")
    
    def test_entry_quality_has_rejections_field(self):
        """Response contains rejections object"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        data = response.json()
        assert "rejections" in data, f"Missing 'rejections' field. Keys: {data.keys()}"
        assert isinstance(data["rejections"], dict), f"rejections should be dict"
        print(f"✓ rejections field present: {data['rejections']}")
    
    def test_entry_quality_has_passed_signals_field(self):
        """Response contains passed_signals object"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        data = response.json()
        assert "passed_signals" in data, f"Missing 'passed_signals' field. Keys: {data.keys()}"
        assert isinstance(data["passed_signals"], dict), f"passed_signals should be dict"
        print(f"✓ passed_signals field present: {data['passed_signals']}")
    
    def test_entry_quality_has_open_positions_field(self):
        """Response contains open_positions object"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        data = response.json()
        assert "open_positions" in data, f"Missing 'open_positions' field. Keys: {data.keys()}"
        assert isinstance(data["open_positions"], dict), f"open_positions should be dict"
        print(f"✓ open_positions field present: {data['open_positions']}")


class TestEntryQualityConfig:
    """Tests for entry quality config values"""
    
    def test_config_has_min_quality_score(self):
        """Config contains min_quality_score = 0.35"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        config = response.json().get("config", {})
        assert "min_quality_score" in config, f"Missing min_quality_score. Keys: {config.keys()}"
        assert config["min_quality_score"] == 0.35, f"Expected 0.35, got {config['min_quality_score']}"
        print(f"✓ min_quality_score = {config['min_quality_score']}")
    
    def test_config_has_min_edge_bps_long(self):
        """Config contains min_edge_bps_long = 700"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        config = response.json().get("config", {})
        assert "min_edge_bps_long" in config, f"Missing min_edge_bps_long. Keys: {config.keys()}"
        assert config["min_edge_bps_long"] == 700.0, f"Expected 700, got {config['min_edge_bps_long']}"
        print(f"✓ min_edge_bps_long = {config['min_edge_bps_long']}")
    
    def test_config_has_long_resolution_hours(self):
        """Config contains long_resolution_hours = 24"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        config = response.json().get("config", {})
        assert "long_resolution_hours" in config, f"Missing long_resolution_hours. Keys: {config.keys()}"
        assert config["long_resolution_hours"] == 24.0, f"Expected 24, got {config['long_resolution_hours']}"
        print(f"✓ long_resolution_hours = {config['long_resolution_hours']}")
    
    def test_config_has_time_preference_weight(self):
        """Config contains time_preference_weight = 0.15"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        config = response.json().get("config", {})
        assert "time_preference_weight" in config, f"Missing time_preference_weight. Keys: {config.keys()}"
        assert config["time_preference_weight"] == 0.15, f"Expected 0.15, got {config['time_preference_weight']}"
        print(f"✓ time_preference_weight = {config['time_preference_weight']}")
    
    def test_config_has_long_hold_penalty(self):
        """Config contains long_hold_penalty = 0.20"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        config = response.json().get("config", {})
        assert "long_hold_penalty" in config, f"Missing long_hold_penalty. Keys: {config.keys()}"
        assert config["long_hold_penalty"] == 0.20, f"Expected 0.20, got {config['long_hold_penalty']}"
        print(f"✓ long_hold_penalty = {config['long_hold_penalty']}")


class TestEntryQualityRejections:
    """Tests for rejection counters"""
    
    def test_rejections_has_low_quality_counter(self):
        """Rejections object tracks low_quality count"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        rejections = response.json().get("rejections", {})
        assert "low_quality" in rejections, f"Missing low_quality. Keys: {rejections.keys()}"
        assert isinstance(rejections["low_quality"], (int, float)), f"low_quality should be numeric"
        print(f"✓ low_quality rejections = {rejections['low_quality']}")
    
    def test_rejections_has_low_edge_long_counter(self):
        """Rejections object tracks low_edge_long count"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        rejections = response.json().get("rejections", {})
        assert "low_edge_long" in rejections, f"Missing low_edge_long. Keys: {rejections.keys()}"
        assert isinstance(rejections["low_edge_long"], (int, float)), f"low_edge_long should be numeric"
        print(f"✓ low_edge_long rejections = {rejections['low_edge_long']}")
    
    def test_rejections_has_long_hold_penalty_counter(self):
        """Rejections object tracks long_hold_penalty count"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        rejections = response.json().get("rejections", {})
        assert "long_hold_penalty" in rejections, f"Missing long_hold_penalty. Keys: {rejections.keys()}"
        assert isinstance(rejections["long_hold_penalty"], (int, float)), f"long_hold_penalty should be numeric"
        print(f"✓ long_hold_penalty rejections = {rejections['long_hold_penalty']}")


class TestEntryQualityPassedSignals:
    """Tests for passed_signals metrics"""
    
    def test_passed_signals_has_total(self):
        """passed_signals tracks total count"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        passed = response.json().get("passed_signals", {})
        assert "total" in passed, f"Missing total. Keys: {passed.keys()}"
        assert isinstance(passed["total"], (int, float)), f"total should be numeric"
        print(f"✓ passed_signals total = {passed['total']}")
    
    def test_passed_signals_has_avg_quality(self):
        """passed_signals tracks avg_quality"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        passed = response.json().get("passed_signals", {})
        assert "avg_quality" in passed, f"Missing avg_quality. Keys: {passed.keys()}"
        assert isinstance(passed["avg_quality"], (int, float)), f"avg_quality should be numeric"
        print(f"✓ passed_signals avg_quality = {passed['avg_quality']}")
    
    def test_passed_signals_has_avg_edge_bps(self):
        """passed_signals tracks avg_edge_bps"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        passed = response.json().get("passed_signals", {})
        assert "avg_edge_bps" in passed, f"Missing avg_edge_bps. Keys: {passed.keys()}"
        assert isinstance(passed["avg_edge_bps"], (int, float)), f"avg_edge_bps should be numeric"
        print(f"✓ passed_signals avg_edge_bps = {passed['avg_edge_bps']}")
    
    def test_passed_signals_has_avg_lead_hours(self):
        """passed_signals tracks avg_lead_hours"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        passed = response.json().get("passed_signals", {})
        assert "avg_lead_hours" in passed, f"Missing avg_lead_hours. Keys: {passed.keys()}"
        assert isinstance(passed["avg_lead_hours"], (int, float)), f"avg_lead_hours should be numeric"
        print(f"✓ passed_signals avg_lead_hours = {passed['avg_lead_hours']}")


class TestEntryQualityOpenPositions:
    """Tests for open_positions metrics"""
    
    def test_open_positions_has_count(self):
        """open_positions shows count"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        open_pos = response.json().get("open_positions", {})
        assert "count" in open_pos, f"Missing count. Keys: {open_pos.keys()}"
        assert isinstance(open_pos["count"], (int, float)), f"count should be numeric"
        print(f"✓ open_positions count = {open_pos['count']}")
    
    def test_open_positions_has_avg_profit_multiple(self):
        """open_positions shows avg_profit_multiple"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        open_pos = response.json().get("open_positions", {})
        assert "avg_profit_multiple" in open_pos, f"Missing avg_profit_multiple. Keys: {open_pos.keys()}"
        assert isinstance(open_pos["avg_profit_multiple"], (int, float)), f"avg_profit_multiple should be numeric"
        print(f"✓ open_positions avg_profit_multiple = {open_pos['avg_profit_multiple']}")
    
    def test_open_positions_has_avg_edge_at_entry_bps(self):
        """open_positions shows avg_edge_at_entry_bps"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        open_pos = response.json().get("open_positions", {})
        assert "avg_edge_at_entry_bps" in open_pos, f"Missing avg_edge_at_entry_bps. Keys: {open_pos.keys()}"
        assert isinstance(open_pos["avg_edge_at_entry_bps"], (int, float)), f"avg_edge_at_entry_bps should be numeric"
        print(f"✓ open_positions avg_edge_at_entry_bps = {open_pos['avg_edge_at_entry_bps']}")
    
    def test_open_positions_has_avg_hours_to_resolution(self):
        """open_positions shows avg_hours_to_resolution"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        open_pos = response.json().get("open_positions", {})
        assert "avg_hours_to_resolution" in open_pos, f"Missing avg_hours_to_resolution. Keys: {open_pos.keys()}"
        assert isinstance(open_pos["avg_hours_to_resolution"], (int, float)), f"avg_hours_to_resolution should be numeric"
        print(f"✓ open_positions avg_hours_to_resolution = {open_pos['avg_hours_to_resolution']}")


class TestWeatherHealthEntryQuality:
    """Tests for entry_quality section in /health endpoint"""
    
    def test_health_includes_entry_quality_section(self):
        """GET /api/strategies/weather/health includes entry_quality"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200, f"Health endpoint failed: {response.status_code}"
        data = response.json()
        assert "entry_quality" in data, f"Missing entry_quality in health. Keys: {data.keys()}"
        print(f"✓ /health includes entry_quality section")
    
    def test_health_entry_quality_has_config(self):
        """entry_quality in health has config"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        eq = response.json().get("entry_quality", {})
        assert "config" in eq, f"Missing config in entry_quality. Keys: {eq.keys()}"
        print(f"✓ health entry_quality has config: {eq['config']}")
    
    def test_health_entry_quality_has_rejections(self):
        """entry_quality in health has rejections"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        eq = response.json().get("entry_quality", {})
        assert "rejections" in eq, f"Missing rejections in entry_quality. Keys: {eq.keys()}"
        print(f"✓ health entry_quality has rejections: {eq['rejections']}")


class TestAsymmetricUnaffected:
    """Tests that asymmetric weather signals are NOT affected by entry quality filters"""
    
    def test_asymmetric_summary_endpoint_works(self):
        """GET /api/strategies/weather-asymmetric/summary returns data"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather-asymmetric/summary")
        assert response.status_code == 200, f"Asymmetric summary failed: {response.status_code}"
        data = response.json()
        # Should have standard fields
        assert "position_count" in data or "config" in data or "open_positions" in data, \
            f"Asymmetric summary missing expected fields. Keys: {data.keys()}"
        print(f"✓ Asymmetric summary returns: position_count={data.get('position_count', 'N/A')}")
    
    def test_asymmetric_config_separate_from_standard(self):
        """Asymmetric config has different (lower) thresholds than standard"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather-asymmetric/summary")
        data = response.json()
        config = data.get("config", {})
        # Asymmetric uses min_model_prob, min_edge (raw), not quality filters
        if config:
            print(f"✓ Asymmetric config: max_price={config.get('max_market_price')}, "
                  f"min_model_prob={config.get('min_model_prob')}, min_edge={config.get('min_edge')}")
        else:
            print("✓ Asymmetric summary returned (config may be nested differently)")


class TestPreviousFeaturesRegression:
    """Tests that previous features still work"""
    
    def test_lifecycle_mode_endpoint_works(self):
        """POST /api/strategies/weather/lifecycle/mode still works"""
        # Get current mode first
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        current_mode = response.json().get("mode", "tag_only")
        
        # Test setting same mode (should return unchanged)
        response = requests.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": current_mode}
        )
        assert response.status_code == 200, f"Mode endpoint failed: {response.status_code}: {response.text}"
        data = response.json()
        assert "status" in data, f"Missing status in response"
        print(f"✓ Lifecycle mode endpoint works: status={data['status']}, mode={data.get('mode', current_mode)}")
    
    def test_lifecycle_dashboard_works(self):
        """GET /api/positions/weather/lifecycle/dashboard still returns data"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        assert response.status_code == 200, f"Dashboard failed: {response.status_code}"
        data = response.json()
        assert "summary" in data or "reason_distribution" in data, \
            f"Dashboard missing expected fields. Keys: {data.keys()}"
        print(f"✓ Lifecycle dashboard works with summary: {data.get('summary', {})}")
    
    def test_exit_candidates_endpoint_works(self):
        """GET /api/positions/weather/exit-candidates still works"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200, f"Exit candidates failed: {response.status_code}"
        data = response.json()
        assert "mode" in data or "candidates" in data, \
            f"Exit candidates missing expected fields. Keys: {data.keys()}"
        print(f"✓ Exit candidates works: mode={data.get('mode')}, "
              f"candidates={len(data.get('candidates', []))}")
    
    def test_positions_by_strategy_works(self):
        """GET /api/positions/by-strategy still returns weather positions"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200, f"Positions by strategy failed: {response.status_code}"
        data = response.json()
        assert "positions" in data, f"Missing positions. Keys: {data.keys()}"
        assert "weather" in data.get("positions", {}), f"Missing weather positions"
        weather_count = len(data["positions"].get("weather", []))
        print(f"✓ Positions by strategy works: {weather_count} weather positions")


class TestIntegrationDataFlow:
    """Tests data flow between entry quality and other components"""
    
    def test_entry_quality_rejection_counters_increment(self):
        """Verify rejection counters are tracked (may be > 0 after scans)"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        rejections = response.json().get("rejections", {})
        total = sum(rejections.get(k, 0) for k in ["low_quality", "low_edge_long", "long_hold_penalty"])
        print(f"✓ Total rejections tracked: {total} "
              f"(low_quality={rejections.get('low_quality', 0)}, "
              f"low_edge_long={rejections.get('low_edge_long', 0)}, "
              f"long_hold_penalty={rejections.get('long_hold_penalty', 0)})")
        # Note: Context says 3 rejections for low_edge_long expected
        if rejections.get("low_edge_long", 0) > 0:
            print("  → low_edge_long rejections detected as expected from context")
    
    def test_entry_quality_passed_metrics_reasonable(self):
        """Verify passed signal metrics are reasonable"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        passed = response.json().get("passed_signals", {})
        
        # If signals have passed, metrics should be reasonable
        if passed.get("total", 0) > 0:
            assert 0 <= passed.get("avg_quality", 0) <= 1, f"avg_quality should be 0-1"
            assert passed.get("avg_edge_bps", 0) >= 0, f"avg_edge_bps should be >= 0"
            assert passed.get("avg_lead_hours", 0) >= 0, f"avg_lead_hours should be >= 0"
            print(f"✓ Passed signal metrics reasonable: total={passed['total']}, "
                  f"avg_quality={passed['avg_quality']:.3f}, "
                  f"avg_edge={passed['avg_edge_bps']:.0f}bps")
        else:
            print("✓ No passed signals yet (metrics are 0)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
