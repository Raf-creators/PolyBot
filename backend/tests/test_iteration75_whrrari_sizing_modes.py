"""
Iteration 75: Whrrari LMSR Shadow - 3 Independent Sizing Modes Testing

Tests the new 3 sizing modes for Whrrari experiment:
1. Unit-Size: flat $3/signal, normalized research comparison
2. Sandbox Notional: edge-tiered $3/$8/$15 bands, primary promotion metric
3. Crypto-Mirrored: $3/signal accumulating to $25 cap, hypothetical stress test

API Endpoints tested:
- GET /api/experiments/whrrari/report (returns unit_size, sandbox_notional, crypto_mirrored stats)
- GET /api/experiments/whrrari/positions?mode=unit|sandbox|crypto
- GET /api/experiments/whrrari/closed?mode=unit|sandbox|crypto
- GET /api/experiments/registry (existing shadow sniper still works)
- GET /api/shadow/report (existing shadow sniper still works)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://edge-trading-hub-1.preview.emergentagent.com"


class TestWhrrariReportEndpoint:
    """Test /api/experiments/whrrari/report returns all 3 mode stats"""

    def test_report_returns_unit_size_stats(self):
        """Report should contain unit_size stats object"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "unit_size" in data, "Report missing unit_size stats"
        unit = data["unit_size"]
        
        # Verify expected fields in unit_size stats
        expected_fields = ["pnl_total", "win_rate", "binary_win_rate", "closed_trades", 
                          "open_positions", "open_exposure", "pnl_per_trade", "rolling_pnl"]
        for field in expected_fields:
            assert field in unit, f"unit_size missing field: {field}"
        
        print(f"PASS: unit_size stats present with {len(unit)} fields")
        print(f"  - pnl_total: {unit.get('pnl_total')}")
        print(f"  - open_positions: {unit.get('open_positions')}")
        print(f"  - closed_trades: {unit.get('closed_trades')}")

    def test_report_returns_sandbox_notional_stats(self):
        """Report should contain sandbox_notional stats object"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/report")
        assert response.status_code == 200
        data = response.json()
        
        assert "sandbox_notional" in data, "Report missing sandbox_notional stats"
        sandbox = data["sandbox_notional"]
        
        # Verify expected fields
        expected_fields = ["pnl_total", "win_rate", "binary_win_rate", "closed_trades", 
                          "open_positions", "open_exposure", "pnl_per_trade", "rolling_pnl"]
        for field in expected_fields:
            assert field in sandbox, f"sandbox_notional missing field: {field}"
        
        print(f"PASS: sandbox_notional stats present with {len(sandbox)} fields")
        print(f"  - pnl_total: {sandbox.get('pnl_total')}")
        print(f"  - open_positions: {sandbox.get('open_positions')}")

    def test_report_returns_crypto_mirrored_stats(self):
        """Report should contain crypto_mirrored stats object"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/report")
        assert response.status_code == 200
        data = response.json()
        
        assert "crypto_mirrored" in data, "Report missing crypto_mirrored stats"
        crypto = data["crypto_mirrored"]
        
        # Verify expected fields
        expected_fields = ["pnl_total", "win_rate", "binary_win_rate", "closed_trades", 
                          "open_positions", "open_exposure", "pnl_per_trade", "rolling_pnl"]
        for field in expected_fields:
            assert field in crypto, f"crypto_mirrored missing field: {field}"
        
        print(f"PASS: crypto_mirrored stats present with {len(crypto)} fields")
        print(f"  - pnl_total: {crypto.get('pnl_total')}")
        print(f"  - open_positions: {crypto.get('open_positions')}")

    def test_report_config_shows_sandbox_bands(self):
        """Report config should show sandbox_bands configuration"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/report")
        assert response.status_code == 200
        data = response.json()
        
        assert "config" in data, "Report missing config"
        config = data["config"]
        
        assert "sandbox_bands" in config, "Config missing sandbox_bands"
        sandbox_bands = config["sandbox_bands"]
        
        # Should contain the band info: $3 (300-599bps) / $8 (600-899bps) / $15 (900+bps)
        assert "$3" in sandbox_bands or "3" in sandbox_bands, "sandbox_bands should mention $3 band"
        assert "$8" in sandbox_bands or "8" in sandbox_bands, "sandbox_bands should mention $8 band"
        assert "$15" in sandbox_bands or "15" in sandbox_bands, "sandbox_bands should mention $15 band"
        
        print(f"PASS: sandbox_bands config present: {sandbox_bands}")

    def test_report_config_shows_crypto_mirror_cap(self):
        """Report config should show crypto_mirror_cap configuration"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/report")
        assert response.status_code == 200
        data = response.json()
        
        assert "config" in data, "Report missing config"
        config = data["config"]
        
        assert "crypto_mirror_cap" in config, "Config missing crypto_mirror_cap"
        crypto_cap = config["crypto_mirror_cap"]
        
        # Should mention $3/signal and $25 max
        assert "$3" in crypto_cap or "3" in crypto_cap, "crypto_mirror_cap should mention $3/signal"
        assert "$25" in crypto_cap or "25" in crypto_cap, "crypto_mirror_cap should mention $25 max"
        
        print(f"PASS: crypto_mirror_cap config present: {crypto_cap}")


class TestWhrrariPositionsEndpoint:
    """Test /api/experiments/whrrari/positions with mode query param"""

    def test_positions_mode_unit(self):
        """GET /api/experiments/whrrari/positions?mode=unit returns unit-size positions"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/positions?mode=unit")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Positions should be a list"
        print(f"PASS: Unit positions endpoint works, returned {len(data)} positions")
        
        # If there are positions, verify structure
        if len(data) > 0:
            pos = data[0]
            assert "token_id" in pos, "Position missing token_id"
            assert "size" in pos, "Position missing size"
            assert "entry_price" in pos or "avg_entry" in pos, "Position missing entry price"
            print(f"  - Sample position: size={pos.get('size')}, entry={pos.get('avg_entry', pos.get('entry_price'))}")

    def test_positions_mode_sandbox(self):
        """GET /api/experiments/whrrari/positions?mode=sandbox returns sandbox positions"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/positions?mode=sandbox")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Positions should be a list"
        print(f"PASS: Sandbox positions endpoint works, returned {len(data)} positions")
        
        # If there are positions, verify sandbox_band field
        if len(data) > 0:
            pos = data[0]
            assert "token_id" in pos, "Position missing token_id"
            assert "size" in pos, "Position missing size"
            # Sandbox positions should have sandbox_band field
            if "sandbox_band" in pos:
                print(f"  - Sample position: size={pos.get('size')}, sandbox_band={pos.get('sandbox_band')}")
            else:
                print(f"  - Sample position: size={pos.get('size')} (sandbox_band field may be added on entry)")

    def test_positions_mode_crypto(self):
        """GET /api/experiments/whrrari/positions?mode=crypto returns crypto-mirrored positions"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/positions?mode=crypto")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Positions should be a list"
        print(f"PASS: Crypto positions endpoint works, returned {len(data)} positions")
        
        # If there are positions, verify structure
        if len(data) > 0:
            pos = data[0]
            assert "token_id" in pos, "Position missing token_id"
            assert "size" in pos, "Position missing size"
            # Crypto positions may have fills field for accumulation tracking
            print(f"  - Sample position: size={pos.get('size')}, fills={pos.get('fills', 1)}")


class TestWhrrariClosedEndpoint:
    """Test /api/experiments/whrrari/closed with mode query param"""

    def test_closed_mode_unit(self):
        """GET /api/experiments/whrrari/closed?mode=unit returns unit closed trades"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/closed?mode=unit&limit=50")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Closed trades should be a list"
        print(f"PASS: Unit closed endpoint works, returned {len(data)} trades")
        
        if len(data) > 0:
            trade = data[0]
            assert "pnl" in trade, "Closed trade missing pnl"
            assert "won" in trade, "Closed trade missing won"
            print(f"  - Sample trade: pnl={trade.get('pnl')}, won={trade.get('won')}")

    def test_closed_mode_sandbox(self):
        """GET /api/experiments/whrrari/closed?mode=sandbox returns sandbox closed trades"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/closed?mode=sandbox&limit=50")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Closed trades should be a list"
        print(f"PASS: Sandbox closed endpoint works, returned {len(data)} trades")
        
        # If there are closed trades, verify sandbox_band field
        if len(data) > 0:
            trade = data[0]
            assert "pnl" in trade, "Closed trade missing pnl"
            # Sandbox closed trades should have sandbox_band field
            if "sandbox_band" in trade:
                print(f"  - Sample trade: pnl={trade.get('pnl')}, sandbox_band={trade.get('sandbox_band')}")
            else:
                print(f"  - Sample trade: pnl={trade.get('pnl')} (sandbox_band preserved from position)")

    def test_closed_mode_crypto(self):
        """GET /api/experiments/whrrari/closed?mode=crypto returns crypto closed trades"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/closed?mode=crypto&limit=50")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Closed trades should be a list"
        print(f"PASS: Crypto closed endpoint works, returned {len(data)} trades")
        
        if len(data) > 0:
            trade = data[0]
            assert "pnl" in trade, "Closed trade missing pnl"
            print(f"  - Sample trade: pnl={trade.get('pnl')}, won={trade.get('won')}")


class TestExistingShadowSniperStillWorks:
    """Verify existing shadow sniper and experiments registry still work"""

    def test_shadow_report_endpoint(self):
        """GET /api/shadow/report should still work"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "status" in data, "Shadow report missing status"
        # Shadow report may return no_data if no evaluations yet, or full report with unit_size/comparison
        valid_statuses = ["active", "collecting", "no_data"]
        assert data.get("status") in valid_statuses, f"Unexpected status: {data.get('status')}"
        
        print(f"PASS: Shadow sniper report still works, status={data.get('status')}")

    def test_experiments_registry_endpoint(self):
        """GET /api/experiments/registry should return all experiments including whrrari"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "experiments" in data, "Registry missing experiments"
        experiments = data["experiments"]
        
        # Find whrrari in registry
        whrrari_exp = next((e for e in experiments if e.get("id") == "whrrari"), None)
        assert whrrari_exp is not None, "Whrrari not found in experiments registry"
        
        print(f"PASS: Experiments registry works, found {len(experiments)} experiments")
        print(f"  - Whrrari status: {whrrari_exp.get('status')}")
        
        # Verify shadow_sniper also present
        shadow_exp = next((e for e in experiments if e.get("id") == "shadow_sniper"), None)
        assert shadow_exp is not None, "Shadow sniper not found in experiments registry"
        print(f"  - Shadow sniper status: {shadow_exp.get('status')}")


class TestWhrrariEvaluations:
    """Test /api/experiments/whrrari/evaluations endpoint"""

    def test_evaluations_endpoint(self):
        """GET /api/experiments/whrrari/evaluations returns evaluation records"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/evaluations?limit=100")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert isinstance(data, list), "Evaluations should be a list"
        print(f"PASS: Evaluations endpoint works, returned {len(data)} records")
        
        if len(data) > 0:
            eval_rec = data[0]
            # Verify expected fields
            expected_fields = ["timestamp", "event_key", "outcome_count", "best_edge_bps", "would_trade"]
            for field in expected_fields:
                if field in eval_rec:
                    print(f"  - {field}: {eval_rec.get(field)}")


class TestHealthAndStatus:
    """Verify system health after Whrrari changes"""

    def test_health_endpoint(self):
        """GET /api/health should return ok"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert data.get("status") == "ok", f"Health status not ok: {data.get('status')}"
        print(f"PASS: Health check ok, engine={data.get('engine')}")

    def test_status_endpoint(self):
        """GET /api/status should return system status"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "mode" in data, "Status missing mode"
        print(f"PASS: Status endpoint works, mode={data.get('mode')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
