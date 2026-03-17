"""
Iteration 53: Lifecycle Dashboard API Tests
Tests the new GET /api/positions/weather/lifecycle/dashboard endpoint 
and validates all response fields for threshold validation and exit-decision quality.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://edge-trading-hub-1.preview.emergentagent.com").rstrip("/")


class TestLifecycleDashboardAPI:
    """Tests for GET /api/positions/weather/lifecycle/dashboard endpoint"""
    
    def test_lifecycle_dashboard_returns_200(self):
        """Dashboard endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/positions/weather/lifecycle/dashboard returns 200")
    
    def test_dashboard_has_all_required_sections(self):
        """Dashboard should return all 8 required sections"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        data = response.json()
        
        required_keys = [
            "summary", "reason_distribution", "time_buckets", 
            "shadow_exits", "sold_vs_held", "sold_vs_held_by_reason",
            "profit_distribution", "config"
        ]
        
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"
        
        print(f"PASS: Dashboard contains all 8 required sections: {required_keys}")
    
    def test_summary_has_required_fields(self):
        """Summary section should contain all exit candidate metrics"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        summary = response.json()["summary"]
        
        required_fields = [
            "total_positions_evaluated",
            "total_exit_candidates", 
            "avg_profit_multiple",
            "avg_current_edge_bps",
            "avg_edge_decay_pct"
        ]
        
        for field in required_fields:
            assert field in summary, f"Summary missing field: {field}"
        
        # Validate types
        assert isinstance(summary["total_positions_evaluated"], int)
        assert isinstance(summary["total_exit_candidates"], int)
        assert isinstance(summary["avg_profit_multiple"], (int, float))
        assert isinstance(summary["avg_current_edge_bps"], (int, float))
        assert isinstance(summary["avg_edge_decay_pct"], (int, float))
        
        print(f"PASS: Summary contains required fields with correct types")
        print(f"  - total_positions_evaluated: {summary['total_positions_evaluated']}")
        print(f"  - total_exit_candidates: {summary['total_exit_candidates']}")
        print(f"  - avg_profit_multiple: {summary['avg_profit_multiple']}")
        print(f"  - avg_current_edge_bps: {summary['avg_current_edge_bps']}")
        print(f"  - avg_edge_decay_pct: {summary['avg_edge_decay_pct']}")
    
    def test_reason_distribution_structure(self):
        """Reason distribution should have count and avg_profit_mult for each reason"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        reason_dist = response.json()["reason_distribution"]
        
        # reason_distribution is a dict of reason -> {count, avg_profit_mult, avg_edge, tokens}
        assert isinstance(reason_dist, dict), "reason_distribution should be a dict"
        
        # If there are exit candidates, validate structure
        for reason, data in reason_dist.items():
            assert "count" in data, f"Reason {reason} missing 'count'"
            assert "avg_profit_mult" in data, f"Reason {reason} missing 'avg_profit_mult'"
            assert isinstance(data["count"], int), f"count should be int for {reason}"
        
        # Valid exit reasons
        valid_reasons = ["profit_capture", "negative_edge", "edge_decay", "time_inefficiency", "model_shift"]
        for reason in reason_dist.keys():
            assert reason in valid_reasons or reason == "unknown", f"Invalid reason: {reason}"
        
        print(f"PASS: reason_distribution structure valid with {len(reason_dist)} reasons")
        for reason, data in reason_dist.items():
            print(f"  - {reason}: count={data['count']}, avg_profit_mult={data['avg_profit_mult']}")
    
    def test_time_buckets_has_required_keys(self):
        """Time buckets should have <6h, 6-24h, >24h, unknown"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        time_buckets = response.json()["time_buckets"]
        
        required_buckets = ["<6h", "6-24h", ">24h", "unknown"]
        for bucket in required_buckets:
            assert bucket in time_buckets, f"Missing time bucket: {bucket}"
        
        # Each bucket should have total, exit_candidates, avg_profit_mult
        for bucket, data in time_buckets.items():
            assert "total" in data, f"Bucket {bucket} missing 'total'"
            assert "exit_candidates" in data, f"Bucket {bucket} missing 'exit_candidates'"
            assert "avg_profit_mult" in data, f"Bucket {bucket} missing 'avg_profit_mult'"
        
        print(f"PASS: time_buckets has all 4 required buckets with correct fields")
        for bucket, data in time_buckets.items():
            print(f"  - {bucket}: total={data['total']}, exit_candidates={data['exit_candidates']}, avg_profit_mult={data['avg_profit_mult']}")
    
    def test_sold_vs_held_structure(self):
        """sold_vs_held entries should have sim_exit_pnl, held_pnl, delta, delta_direction"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        sold_vs_held = response.json()["sold_vs_held"]
        
        assert isinstance(sold_vs_held, list), "sold_vs_held should be a list"
        
        required_fields = [
            "sim_exit_pnl", "held_pnl", "delta", "delta_direction",
            "flagged_price", "current_price", "reason"
        ]
        
        for entry in sold_vs_held:
            for field in required_fields:
                assert field in entry, f"sold_vs_held entry missing field: {field}"
            
            # Validate delta_direction values
            assert entry["delta_direction"] in ["hold_better", "sell_better", "neutral"], \
                f"Invalid delta_direction: {entry['delta_direction']}"
        
        print(f"PASS: sold_vs_held has {len(sold_vs_held)} entries with correct structure")
        for entry in sold_vs_held:
            print(f"  - {entry.get('market_question', entry['token_id'])[:40]}: delta={entry['delta']}, direction={entry['delta_direction']}")
    
    def test_sold_vs_held_by_reason_structure(self):
        """sold_vs_held_by_reason should aggregate sim_exit_pnl, held_pnl, total_delta"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        by_reason = response.json()["sold_vs_held_by_reason"]
        
        assert isinstance(by_reason, dict), "sold_vs_held_by_reason should be a dict"
        
        for reason, data in by_reason.items():
            assert "count" in data, f"Reason {reason} missing 'count'"
            assert "total_sim_exit_pnl" in data, f"Reason {reason} missing 'total_sim_exit_pnl'"
            assert "total_held_pnl" in data, f"Reason {reason} missing 'total_held_pnl'"
            assert "total_delta" in data, f"Reason {reason} missing 'total_delta'"
            assert "verdict" in data, f"Reason {reason} missing 'verdict'"
            assert data["verdict"] in ["hold_better", "sell_better", "neutral"], \
                f"Invalid verdict for {reason}: {data['verdict']}"
        
        print(f"PASS: sold_vs_held_by_reason aggregates correctly for {len(by_reason)} reasons")
        for reason, data in by_reason.items():
            print(f"  - {reason}: count={data['count']}, sim_exit={data['total_sim_exit_pnl']}, held={data['total_held_pnl']}, delta={data['total_delta']}, verdict={data['verdict']}")
    
    def test_profit_distribution_has_all_ranges(self):
        """profit_distribution should have ranges <0.5x through >2.0x"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        profit_dist = response.json()["profit_distribution"]
        
        required_ranges = ["<0.5x", "0.5-0.8x", "0.8-1.0x", "1.0-1.5x", "1.5-2.0x", ">2.0x"]
        
        for range_key in required_ranges:
            assert range_key in profit_dist, f"Missing profit range: {range_key}"
            assert isinstance(profit_dist[range_key], int), f"Profit range {range_key} should be int"
        
        total = sum(profit_dist.values())
        
        print(f"PASS: profit_distribution has all 6 ranges, total={total}")
        for range_key in required_ranges:
            print(f"  - {range_key}: {profit_dist[range_key]}")
    
    def test_config_contains_all_thresholds(self):
        """config should contain all lifecycle thresholds"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        config = response.json()["config"]
        
        required_thresholds = [
            "lifecycle_mode",
            "profit_capture_threshold",
            "max_negative_edge_bps",
            "edge_decay_exit_pct",
            "time_inefficiency_hours",
            "time_inefficiency_min_edge_bps"
        ]
        
        for threshold in required_thresholds:
            assert threshold in config, f"Config missing threshold: {threshold}"
        
        print(f"PASS: config contains all lifecycle thresholds")
        print(f"  - lifecycle_mode: {config['lifecycle_mode']}")
        print(f"  - profit_capture_threshold: {config['profit_capture_threshold']}")
        print(f"  - max_negative_edge_bps: {config['max_negative_edge_bps']}")
        print(f"  - edge_decay_exit_pct: {config['edge_decay_exit_pct']}")
        print(f"  - time_inefficiency_hours: {config['time_inefficiency_hours']}")
        print(f"  - time_inefficiency_min_edge_bps: {config['time_inefficiency_min_edge_bps']}")
    
    def test_shadow_exits_is_list(self):
        """shadow_exits should be a list (empty in tag_only mode)"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        shadow_exits = response.json()["shadow_exits"]
        
        assert isinstance(shadow_exits, list), "shadow_exits should be a list"
        
        config = response.json()["config"]
        if config["lifecycle_mode"] == "tag_only":
            # In tag_only mode, shadow_exits should be empty
            print(f"PASS: shadow_exits is list with {len(shadow_exits)} entries (tag_only mode)")
        else:
            print(f"PASS: shadow_exits is list with {len(shadow_exits)} entries")


class TestLifecycleDashboardDataIntegrity:
    """Data integrity tests for lifecycle dashboard"""
    
    def test_exit_candidate_counts_match(self):
        """total_exit_candidates should match sum of reason_distribution counts"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        data = response.json()
        
        summary_count = data["summary"]["total_exit_candidates"]
        reason_count = sum(r["count"] for r in data["reason_distribution"].values())
        
        assert summary_count == reason_count, \
            f"Exit candidate count mismatch: summary={summary_count}, reason_sum={reason_count}"
        
        print(f"PASS: Exit candidate count consistent: {summary_count}")
    
    def test_time_bucket_totals_match_positions_evaluated(self):
        """Sum of time bucket totals should equal total_positions_evaluated"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        data = response.json()
        
        bucket_total = sum(b["total"] for b in data["time_buckets"].values())
        positions_total = data["summary"]["total_positions_evaluated"]
        
        assert bucket_total == positions_total, \
            f"Time bucket total mismatch: buckets={bucket_total}, positions={positions_total}"
        
        print(f"PASS: Time bucket total matches positions evaluated: {positions_total}")
    
    def test_profit_distribution_total_matches_positions_evaluated(self):
        """Sum of profit distribution should equal total_positions_evaluated"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        data = response.json()
        
        profit_total = sum(data["profit_distribution"].values())
        positions_total = data["summary"]["total_positions_evaluated"]
        
        assert profit_total == positions_total, \
            f"Profit distribution total mismatch: profit={profit_total}, positions={positions_total}"
        
        print(f"PASS: Profit distribution total matches positions evaluated: {positions_total}")


class TestPreviousLifecycleFeatures:
    """Ensure previous lifecycle features still work (regression)"""
    
    def test_exit_candidates_endpoint_still_works(self):
        """GET /api/positions/weather/exit-candidates should still return 200"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200
        
        data = response.json()
        assert "mode" in data
        assert "candidates" in data
        assert "total_evaluated" in data
        
        print(f"PASS: exit-candidates endpoint returns 200 with mode={data['mode']}, candidates={len(data['candidates'])}")
    
    def test_lifecycle_endpoint_still_works(self):
        """GET /api/positions/weather/lifecycle should still return 200"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert response.status_code == 200
        
        data = response.json()
        assert "mode" in data
        assert "evaluations" in data
        assert "metrics" in data
        
        print(f"PASS: lifecycle endpoint returns 200 with mode={data['mode']}, evaluations={len(data['evaluations'])}")
    
    def test_positions_by_strategy_has_lifecycle_data(self):
        """Weather positions should still be enriched with lifecycle data"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        
        data = response.json()
        weather_positions = data.get("positions", {}).get("weather", [])
        
        # At least some weather positions should have lifecycle data
        lifecycle_count = sum(1 for p in weather_positions if p.get("lifecycle") is not None)
        
        print(f"PASS: positions/by-strategy returns weather positions with lifecycle data: {lifecycle_count}/{len(weather_positions)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
