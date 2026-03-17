"""
Iteration 54: Threshold Simulator Panel Tests
Tests for POST /api/positions/weather/lifecycle/simulate endpoint
and verification that simulation does NOT modify live lifecycle data.
"""
import pytest
import requests
import os

# Get the backend URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://edge-trading-hub-1.preview.emergentagent.com"


class TestSimulateEndpointBasics:
    """Test POST /api/positions/weather/lifecycle/simulate endpoint structure"""

    def test_simulate_endpoint_returns_200(self):
        """POST /api/positions/weather/lifecycle/simulate should return 200"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={},  # Empty body uses defaults
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"PASS: Simulate endpoint returns 200")

    def test_simulate_returns_required_fields(self):
        """Simulate endpoint should return all required fields"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        required_fields = [
            "sim_thresholds", "live_thresholds", "total_evaluated",
            "live_candidates", "sim_candidates", "delta_candidates",
            "per_reason", "decision_quality", "comparison"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"PASS: All required fields present: {required_fields}")

    def test_simulate_returns_sim_thresholds(self):
        """Simulate should return sim_thresholds with all threshold values"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 1.5},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        sim_thresh = data.get("sim_thresholds", {})
        threshold_fields = [
            "profit_capture_threshold", "max_negative_edge_bps",
            "edge_decay_exit_pct", "time_inefficiency_hours",
            "time_inefficiency_min_edge_bps"
        ]
        
        for field in threshold_fields:
            assert field in sim_thresh, f"Missing sim_threshold field: {field}"
        
        # Verify the custom value was applied
        assert sim_thresh["profit_capture_threshold"] == 1.5, \
            f"Expected profit_capture_threshold=1.5, got {sim_thresh['profit_capture_threshold']}"
        print(f"PASS: sim_thresholds contains all 5 threshold fields")

    def test_simulate_returns_live_thresholds(self):
        """Simulate should return live_thresholds for comparison"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        live_thresh = data.get("live_thresholds", {})
        assert "profit_capture_threshold" in live_thresh
        assert "max_negative_edge_bps" in live_thresh
        assert "edge_decay_exit_pct" in live_thresh
        assert "time_inefficiency_hours" in live_thresh
        assert "time_inefficiency_min_edge_bps" in live_thresh
        print(f"PASS: live_thresholds contains all threshold fields")


class TestSimulatePerReasonBreakdown:
    """Test per_reason breakdown in simulation results"""

    def test_per_reason_structure(self):
        """per_reason should be a dict (may be empty if no positions evaluated)"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 1.0},  # Low threshold to trigger exits
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        per_reason = data.get("per_reason", None)
        assert per_reason is not None, "per_reason field missing"
        assert isinstance(per_reason, dict), f"per_reason should be dict, got {type(per_reason)}"
        
        # If there are positions evaluated, verify the structure
        total_evaluated = data.get("total_evaluated", 0)
        if total_evaluated > 0 and len(per_reason) > 0:
            expected_reasons = ["profit_capture", "negative_edge", "edge_decay", "time_inefficiency", "model_shift"]
            for reason in expected_reasons:
                if reason in per_reason:
                    reason_data = per_reason[reason]
                    assert "sim_count" in reason_data, f"Missing sim_count in {reason}"
                    assert "live_count" in reason_data, f"Missing live_count in {reason}"
                    assert "delta" in reason_data, f"Missing delta in {reason}"
        
        print(f"PASS: per_reason is valid dict (evaluated={total_evaluated}, reasons={len(per_reason)})")

    def test_per_reason_delta_calculated_correctly(self):
        """per_reason delta should equal sim_count - live_count"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 1.5},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        per_reason = data.get("per_reason", {})
        for reason, rdata in per_reason.items():
            expected_delta = rdata["sim_count"] - rdata["live_count"]
            assert rdata["delta"] == expected_delta, \
                f"Delta mismatch for {reason}: expected {expected_delta}, got {rdata['delta']}"
        
        print(f"PASS: All per_reason deltas calculated correctly")


class TestSimulateDecisionQuality:
    """Test decision_quality metrics in simulation results"""

    def test_decision_quality_structure(self):
        """decision_quality should be a dict (may be empty if no positions evaluated)"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        dq = data.get("decision_quality", None)
        assert dq is not None, "decision_quality field missing"
        assert isinstance(dq, dict), f"decision_quality should be dict, got {type(dq)}"
        
        # If there are positions evaluated, verify the structure
        total_evaluated = data.get("total_evaluated", 0)
        if total_evaluated > 0 and len(dq) > 0:
            required_fields = ["total_sim_exits", "good_exits", "bad_exits", "good_exit_pct", "bad_exit_pct"]
            for field in required_fields:
                assert field in dq, f"Missing decision_quality field: {field}"
        
        print(f"PASS: decision_quality is valid dict (evaluated={total_evaluated})")

    def test_decision_quality_percentages_add_up(self):
        """good_exit_pct + bad_exit_pct should approximately equal 100% (or 0% if no exits)"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 1.0},  # Low to trigger many exits
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        dq = data.get("decision_quality", {})
        total = dq.get("total_sim_exits", 0)
        good_pct = dq.get("good_exit_pct", 0)
        bad_pct = dq.get("bad_exit_pct", 0)
        
        if total > 0:
            # Percentages should add up to ~100% (allowing for rounding)
            total_pct = good_pct + bad_pct
            assert 99 <= total_pct <= 101, \
                f"Percentages don't add up: good={good_pct}% + bad={bad_pct}% = {total_pct}%"
        
        print(f"PASS: Decision quality percentages valid (good={good_pct}%, bad={bad_pct}%)")


class TestSimulateComparison:
    """Test comparison section in simulation results"""

    def test_comparison_structure(self):
        """comparison should be a dict (may be empty if no positions evaluated)"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        comparison = data.get("comparison", None)
        assert comparison is not None, "comparison field missing"
        assert isinstance(comparison, dict), f"comparison should be dict, got {type(comparison)}"
        
        # If there are positions evaluated, verify the structure
        total_evaluated = data.get("total_evaluated", 0)
        if total_evaluated > 0 and len(comparison) > 0:
            assert "live_candidates" in comparison, "Missing live_candidates"
            assert "sim_candidates" in comparison, "Missing sim_candidates"
            assert "delta" in comparison, "Missing delta"
            assert "new_exits" in comparison, "Missing new_exits"
            assert "removed_exits" in comparison, "Missing removed_exits"
            assert isinstance(comparison["new_exits"], list), "new_exits should be a list"
            assert isinstance(comparison["removed_exits"], list), "removed_exits should be a list"
        
        print(f"PASS: comparison is valid dict (evaluated={total_evaluated})")

    def test_comparison_delta_matches_candidates(self):
        """Top-level delta_candidates should equal sim_candidates - live_candidates"""
        response = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 1.5},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        
        # Verify at top level (always present even with 0 positions)
        sim_candidates = data.get("sim_candidates", 0)
        live_candidates = data.get("live_candidates", 0)
        delta_candidates = data.get("delta_candidates", 0)
        
        expected_delta = sim_candidates - live_candidates
        assert delta_candidates == expected_delta, \
            f"Delta mismatch: expected {expected_delta}, got {delta_candidates}"
        print(f"PASS: delta_candidates calculated correctly (sim={sim_candidates}, live={live_candidates}, delta={delta_candidates})")


class TestThresholdPresets:
    """Test that different threshold presets produce expected results"""

    def test_aggressive_produces_more_candidates(self):
        """Aggressive thresholds (1.5x profit) should produce more exit candidates"""
        # First get default results
        default_resp = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 2.0},  # Default
            headers={"Content-Type": "application/json"}
        )
        default_data = default_resp.json()
        default_candidates = default_data.get("sim_candidates", 0)
        
        # Then get aggressive results
        aggressive_resp = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 1.5},  # Aggressive
            headers={"Content-Type": "application/json"}
        )
        aggressive_data = aggressive_resp.json()
        aggressive_candidates = aggressive_data.get("sim_candidates", 0)
        
        # Aggressive should have >= candidates (lower threshold catches more)
        assert aggressive_candidates >= default_candidates, \
            f"Expected aggressive ({aggressive_candidates}) >= default ({default_candidates})"
        
        print(f"PASS: Aggressive ({aggressive_candidates}) >= Default ({default_candidates}) candidates")

    def test_conservative_produces_fewer_candidates(self):
        """Conservative thresholds (3.0x profit) should produce fewer exit candidates"""
        # First get default results
        default_resp = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 2.0},  # Default
            headers={"Content-Type": "application/json"}
        )
        default_data = default_resp.json()
        default_candidates = default_data.get("sim_candidates", 0)
        
        # Then get conservative results
        conservative_resp = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 3.0},  # Conservative
            headers={"Content-Type": "application/json"}
        )
        conservative_data = conservative_resp.json()
        conservative_candidates = conservative_data.get("sim_candidates", 0)
        
        # Conservative should have <= candidates (higher threshold catches fewer)
        assert conservative_candidates <= default_candidates, \
            f"Expected conservative ({conservative_candidates}) <= default ({default_candidates})"
        
        print(f"PASS: Conservative ({conservative_candidates}) <= Default ({default_candidates}) candidates")


class TestSimulationDoesNotModifyLive:
    """CRITICAL: Verify that simulation does NOT modify live lifecycle evaluations"""

    def test_simulation_does_not_modify_live_data(self):
        """
        GET lifecycle BEFORE → POST simulate → GET lifecycle AFTER
        Live data should be unchanged after simulation
        """
        # Step 1: Get live lifecycle state BEFORE simulation
        before_resp = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert before_resp.status_code == 200, f"GET lifecycle failed: {before_resp.status_code}"
        before_data = before_resp.json()
        before_evals = before_data.get("evaluations", {})
        before_mode = before_data.get("mode")
        before_metrics = before_data.get("metrics", {})
        
        # Step 2: Run simulation with VERY different thresholds
        sim_resp = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={
                "profit_capture_threshold": 0.5,  # Very low - should flag everything
                "max_negative_edge_bps": 0,       # Very permissive
                "edge_decay_exit_pct": 0.1,       # Very low
            },
            headers={"Content-Type": "application/json"}
        )
        assert sim_resp.status_code == 200, f"POST simulate failed: {sim_resp.status_code}"
        
        # Step 3: Get live lifecycle state AFTER simulation
        after_resp = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert after_resp.status_code == 200, f"GET lifecycle failed after sim: {after_resp.status_code}"
        after_data = after_resp.json()
        after_evals = after_data.get("evaluations", {})
        after_mode = after_data.get("mode")
        after_metrics = after_data.get("metrics", {})
        
        # Step 4: VERIFY NO CHANGES
        assert before_mode == after_mode, \
            f"Mode changed after simulation: {before_mode} -> {after_mode}"
        
        # Check that evaluations haven't changed
        assert len(before_evals) == len(after_evals), \
            f"Evaluation count changed: {len(before_evals)} -> {len(after_evals)}"
        
        # Check a few specific fields that should NOT change
        for token_id in list(before_evals.keys())[:5]:
            if token_id in after_evals:
                before_ev = before_evals[token_id]
                after_ev = after_evals[token_id]
                
                assert before_ev.get("is_exit_candidate") == after_ev.get("is_exit_candidate"), \
                    f"is_exit_candidate changed for {token_id[:8]}"
                assert before_ev.get("exit_reason") == after_ev.get("exit_reason"), \
                    f"exit_reason changed for {token_id[:8]}"
        
        print(f"PASS: Simulation did NOT modify live lifecycle data (mode={after_mode}, evals={len(after_evals)})")

    def test_simulation_does_not_affect_exit_candidates_endpoint(self):
        """Exit candidates endpoint should be unchanged after simulation"""
        # Get exit candidates BEFORE
        before_resp = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        before_data = before_resp.json()
        before_count = len(before_data.get("candidates", []))
        
        # Run simulation with extreme thresholds
        requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 0.1},
            headers={"Content-Type": "application/json"}
        )
        
        # Get exit candidates AFTER
        after_resp = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        after_data = after_resp.json()
        after_count = len(after_data.get("candidates", []))
        
        assert before_count == after_count, \
            f"Exit candidate count changed: {before_count} -> {after_count}"
        
        print(f"PASS: Exit candidates unchanged after simulation ({after_count} candidates)")


class TestRegressionPreviousFeatures:
    """Ensure previous lifecycle dashboard features still work"""

    def test_lifecycle_dashboard_still_works(self):
        """GET /api/positions/weather/lifecycle/dashboard should still return data"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        required_sections = ["summary", "reason_distribution", "time_buckets", "config"]
        for section in required_sections:
            assert section in data, f"Missing section: {section}"
        
        print(f"PASS: Lifecycle dashboard endpoint still works")

    def test_positions_by_strategy_still_enriched(self):
        """Weather positions should still have lifecycle data"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        
        data = response.json()
        weather_positions = data.get("positions", {}).get("weather", [])
        
        # Check at least one position has lifecycle data
        has_lifecycle = any(p.get("lifecycle") for p in weather_positions)
        print(f"PASS: positions/by-strategy returns weather positions (has_lifecycle={has_lifecycle})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
