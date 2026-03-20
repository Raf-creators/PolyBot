"""
Iteration 74: Quant Lab Incubator Testing
Tests Wave 1 (active) and Wave 2 (planned) shadow experiments.
All experiments are 100% SHADOW ONLY - no live fills.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestExperimentsRegistry:
    """Test /api/experiments/registry returns all 6 experiments"""
    
    def test_registry_returns_all_experiments(self):
        """Registry should return 6 experiments total"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "experiments" in data, "Response should have 'experiments' key"
        
        experiments = data["experiments"]
        assert len(experiments) == 6, f"Expected 6 experiments, got {len(experiments)}"
        
        # Verify all expected experiment IDs are present
        exp_ids = [e["id"] for e in experiments]
        expected_ids = ["shadow_sniper", "moondev", "phantom", "whrrari", "marik", "argona"]
        for eid in expected_ids:
            assert eid in exp_ids, f"Missing experiment: {eid}"
        
        print(f"PASS: Registry returns all 6 experiments: {exp_ids}")
    
    def test_registry_active_experiments(self):
        """Wave 1 experiments should be active, Wave 2 should be planned"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        
        experiments = {e["id"]: e for e in response.json()["experiments"]}
        
        # Wave 0 + Wave 1: should be active
        active_expected = ["shadow_sniper", "moondev", "phantom", "whrrari"]
        for eid in active_expected:
            status = experiments[eid].get("status", "unknown")
            assert status == "active", f"{eid} should be active, got {status}"
        
        # Wave 2: should be planned
        planned_expected = ["marik", "argona"]
        for eid in planned_expected:
            status = experiments[eid].get("status", "unknown")
            assert status == "planned", f"{eid} should be planned, got {status}"
        
        print("PASS: Active/planned status correct for all experiments")


class TestMoonDevExperiment:
    """Test MoonDev Short Window shadow experiment endpoints"""
    
    def test_moondev_report(self):
        """GET /api/experiments/moondev/report returns valid report"""
        response = requests.get(f"{BASE_URL}/api/experiments/moondev/report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify required fields
        assert "status" in data, "Report should have 'status'"
        assert "experiment" in data, "Report should have 'experiment'"
        assert "metrics" in data, "Report should have 'metrics'"
        assert "unit_size" in data, "Report should have 'unit_size'"
        assert "live_equivalent" in data, "Report should have 'live_equivalent'"
        
        # Verify metrics structure
        metrics = data["metrics"]
        required_metrics = ["total_signals_received", "window_filtered_out", "evaluated", "would_trade"]
        for m in required_metrics:
            assert m in metrics, f"Missing metric: {m}"
        
        print(f"PASS: MoonDev report valid - status={data['status']}, evaluated={metrics['evaluated']}")
    
    def test_moondev_evaluations(self):
        """GET /api/experiments/moondev/evaluations returns records with window field"""
        response = requests.get(f"{BASE_URL}/api/experiments/moondev/evaluations?limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Evaluations should be a list"
        
        # If there are evaluations, verify structure
        if len(data) > 0:
            eval_record = data[0]
            assert "window" in eval_record, "Evaluation should have 'window' field"
            assert eval_record["window"] in ["5m", "15m"], f"Window should be 5m or 15m, got {eval_record['window']}"
            print(f"PASS: MoonDev evaluations valid - {len(data)} records, window={eval_record['window']}")
        else:
            print("PASS: MoonDev evaluations endpoint works (no data yet)")
    
    def test_moondev_positions(self):
        """GET /api/experiments/moondev/positions returns positions with window field"""
        response = requests.get(f"{BASE_URL}/api/experiments/moondev/positions?mode=unit")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Positions should be a list"
        
        if len(data) > 0:
            pos = data[0]
            assert "window" in pos, "Position should have 'window' field"
            print(f"PASS: MoonDev positions valid - {len(data)} open positions")
        else:
            print("PASS: MoonDev positions endpoint works (no positions yet)")
    
    def test_moondev_closed(self):
        """GET /api/experiments/moondev/closed returns closed trades"""
        response = requests.get(f"{BASE_URL}/api/experiments/moondev/closed?mode=unit&limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Closed trades should be a list"
        print(f"PASS: MoonDev closed endpoint works - {len(data)} closed trades")


class TestPhantomSpreadExperiment:
    """Test Phantom Spread shadow experiment endpoints"""
    
    def test_phantom_report(self):
        """GET /api/experiments/phantom/report returns valid report"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify required fields
        assert "status" in data, "Report should have 'status'"
        assert "experiment" in data, "Report should have 'experiment'"
        assert "metrics" in data, "Report should have 'metrics'"
        
        # Verify metrics structure
        metrics = data["metrics"]
        required_metrics = ["total_scans", "pairs_scanned", "dislocations_found", "hypothetical_trades"]
        for m in required_metrics:
            assert m in metrics, f"Missing metric: {m}"
        
        print(f"PASS: Phantom report valid - status={data['status']}, scans={metrics['total_scans']}")
    
    def test_phantom_evaluations(self):
        """GET /api/experiments/phantom/evaluations returns records with spread fields"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/evaluations?limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Evaluations should be a list"
        
        if len(data) > 0:
            eval_record = data[0]
            required_fields = ["yes_price", "no_price", "price_sum", "spread_bps"]
            for f in required_fields:
                assert f in eval_record, f"Evaluation should have '{f}' field"
            print(f"PASS: Phantom evaluations valid - {len(data)} records, spread_bps={eval_record.get('spread_bps')}")
        else:
            print("PASS: Phantom evaluations endpoint works (no data yet)")
    
    def test_phantom_positions(self):
        """GET /api/experiments/phantom/positions returns positions with spread_bps_at_entry"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/positions")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Positions should be a list"
        
        if len(data) > 0:
            pos = data[0]
            assert "spread_bps_at_entry" in pos, "Position should have 'spread_bps_at_entry' field"
            print(f"PASS: Phantom positions valid - {len(data)} open positions")
        else:
            print("PASS: Phantom positions endpoint works (no positions yet)")
    
    def test_phantom_closed(self):
        """GET /api/experiments/phantom/closed returns closed trades"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/closed?limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Closed trades should be a list"
        print(f"PASS: Phantom closed endpoint works - {len(data)} closed trades")


class TestWhrrariLMSRExperiment:
    """Test Whrrari LMSR shadow experiment endpoints"""
    
    def test_whrrari_report(self):
        """GET /api/experiments/whrrari/report returns valid report"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Verify required fields
        assert "status" in data, "Report should have 'status'"
        assert "experiment" in data, "Report should have 'experiment'"
        assert "metrics" in data, "Report should have 'metrics'"
        
        # Verify metrics structure
        metrics = data["metrics"]
        required_metrics = ["total_scans", "groups_found", "groups_evaluated", "deviations_found"]
        for m in required_metrics:
            assert m in metrics, f"Missing metric: {m}"
        
        print(f"PASS: Whrrari report valid - status={data['status']}, scans={metrics['total_scans']}")
    
    def test_whrrari_evaluations(self):
        """GET /api/experiments/whrrari/evaluations returns records with LMSR fields"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/evaluations?limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Evaluations should be a list"
        
        if len(data) > 0:
            eval_record = data[0]
            required_fields = ["outcome_count", "price_sum", "best_edge_bps"]
            for f in required_fields:
                assert f in eval_record, f"Evaluation should have '{f}' field"
            # deviations array is optional but should be present if there are evaluations
            if "deviations" in eval_record:
                assert isinstance(eval_record["deviations"], list), "deviations should be a list"
            print(f"PASS: Whrrari evaluations valid - {len(data)} records, best_edge_bps={eval_record.get('best_edge_bps')}")
        else:
            print("PASS: Whrrari evaluations endpoint works (no data yet)")
    
    def test_whrrari_positions(self):
        """GET /api/experiments/whrrari/positions returns positions with LMSR fields"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/positions")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Positions should be a list"
        
        if len(data) > 0:
            pos = data[0]
            required_fields = ["edge_bps_at_entry", "fair_prob_at_entry"]
            for f in required_fields:
                assert f in pos, f"Position should have '{f}' field"
            print(f"PASS: Whrrari positions valid - {len(data)} open positions")
        else:
            print("PASS: Whrrari positions endpoint works (no positions yet)")
    
    def test_whrrari_closed(self):
        """GET /api/experiments/whrrari/closed returns closed trades"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/closed?limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Closed trades should be a list"
        print(f"PASS: Whrrari closed endpoint works - {len(data)} closed trades")


class TestExistingShadowSniper:
    """Test existing shadow sniper endpoints still work"""
    
    def test_shadow_report(self):
        """GET /api/shadow/report returns valid report"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "status" in data, "Report should have 'status'"
        # When active, should have unit_size and live_equivalent
        # When no_data, may just have status and message
        if data.get("status") == "active":
            assert "unit_size" in data, "Active report should have 'unit_size'"
            assert "live_equivalent" in data, "Active report should have 'live_equivalent'"
        
        print(f"PASS: Shadow sniper report valid - status={data['status']}")
    
    def test_shadow_evaluations(self):
        """GET /api/shadow/evaluations returns evaluation records"""
        response = requests.get(f"{BASE_URL}/api/shadow/evaluations?limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Evaluations should be a list"
        print(f"PASS: Shadow sniper evaluations - {len(data)} records")
    
    def test_shadow_positions(self):
        """GET /api/shadow/positions returns positions"""
        response = requests.get(f"{BASE_URL}/api/shadow/positions?mode=unit")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Positions should be a list"
        print(f"PASS: Shadow sniper positions - {len(data)} open")
    
    def test_shadow_closed(self):
        """GET /api/shadow/closed returns closed trades"""
        response = requests.get(f"{BASE_URL}/api/shadow/closed?mode=unit&limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list), "Closed trades should be a list"
        print(f"PASS: Shadow sniper closed - {len(data)} trades")


class TestEpoch3Reset:
    """Test Epoch 3 reset executed correctly"""
    
    def test_status_endpoint(self):
        """GET /api/status should show system running normally"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "stats" in data, "Status should have 'stats'"
        assert "mode" in data, "Status should have 'mode'"
        
        print(f"PASS: Status endpoint working - mode={data['mode']}")
    
    def test_pnl_history_baseline(self):
        """GET /api/analytics/pnl-history should show reset baseline"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # PnL history should have current_pnl
        assert "current_pnl" in data, "PnL history should have current_pnl"
        
        print(f"PASS: PnL history endpoint working - current_pnl={data.get('current_pnl')}")
    
    def test_health_endpoint(self):
        """GET /api/health should return ok"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "ok", f"Health status should be 'ok', got {data.get('status')}"
        
        print(f"PASS: Health endpoint ok - engine={data.get('engine')}")


class TestWave2PlannedExperiments:
    """Test that Wave 2 experiments are properly marked as planned"""
    
    def test_marik_in_registry(self):
        """Marik Latency should be in registry as planned"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        
        experiments = {e["id"]: e for e in response.json()["experiments"]}
        assert "marik" in experiments, "Marik should be in registry"
        assert experiments["marik"]["status"] == "planned", "Marik should be planned"
        
        print(f"PASS: Marik Latency is planned - {experiments['marik']['name']}")
    
    def test_argona_in_registry(self):
        """Argona Macro should be in registry as planned"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        
        experiments = {e["id"]: e for e in response.json()["experiments"]}
        assert "argona" in experiments, "Argona should be in registry"
        assert experiments["argona"]["status"] == "planned", "Argona should be planned"
        
        print(f"PASS: Argona Macro is planned - {experiments['argona']['name']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
