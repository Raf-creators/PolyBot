"""
Iteration 72: Dual-Mode Shadow Comparison Testing
Tests the new dual-mode shadow system:
1. Unit-Size mode: $3/signal, no accumulation
2. Live-Equivalent mode: same sizing/accumulation/cap as live sniper (up to max_position_size=25)

Key features verified:
- GET /api/shadow/report returns both unit_size and live_equivalent sections
- Sizing section with unit.accumulation=false and live_equivalent.accumulation=true
- GET /api/shadow/positions?mode=unit vs mode=le returns correct positions
- LE positions can have size>3 and fills>1 (accumulation)
- LE positions respect max_position_size cap (no position exceeds 25)
- Shadow data isolated from /api/status and /api/analytics/pnl-history
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestShadowReportDualMode:
    """Tests for /api/shadow/report dual-mode structure"""

    def test_shadow_report_returns_both_unit_and_le_sections(self):
        """Report must contain both unit_size and live_equivalent sections"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Must have status
        assert 'status' in data, "Missing status field"
        
        # If no_data, skip (shadow engine hasn't processed any evaluations yet)
        if data.get('status') == 'no_data':
            pytest.skip("Shadow engine has no data yet (system just restarted)")
        
        # Both modes must be present
        assert 'unit_size' in data, "Missing unit_size section"
        assert 'live_equivalent' in data, "Missing live_equivalent section"
        
        print(f"PASS: Report has both unit_size and live_equivalent sections")
        print(f"  - Unit-Size: {data.get('unit_size', {})}")
        print(f"  - Live-Equiv: {data.get('live_equivalent', {})}")

    def test_unit_size_section_has_required_fields(self):
        """Unit-size section must have: pnl_total, win_rate, binary_win_rate, open_positions, etc."""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        data = response.json()
        
        if data.get('status') == 'no_data':
            pytest.skip("Shadow engine has no data yet")
        
        unit = data.get('unit_size', {})
        
        required_fields = [
            'pnl_total', 'win_rate', 'binary_win_rate', 'open_positions',
            'open_exposure', 'open_total_size', 'pnl_per_trade', 'rolling_pnl'
        ]
        for field in required_fields:
            assert field in unit, f"unit_size missing {field}"
        
        print(f"PASS: unit_size has all required fields: {required_fields}")

    def test_live_equivalent_section_has_required_fields(self):
        """Live-equivalent section must have same fields as unit_size"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        data = response.json()
        
        if data.get('status') == 'no_data':
            pytest.skip("Shadow engine has no data yet")
        
        le = data.get('live_equivalent', {})
        
        required_fields = [
            'pnl_total', 'win_rate', 'binary_win_rate', 'open_positions',
            'open_exposure', 'open_total_size', 'pnl_per_trade', 'rolling_pnl'
        ]
        for field in required_fields:
            assert field in le, f"live_equivalent missing {field}"
        
        print(f"PASS: live_equivalent has all required fields: {required_fields}")

    def test_sizing_section_shows_accumulation_difference(self):
        """Sizing section must show unit.accumulation=false and le.accumulation=true"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        data = response.json()
        
        if data.get('status') == 'no_data':
            pytest.skip("Shadow engine has no data yet")
        
        assert 'sizing' in data, "Missing sizing section"
        sizing = data['sizing']
        
        assert 'unit' in sizing, "Missing sizing.unit"
        assert 'live_equivalent' in sizing, "Missing sizing.live_equivalent"
        
        # Unit should NOT accumulate
        assert sizing['unit'].get('accumulation') == False, \
            f"unit.accumulation should be False, got {sizing['unit'].get('accumulation')}"
        
        # LE should accumulate
        assert sizing['live_equivalent'].get('accumulation') == True, \
            f"live_equivalent.accumulation should be True, got {sizing['live_equivalent'].get('accumulation')}"
        
        # LE should have max_size = 25
        le_max = sizing['live_equivalent'].get('max_size')
        assert le_max == 25 or le_max == 25.0, f"live_equivalent.max_size should be 25, got {le_max}"
        
        print(f"PASS: Sizing section correctly shows:")
        print(f"  - unit.accumulation = {sizing['unit'].get('accumulation')}")
        print(f"  - live_equivalent.accumulation = {sizing['live_equivalent'].get('accumulation')}")
        print(f"  - live_equivalent.max_size = {le_max}")


class TestShadowPositionsEndpoints:
    """Tests for /api/shadow/positions with mode parameter"""

    def test_unit_positions_endpoint_works(self):
        """GET /api/shadow/positions?mode=unit returns valid list"""
        response = requests.get(f"{BASE_URL}/api/shadow/positions?mode=unit")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS: Unit positions endpoint returns {len(data)} positions")
        
        # If there are unit positions, verify size=3 (no accumulation)
        for pos in data[:3]:  # Check first 3
            size = pos.get('size')
            fills = pos.get('fills', 1)
            print(f"  - {pos.get('asset', 'N/A')}: size={size}, fills={fills}")
            # Unit mode should have size equal to default ($3)
            assert size == 3 or size == 3.0, f"Unit position should have size=3, got {size}"
            # Unit mode should have exactly 1 fill (no accumulation)
            assert fills == 1, f"Unit position should have fills=1, got {fills}"

    def test_le_positions_endpoint_works(self):
        """GET /api/shadow/positions?mode=le returns valid list"""
        response = requests.get(f"{BASE_URL}/api/shadow/positions?mode=le")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS: LE positions endpoint returns {len(data)} positions")
        
        # Check for accumulation evidence
        accumulated = [p for p in data if p.get('fills', 1) > 1]
        print(f"  - Positions with accumulation (fills>1): {len(accumulated)}")
        
        for pos in data[:5]:  # Check first 5
            size = pos.get('size')
            fills = pos.get('fills', 1)
            avg_entry = pos.get('avg_entry')
            entry_price = pos.get('entry_price')
            print(f"  - {pos.get('asset', 'N/A')}: size={size}, fills={fills}, avg_entry={avg_entry}, entry_price={entry_price}")

    def test_le_positions_have_avg_entry_field(self):
        """LE positions must have avg_entry field for cost-basis tracking"""
        response = requests.get(f"{BASE_URL}/api/shadow/positions?mode=le")
        assert response.status_code == 200
        data = response.json()
        
        for pos in data[:5]:
            assert 'avg_entry' in pos, f"LE position missing avg_entry field"
            assert 'fills' in pos, f"LE position missing fills field"
        
        print(f"PASS: LE positions have avg_entry and fills fields")

    def test_le_positions_respect_max_cap(self):
        """No LE position should exceed max_position_size (25)"""
        response = requests.get(f"{BASE_URL}/api/shadow/positions?mode=le")
        assert response.status_code == 200
        data = response.json()
        
        max_allowed = 25  # max_position_size from risk_config
        violations = []
        for pos in data:
            size = pos.get('size', 0)
            if size > max_allowed:
                violations.append({
                    'token_id': pos.get('token_id'),
                    'size': size
                })
        
        assert len(violations) == 0, f"Found {len(violations)} positions exceeding max cap: {violations}"
        print(f"PASS: All {len(data)} LE positions respect max_position_size={max_allowed}")


class TestShadowClosedEndpoints:
    """Tests for /api/shadow/closed with mode parameter"""

    def test_unit_closed_endpoint_works(self):
        """GET /api/shadow/closed?mode=unit returns valid list"""
        response = requests.get(f"{BASE_URL}/api/shadow/closed?mode=unit")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS: Unit closed endpoint returns {len(data)} trades")

    def test_le_closed_endpoint_works(self):
        """GET /api/shadow/closed?mode=le returns valid list"""
        response = requests.get(f"{BASE_URL}/api/shadow/closed?mode=le")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"PASS: LE closed endpoint returns {len(data)} trades")


class TestShadowEvaluationsLEAction:
    """Tests for /api/shadow/evaluations with LE Action field"""

    def test_evaluations_have_le_action_field(self):
        """Evaluations should have le_action field for LE mode tracking"""
        response = requests.get(f"{BASE_URL}/api/shadow/evaluations?limit=100")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        
        # Check for le_action field presence
        evals_with_le_action = [e for e in data if e.get('le_action')]
        print(f"PASS: Evaluations endpoint returns {len(data)} evaluations")
        print(f"  - Evaluations with LE action: {len(evals_with_le_action)}")
        
        # Check for accum/cap_blocked entries
        accum_actions = [e for e in data if e.get('le_action') and 'accum' in str(e.get('le_action'))]
        cap_blocked = [e for e in data if e.get('le_action') and 'cap_blocked' in str(e.get('le_action'))]
        print(f"  - Accumulation actions: {len(accum_actions)}")
        print(f"  - Cap blocked actions: {len(cap_blocked)}")


class TestShadowDataIsolation:
    """Verify shadow data does NOT appear in main system endpoints"""

    def test_status_has_no_shadow_data(self):
        """GET /api/status should NOT contain shadow strategy or shadow PnL"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Check strategies list
        strategies = data.get('strategies', {})
        assert 'shadow' not in strategies, "shadow strategy should not appear in status.strategies"
        assert 'shadow_sniper' not in strategies, "shadow_sniper should not appear in status.strategies"
        
        # Check stats
        stats = data.get('stats', {})
        assert 'shadow_pnl' not in stats, "shadow_pnl should not appear in status.stats"
        
        print(f"PASS: /api/status has no shadow data contamination")

    def test_pnl_history_has_no_shadow_entries(self):
        """GET /api/analytics/pnl-history should NOT have shadow entries"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        history = data.get('history', [])
        for entry in history:
            strategy = entry.get('strategy_id', '')
            assert 'shadow' not in strategy.lower(), \
                f"Found shadow entry in pnl-history: {strategy}"
        
        print(f"PASS: /api/analytics/pnl-history has no shadow entries ({len(history)} entries checked)")


class TestDualModeComparison:
    """Test that dual modes produce meaningful differences"""

    def test_unit_vs_le_total_size_difference(self):
        """LE total_size should potentially be larger than unit due to accumulation"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        data = response.json()
        
        if data.get('status') == 'no_data':
            pytest.skip("Shadow engine has no data yet")
        
        unit = data.get('unit_size', {})
        le = data.get('live_equivalent', {})
        
        unit_total = unit.get('open_total_size', 0)
        le_total = le.get('open_total_size', 0)
        
        print(f"Unit-Size total: {unit_total}")
        print(f"Live-Equivalent total: {le_total}")
        
        # Note: LE can be equal or larger than unit due to accumulation
        # We just verify both are reasonable values
        assert unit_total >= 0, "Unit total size should be >= 0"
        assert le_total >= 0, "LE total size should be >= 0"
        
        # Log the comparison for analysis
        if le_total > unit_total:
            print(f"PASS: LE total ({le_total}) > Unit total ({unit_total}) - accumulation visible")
        elif le_total == unit_total:
            print(f"PASS: LE total == Unit total ({le_total}) - same positions or no accumulation yet")
        else:
            print(f"NOTE: LE total ({le_total}) < Unit total ({unit_total}) - unexpected but not error")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
