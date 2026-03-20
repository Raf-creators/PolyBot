"""
Iteration 71: Shadow System Correctness Audit Tests
Tests for shadow sizing metadata, binary resolution, FP/FN tracking, 
meaningful agreement rate, and data isolation from live PnL/status.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestShadowReportAPI:
    """Tests for GET /api/shadow/report new fields"""
    
    def test_shadow_report_returns_sizing_section(self):
        """Shadow report should include sizing section with type=unit_size and per_signal_size=3.0"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        
        data = response.json()
        
        # If no evaluations yet, skip with info message
        if data.get("status") == "no_data":
            pytest.skip("Shadow system has no evaluations yet (expected after restart)")
        
        assert "sizing" in data, "Missing 'sizing' section in shadow report"
        sizing = data["sizing"]
        
        # Verify sizing type is unit_size
        assert sizing.get("type") == "unit_size", f"Expected type='unit_size', got '{sizing.get('type')}'"
        
        # Verify per_signal_size is 3.0 (the default)
        per_signal = sizing.get("per_signal_size")
        assert per_signal is not None, "Missing 'per_signal_size' in sizing"
        assert per_signal == 3.0, f"Expected per_signal_size=3.0, got {per_signal}"
        
        # Verify note includes unit-size clarification
        note = sizing.get("note", "")
        assert "unit-size" in note.lower() or "$3" in note, f"Sizing note should clarify unit-size: {note}"
        print(f"PASS: Shadow sizing section correct - type={sizing['type']}, per_signal_size={per_signal}")

    def test_shadow_report_returns_meaningful_evaluations(self):
        """Shadow report should include meaningful_evaluations and meaningful_agreement_rate"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        
        data = response.json()
        
        # If no evaluations yet, skip with info message
        if data.get("status") == "no_data":
            pytest.skip("Shadow system has no evaluations yet (expected after restart)")
        
        # Check total_evaluations exists
        assert "total_evaluations" in data, "Missing 'total_evaluations'"
        
        # Check meaningful_evaluations exists
        assert "meaningful_evaluations" in data, "Missing 'meaningful_evaluations'"
        meaningful_evals = data["meaningful_evaluations"]
        assert isinstance(meaningful_evals, int), "meaningful_evaluations should be an integer"
        
        # Check meaningful_agreement_rate in comparison
        assert "comparison" in data, "Missing 'comparison' section"
        comp = data["comparison"]
        assert "meaningful_agreement_rate" in comp, "Missing 'meaningful_agreement_rate' in comparison"
        mar = comp["meaningful_agreement_rate"]
        assert isinstance(mar, (int, float)), "meaningful_agreement_rate should be numeric"
        assert 0 <= mar <= 1, f"meaningful_agreement_rate should be between 0 and 1, got {mar}"
        
        print(f"PASS: meaningful_evaluations={meaningful_evals}, meaningful_agreement_rate={mar}")

    def test_shadow_report_returns_binary_win_rate(self):
        """Shadow report should include binary_win_rate and binary_resolved_count"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        
        data = response.json()
        
        # If no evaluations yet, skip with info message
        if data.get("status") == "no_data":
            pytest.skip("Shadow system has no evaluations yet (expected after restart)")
        
        assert "comparison" in data, "Missing 'comparison' section"
        
        shadow = data["comparison"].get("shadow", {})
        
        # binary_win_rate
        assert "binary_win_rate" in shadow, "Missing 'binary_win_rate' in shadow comparison"
        bwr = shadow["binary_win_rate"]
        assert isinstance(bwr, (int, float)), "binary_win_rate should be numeric"
        
        # binary_resolved_count
        assert "binary_resolved_count" in shadow, "Missing 'binary_resolved_count' in shadow comparison"
        brc = shadow["binary_resolved_count"]
        assert isinstance(brc, int), "binary_resolved_count should be integer"
        assert brc >= 0, "binary_resolved_count should be >= 0"
        
        print(f"PASS: binary_win_rate={bwr}, binary_resolved_count={brc}")

    def test_shadow_report_has_false_positive_negative_tracking(self):
        """Shadow report should track false_positives and false_negatives"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        
        data = response.json()
        
        # If no evaluations yet, skip with info message
        if data.get("status") == "no_data":
            pytest.skip("Shadow system has no evaluations yet (expected after restart)")
        
        comp = data.get("comparison", {})
        
        assert "false_positives" in comp, "Missing 'false_positives'"
        assert "false_negatives" in comp, "Missing 'false_negatives'"
        
        fp = comp["false_positives"]
        fn = comp["false_negatives"]
        
        assert isinstance(fp, int), "false_positives should be integer"
        assert isinstance(fn, int), "false_negatives should be integer"
        assert fp >= 0, "false_positives should be >= 0"
        assert fn >= 0, "false_negatives should be >= 0"
        
        print(f"PASS: false_positives={fp}, false_negatives={fn}")


class TestShadowPositionsAPI:
    """Tests for GET /api/shadow/positions"""
    
    def test_shadow_positions_returns_size_and_notional(self):
        """Shadow positions should include size and notional fields"""
        response = requests.get(f"{BASE_URL}/api/shadow/positions")
        assert response.status_code == 200
        
        positions = response.json()
        assert isinstance(positions, list), "Shadow positions should be a list"
        
        if len(positions) == 0:
            print("INFO: No open shadow positions to test, but endpoint works")
            return
        
        # Check first position has size and notional
        pos = positions[0]
        
        assert "size" in pos, f"Position missing 'size' field. Keys: {pos.keys()}"
        assert "notional" in pos, f"Position missing 'notional' field. Keys: {pos.keys()}"
        
        size = pos["size"]
        notional = pos["notional"]
        
        assert isinstance(size, (int, float)), f"size should be numeric, got {type(size)}"
        assert isinstance(notional, (int, float)), f"notional should be numeric, got {type(notional)}"
        assert size > 0, "size should be positive"
        
        # Verify notional = size * entry_price (approximately)
        entry_price = pos.get("entry_price", 0)
        expected_notional = size * entry_price
        assert abs(notional - expected_notional) < 0.01, f"notional={notional} should be size*entry_price={expected_notional}"
        
        print(f"PASS: Shadow positions have size={size}, notional={notional}")


class TestShadowClosedAPI:
    """Tests for GET /api/shadow/closed"""
    
    def test_shadow_closed_returns_resolution_type_and_is_binary_resolved(self):
        """Shadow closed trades should include resolution_type and is_binary_resolved"""
        response = requests.get(f"{BASE_URL}/api/shadow/closed?limit=50")
        assert response.status_code == 200
        
        closed = response.json()
        assert isinstance(closed, list), "Shadow closed should be a list"
        
        if len(closed) == 0:
            # This is expected if no markets have resolved to binary outcomes yet
            print("INFO: No closed shadow trades yet (expected - shadow was just restarted)")
            return
        
        # Check first closed trade has required fields
        trade = closed[0]
        
        assert "resolution_type" in trade, f"Closed trade missing 'resolution_type'. Keys: {trade.keys()}"
        resolution_type = trade["resolution_type"]
        valid_types = ["resolved_yes", "resolved_no", "expired_mtm", "no_data"]
        assert resolution_type in valid_types, f"resolution_type '{resolution_type}' not in {valid_types}"
        
        assert "is_binary_resolved" in trade, f"Closed trade missing 'is_binary_resolved'. Keys: {trade.keys()}"
        is_binary = trade["is_binary_resolved"]
        assert isinstance(is_binary, bool), "is_binary_resolved should be boolean"
        
        # If resolution_type starts with 'resolved_', is_binary_resolved should be True
        if resolution_type.startswith("resolved_"):
            assert is_binary is True, f"resolution_type={resolution_type} but is_binary_resolved=False"
        
        print(f"PASS: Closed trade has resolution_type={resolution_type}, is_binary_resolved={is_binary}")


class TestShadowIsolation:
    """Tests to verify shadow data does NOT contaminate live Overview/PnL"""
    
    def test_status_has_no_shadow_strategy(self):
        """GET /api/status should NOT contain any shadow strategy"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check components list
        components = data.get("components", [])
        for comp in components:
            comp_name = comp.get("name", "").lower()
            assert "shadow" not in comp_name, f"Shadow component found in status: {comp_name}"
        
        # Check strategies list
        strategies = data.get("strategies", [])
        for strat in strategies:
            strat_id = strat.get("strategy_id", "").lower()
            strat_name = strat.get("name", "").lower()
            assert "shadow" not in strat_id, f"Shadow strategy_id found in status: {strat_id}"
            assert "shadow" not in strat_name, f"Shadow strategy name found in status: {strat_name}"
        
        # Check stats if present
        stats = data.get("stats", {})
        for key in stats.keys():
            assert "shadow" not in key.lower(), f"Shadow key in stats: {key}"
        
        print(f"PASS: /api/status has no shadow contamination")

    def test_pnl_history_has_no_shadow_entries(self):
        """GET /api/analytics/pnl-history should NOT contain shadow strategy entries"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        
        data = response.json()
        points = data.get("points", [])
        
        shadow_entries = []
        for point in points:
            strategy = point.get("strategy", "").lower()
            if "shadow" in strategy:
                shadow_entries.append(point)
        
        assert len(shadow_entries) == 0, f"Found {len(shadow_entries)} shadow entries in pnl-history: {shadow_entries[:5]}"
        
        # Additional verification: check unique strategies
        unique_strategies = set(p.get("strategy", "") for p in points)
        for strat in unique_strategies:
            assert "shadow" not in strat.lower(), f"Shadow strategy in pnl-history: {strat}"
        
        print(f"PASS: /api/analytics/pnl-history has no shadow contamination. Strategies: {unique_strategies}")

    def test_status_stats_no_shadow_position_or_pnl(self):
        """Status stats should not include shadow position counts or PnL"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get("stats", {})
        
        # If stats exist, verify no shadow fields
        for key, value in stats.items():
            key_lower = key.lower()
            assert "shadow" not in key_lower, f"Shadow field in stats: {key}={value}"
        
        print(f"PASS: Status stats have no shadow fields")


class TestShadowEndpointStructure:
    """Tests for overall endpoint structure and response format"""
    
    def test_shadow_report_complete_structure(self):
        """Verify shadow/report has all expected top-level keys"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        
        data = response.json()
        
        # If no evaluations yet, skip with info message
        if data.get("status") == "no_data":
            pytest.skip("Shadow system has no evaluations yet (expected after restart)")
        
        required_keys = [
            "status",
            "total_evaluations",
            "meaningful_evaluations",
            "comparison",
            "rolling_pnl",
            "sizing",
            "config",
        ]
        
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"
        
        # Verify comparison sub-structure
        comp = data["comparison"]
        comp_required = ["live", "shadow", "agreement_rate", "meaningful_agreement_rate", "false_positives", "false_negatives"]
        for key in comp_required:
            assert key in comp, f"Missing comparison key: {key}"
        
        # Verify shadow sub-structure
        shadow = comp["shadow"]
        shadow_required = ["trade_count", "skip_count", "pnl_total", "win_rate", "binary_win_rate", "binary_resolved_count", "closed_trades", "open_positions"]
        for key in shadow_required:
            assert key in shadow, f"Missing shadow key: {key}"
        
        print(f"PASS: Shadow report has complete structure")

    def test_all_shadow_endpoints_respond(self):
        """Verify all shadow endpoints return 200"""
        endpoints = [
            "/api/shadow/report",
            "/api/shadow/evaluations?limit=10",
            "/api/shadow/positions",
            "/api/shadow/closed?limit=10",
        ]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 200, f"Endpoint {endpoint} returned {response.status_code}"
            print(f"PASS: {endpoint} returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
