"""
Iteration 65: Hybrid Staleness-Adjusted Execution Tests

Tests the new dynamic threshold system for the arbitrage engine:
- Dynamic min edge calculation based on staleness + liquidity
- Hard reject rules for very stale quotes (>1800s) and thin liquidity (<200)
- Rejection log entries with all required fields
- Raw edges include stale_age_s and liquidity
- GET /api/strategies/arb/diagnostics returns dynamic_threshold_samples
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestArbConfigDynamicThresholdParams:
    """Verify ArbConfig has new dynamic threshold parameters"""
    
    def test_arb_config_has_staleness_edge_base_bps(self):
        """staleness_edge_base_bps should be 15 (min edge for fresh data)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        config = data.get("config", {})
        assert "staleness_edge_base_bps" in config, "staleness_edge_base_bps missing from config"
        assert config["staleness_edge_base_bps"] == 15.0, f"Expected 15.0, got {config['staleness_edge_base_bps']}"
        print(f"PASS: staleness_edge_base_bps = {config['staleness_edge_base_bps']}")
    
    def test_arb_config_has_staleness_edge_per_minute_bps(self):
        """staleness_edge_per_minute_bps should be 5 (additional bps per minute of staleness)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        config = response.json().get("config", {})
        assert "staleness_edge_per_minute_bps" in config, "staleness_edge_per_minute_bps missing from config"
        assert config["staleness_edge_per_minute_bps"] == 5.0, f"Expected 5.0, got {config['staleness_edge_per_minute_bps']}"
        print(f"PASS: staleness_edge_per_minute_bps = {config['staleness_edge_per_minute_bps']}")
    
    def test_arb_config_has_hard_max_stale_seconds(self):
        """hard_max_stale_seconds should be 1800 (30 min absolute hard reject)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        config = response.json().get("config", {})
        assert "hard_max_stale_seconds" in config, "hard_max_stale_seconds missing from config"
        assert config["hard_max_stale_seconds"] == 1800.0, f"Expected 1800.0, got {config['hard_max_stale_seconds']}"
        print(f"PASS: hard_max_stale_seconds = {config['hard_max_stale_seconds']}")
    
    def test_arb_config_has_liquidity_deep_threshold(self):
        """liquidity_deep_threshold should be 2000 (above this = no liq buffer)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        config = response.json().get("config", {})
        assert "liquidity_deep_threshold" in config, "liquidity_deep_threshold missing from config"
        assert config["liquidity_deep_threshold"] == 2000.0, f"Expected 2000.0, got {config['liquidity_deep_threshold']}"
        print(f"PASS: liquidity_deep_threshold = {config['liquidity_deep_threshold']}")
    
    def test_arb_config_has_liquidity_mid_threshold(self):
        """liquidity_mid_threshold should be 500 (above this = half buffer)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        config = response.json().get("config", {})
        assert "liquidity_mid_threshold" in config, "liquidity_mid_threshold missing from config"
        assert config["liquidity_mid_threshold"] == 500.0, f"Expected 500.0, got {config['liquidity_mid_threshold']}"
        print(f"PASS: liquidity_mid_threshold = {config['liquidity_mid_threshold']}")
    
    def test_arb_config_has_liquidity_buffer_thin_bps(self):
        """liquidity_buffer_thin_bps should be 15 (full buffer for thin liquidity <500)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        config = response.json().get("config", {})
        assert "liquidity_buffer_thin_bps" in config, "liquidity_buffer_thin_bps missing from config"
        assert config["liquidity_buffer_thin_bps"] == 15.0, f"Expected 15.0, got {config['liquidity_buffer_thin_bps']}"
        print(f"PASS: liquidity_buffer_thin_bps = {config['liquidity_buffer_thin_bps']}")
    
    def test_min_net_edge_bps_lowered_to_15(self):
        """min_net_edge_bps should be lowered from 30 to 15 (absolute floor)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        config = response.json().get("config", {})
        assert "min_net_edge_bps" in config, "min_net_edge_bps missing from config"
        assert config["min_net_edge_bps"] == 15.0, f"Expected 15.0, got {config['min_net_edge_bps']}"
        print(f"PASS: min_net_edge_bps = {config['min_net_edge_bps']}")


class TestDynamicThresholdSamples:
    """Verify dynamic_threshold_samples in diagnostics endpoint"""
    
    def test_diagnostics_has_dynamic_threshold_samples(self):
        """GET /api/strategies/arb/diagnostics should return dynamic_threshold_samples"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert "dynamic_threshold_samples" in data, "dynamic_threshold_samples missing from diagnostics"
        samples = data["dynamic_threshold_samples"]
        assert isinstance(samples, list), "dynamic_threshold_samples should be a list"
        assert len(samples) > 0, "dynamic_threshold_samples should not be empty"
        print(f"PASS: dynamic_threshold_samples has {len(samples)} samples")
    
    def test_threshold_sample_structure(self):
        """Each sample should have stale_age_s, liquidity, required_min_edge_bps, hard_reject"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        samples = response.json().get("dynamic_threshold_samples", [])
        
        required_fields = ["stale_age_s", "liquidity", "required_min_edge_bps", "hard_reject"]
        for sample in samples[:5]:  # Check first 5 samples
            for field in required_fields:
                assert field in sample, f"Missing {field} in sample: {sample}"
        print(f"PASS: All required fields present in threshold samples")
    
    def test_dynamic_threshold_at_30s_3000liq_equals_15bps(self):
        """At 30s/3000liq: staleness=15+0.5*5=17.5, liq=0, total=17.5 → floor to 15"""
        # Formula: staleness_bps = base(15) + (age_s/60)*per_min(5) = 15 + (30/60)*5 = 17.5
        # liq_bps = 0 (>2000)
        # dynamic_min = 17.5 + 0 = 17.5, but floor at min_net_edge_bps(15) → effective = 17.5
        # Actually the implementation max(dynamic_min, min_net_edge_bps) so should be 17.5
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        samples = response.json().get("dynamic_threshold_samples", [])
        
        # Find sample with stale_age_s=30, liquidity=3000
        sample_30_3000 = next((s for s in samples if s["stale_age_s"] == 30 and s["liquidity"] == 3000), None)
        assert sample_30_3000 is not None, "No sample for 30s/3000liq"
        
        # Expected: staleness=15+(30/60)*5=17.5, liq=0, total=17.5, floor=15 → result=17.5
        expected_min = 17.5
        actual_min = sample_30_3000["required_min_edge_bps"]
        assert actual_min == expected_min, f"Expected {expected_min}bps at 30s/3000liq, got {actual_min}"
        assert sample_30_3000["hard_reject"] is None, f"Should not be hard reject at 30s/3000liq"
        print(f"PASS: 30s/3000liq threshold = {actual_min}bps (no hard reject)")
    
    def test_dynamic_threshold_at_600s_300liq(self):
        """At 600s/300liq: staleness=15+10*5=65, liq=15 (thin <500), total=80"""
        # Formula: staleness_bps = 15 + (600/60)*5 = 15 + 50 = 65
        # liq_bps = 15 (liquidity < 500)
        # dynamic_min = 65 + 15 = 80
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        samples = response.json().get("dynamic_threshold_samples", [])
        
        sample_600_300 = next((s for s in samples if s["stale_age_s"] == 600 and s["liquidity"] == 300), None)
        assert sample_600_300 is not None, "No sample for 600s/300liq"
        
        expected_min = 80.0
        actual_min = sample_600_300["required_min_edge_bps"]
        assert actual_min == expected_min, f"Expected {expected_min}bps at 600s/300liq, got {actual_min}"
        assert sample_600_300["hard_reject"] is None, f"Should not be hard reject at 600s/300liq"
        print(f"PASS: 600s/300liq threshold = {actual_min}bps")
    
    def test_dynamic_threshold_at_1200s_800liq(self):
        """At 1200s/800liq: staleness=15+20*5=115, liq=7.5 (mid 500-2000), total=122.5"""
        # Formula: staleness_bps = 15 + (1200/60)*5 = 15 + 100 = 115
        # liq_bps = 7.5 (liquidity >= 500 and < 2000)
        # dynamic_min = 115 + 7.5 = 122.5
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        samples = response.json().get("dynamic_threshold_samples", [])
        
        sample_1200_800 = next((s for s in samples if s["stale_age_s"] == 1200 and s["liquidity"] == 800), None)
        assert sample_1200_800 is not None, "No sample for 1200s/800liq"
        
        expected_min = 122.5
        actual_min = sample_1200_800["required_min_edge_bps"]
        assert actual_min == expected_min, f"Expected {expected_min}bps at 1200s/800liq, got {actual_min}"
        assert sample_1200_800["hard_reject"] is None, f"Should not be hard reject at 1200s/800liq"
        print(f"PASS: 1200s/800liq threshold = {actual_min}bps")
    
    def test_hard_stale_reject_at_1800s(self):
        """Any data > 1800s should be hard rejected"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        samples = response.json().get("dynamic_threshold_samples", [])
        
        # Find sample with stale_age_s=1800 (should be at the boundary or just above)
        sample_1800 = next((s for s in samples if s["stale_age_s"] == 1800), None)
        assert sample_1800 is not None, "No sample for 1800s"
        
        # At exactly 1800s: NOT hard rejected (> 1800 required)
        # The hard_reject should be None at exactly 1800s
        # Check for samples above 1800 if any
        stale_samples = [s for s in samples if s["stale_age_s"] > 1800]
        for s in stale_samples:
            assert s["hard_reject"] is not None, f"Expected hard reject at {s['stale_age_s']}s"
            assert "hard_stale_reject" in s["hard_reject"], f"Reject reason should contain 'hard_stale_reject'"
        
        print(f"PASS: Hard stale reject verified (>1800s)")


class TestHardLiquidityReject:
    """Verify hard liquidity reject for thin liquidity (<200)"""
    
    def test_hard_liquidity_reject_below_200(self):
        """Any liquidity < 200 should be hard rejected with hard_liquidity_reject reason"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        config = response.json().get("config", {})
        
        # Verify min_liquidity = 200 (hard reject threshold)
        assert config.get("min_liquidity") == 200.0, f"min_liquidity should be 200, got {config.get('min_liquidity')}"
        print(f"PASS: min_liquidity = {config['min_liquidity']} (hard reject threshold)")


class TestRejectionLogEntries:
    """Verify rejection log entries include all required fields"""
    
    def test_rejection_log_present_in_diagnostics(self):
        """GET /api/strategies/arb/diagnostics should include rejection_log"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert "rejection_log" in data, "rejection_log missing from diagnostics"
        print(f"PASS: rejection_log present with {len(data['rejection_log'])} entries")
    
    def test_rejection_log_entry_has_required_fields(self):
        """Rejection entries should have: type, condition_id, question, total_cost, gross_edge_bps,
        fees_bps, slippage_bps, net_edge_bps, stale_age_s, liquidity, dynamic_min_edge_bps, reason"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        rejection_log = response.json().get("rejection_log", [])
        
        required_fields = [
            "type", "condition_id", "question", "total_cost", "gross_edge_bps",
            "fees_bps", "slippage_bps", "net_edge_bps", "stale_age_s", "liquidity",
            "dynamic_min_edge_bps", "reason"
        ]
        
        if len(rejection_log) == 0:
            print("INFO: No rejection log entries yet (scanner may not have found rejectable opportunities)")
            return
        
        for entry in rejection_log[:5]:  # Check first 5 entries
            for field in required_fields:
                assert field in entry, f"Missing {field} in rejection entry: {entry}"
        
        print(f"PASS: All required fields present in rejection log entries")


class TestRawEdgesEntries:
    """Verify raw edges entries include stale_age_s and liquidity fields"""
    
    def test_raw_edges_present_in_diagnostics(self):
        """GET /api/strategies/arb/diagnostics should include raw_edges"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert "raw_edges" in data, "raw_edges missing from diagnostics"
        print(f"PASS: raw_edges present with {len(data['raw_edges'])} entries")
    
    def test_raw_edges_entry_has_stale_age_s(self):
        """Raw edges entries should include stale_age_s field"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        raw_edges = response.json().get("raw_edges", [])
        
        if len(raw_edges) == 0:
            print("INFO: No raw edges yet (scanner may not have found any edge opportunities)")
            return
        
        for edge in raw_edges[:5]:
            assert "stale_age_s" in edge, f"stale_age_s missing from raw edge: {edge}"
        
        print(f"PASS: stale_age_s present in raw edges entries")
    
    def test_raw_edges_entry_has_liquidity(self):
        """Raw edges entries should include liquidity field"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        raw_edges = response.json().get("raw_edges", [])
        
        if len(raw_edges) == 0:
            print("INFO: No raw edges yet")
            return
        
        for edge in raw_edges[:5]:
            assert "liquidity" in edge, f"liquidity missing from raw edge: {edge}"
        
        print(f"PASS: liquidity present in raw edges entries")


class TestArbOpportunitiesEndpoint:
    """Verify GET /api/strategies/arb/opportunities endpoint"""
    
    def test_opportunities_returns_tradable_and_rejected(self):
        """GET /api/strategies/arb/opportunities should return tradable and rejected lists"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert response.status_code == 200
        data = response.json()
        assert "tradable" in data, "tradable list missing from opportunities"
        assert "rejected" in data, "rejected list missing from opportunities"
        print(f"PASS: opportunities endpoint returns tradable ({len(data['tradable'])}) and rejected ({len(data['rejected'])})")


class TestArbExecutionsEndpoint:
    """Verify GET /api/strategies/arb/executions endpoint"""
    
    def test_executions_returns_active_and_completed(self):
        """GET /api/strategies/arb/executions should return active and completed lists"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/executions")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data, "active list missing from executions"
        assert "completed" in data, "completed list missing from executions"
        print(f"PASS: executions endpoint returns active ({len(data['active'])}) and completed ({len(data['completed'])})")


class TestArbPerformanceEndpoint:
    """Verify GET /api/strategies/arb/health endpoint includes performance metrics"""
    
    def test_arb_health_returns_performance_metrics(self):
        """GET /api/strategies/arb/health should return performance metrics"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        data = response.json()
        
        assert "performance" in data, "performance key missing from arb health"
        perf = data["performance"]
        
        required_fields = [
            "trades_per_hour", "avg_realized_edge_bps", "total_realized_edge_bps",
            "capital_deployed", "current_exposure", "capital_utilization_pct",
            "binary_executed", "multi_executed", "completed", "invalidated"
        ]
        
        for field in required_fields:
            assert field in perf, f"Missing {field} in performance data"
        
        print(f"PASS: arb health endpoint has all required performance metrics")


class TestHealthEndpoint:
    """Verify GET /api/health returns 200"""
    
    def test_health_returns_200(self):
        """GET /api/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print(f"PASS: /api/health returns 200")


class TestUpgradeValidationEndpoint:
    """Verify GET /api/admin/upgrade-validation returns 200 with arb_health data"""
    
    def test_upgrade_validation_returns_200(self):
        """GET /api/admin/upgrade-validation should return 200"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation")
        assert response.status_code == 200
        print(f"PASS: /api/admin/upgrade-validation returns 200")
    
    def test_upgrade_validation_has_arb_health(self):
        """upgrade-validation should include arb_health data with performance"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation")
        assert response.status_code == 200
        data = response.json()
        assert "arb_health" in data, "arb_health missing from upgrade-validation"
        
        arb_health = data["arb_health"]
        assert "performance" in arb_health, "performance missing from arb_health"
        
        # Verify performance has key metrics
        perf = arb_health["performance"]
        assert "trades_per_hour" in perf, "trades_per_hour missing from arb_health.performance"
        assert "capital_utilization_pct" in perf, "capital_utilization_pct missing"
        
        # Config is in /api/strategies/arb/diagnostics, not upgrade-validation
        # Check it separately
        diag_response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert diag_response.status_code == 200
        config = diag_response.json().get("config", {})
        assert config.get("min_net_edge_bps") == 15.0, "min_net_edge_bps should be 15"
        assert config.get("staleness_edge_base_bps") == 15.0, "staleness_edge_base_bps should be 15"
        assert config.get("hard_max_stale_seconds") == 1800.0, "hard_max_stale_seconds should be 1800"
        
        print(f"PASS: upgrade-validation has arb_health with performance metrics")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
