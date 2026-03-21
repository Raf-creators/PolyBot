"""
Iteration 76: Sanity Check Audit - Phase 1 + Phase 2 Features
Tests all backend APIs for Polymarket trading bot with:
- Phase 1: Dynamic Kelly-inspired sizing, window-aware position caps, minimum dislocation filter
- Phase 2: Phantom Gabagool both-sides structural arb mode
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCoreBackendAPIs:
    """Core backend health and status endpoints"""
    
    def test_status_endpoint(self):
        """Test /api/status returns running status"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'running'
        assert data['mode'] == 'paper'
        assert 'uptime_seconds' in data
        assert 'components' in data
    
    def test_positions_endpoint(self):
        """Test /api/positions returns array"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_trades_endpoint(self):
        """Test /api/trades returns array"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_diagnostics_endpoint(self):
        """Test /api/diagnostics returns system info"""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert 'environment' in data
        assert 'database' in data
        assert 'state' in data


class TestSniperHealth:
    """Phase 1: Sniper health with dynamic sizing, position caps, dislocation filter"""
    
    def test_sniper_health_endpoint(self):
        """Test /api/strategies/sniper/health returns running=true"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert data['running'] == True
        assert 'total_scans' in data
        assert 'signals_generated' in data
    
    def test_sniper_dislocation_filtered_field_exists(self):
        """Test dislocation_filtered field exists (Phase 1 minimum dislocation filter)"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert 'dislocation_filtered' in data
        # Field exists - value may be 0 if no dislocations filtered yet after reset
    
    def test_sniper_position_capped_field_exists(self):
        """Test position_capped field exists (Phase 1 window-aware position caps)"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert 'position_capped' in data
        # Field exists - value may be 0 or positive depending on market conditions
    
    def test_sniper_rejection_reasons_field_exists(self):
        """Test rejection_reasons field exists"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert 'rejection_reasons' in data
        assert isinstance(data['rejection_reasons'], dict)


class TestShadowReport:
    """Shadow sniper report endpoint"""
    
    def test_shadow_report_status(self):
        """Test /api/shadow/report returns valid status"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] in ['active', 'no_data', 'collecting']
    
    def test_shadow_report_structure(self):
        """Test shadow report has expected structure"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data
        # If active, should have evaluations
        if data['status'] == 'active':
            assert 'total_evaluations' in data


class TestMoonDevReport:
    """MoonDev short window experiment"""
    
    def test_moondev_report_status(self):
        """Test /api/experiments/moondev/report returns valid status"""
        response = requests.get(f"{BASE_URL}/api/experiments/moondev/report")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] in ['active', 'collecting', 'no_data']
    
    def test_moondev_report_has_metrics(self):
        """Test MoonDev report has metrics"""
        response = requests.get(f"{BASE_URL}/api/experiments/moondev/report")
        assert response.status_code == 200
        data = response.json()
        assert 'metrics' in data
        metrics = data['metrics']
        assert 'total_signals_received' in metrics
        assert 'window_filtered_out' in metrics
        assert 'evaluated' in metrics


class TestPhantomReport:
    """Phase 2: Phantom Gabagool both-sides structural arb"""
    
    def test_phantom_report_status(self):
        """Test /api/experiments/phantom/report returns valid status"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/report")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] in ['active', 'collecting', 'no_data']
    
    def test_phantom_gabagool_threshold(self):
        """Test gabagool_threshold = 0.96"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/report")
        assert response.status_code == 200
        data = response.json()
        assert 'config' in data
        assert data['config']['gabagool_threshold'] == 0.96
    
    def test_phantom_gabagool_trades_field_exists(self):
        """Test gabagool_trades field exists in metrics"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/report")
        assert response.status_code == 200
        data = response.json()
        assert 'metrics' in data
        assert 'gabagool_trades' in data['metrics']
        # Value may be 0 after reset, but field should exist
    
    def test_phantom_gabagool_stats(self):
        """Test gabagool stats object exists with win_rate"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/report")
        assert response.status_code == 200
        data = response.json()
        assert 'gabagool' in data
        gabagool = data['gabagool']
        assert 'pnl_total' in gabagool
        assert 'win_rate' in gabagool
        assert 'closed_trades' in gabagool


class TestPhantomGabagoolPositions:
    """Phantom Gabagool positions and closed endpoints"""
    
    def test_phantom_gabagool_positions_returns_array(self):
        """Test /api/experiments/phantom/positions?mode=gabagool returns array"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/positions?mode=gabagool")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_phantom_gabagool_closed_returns_array(self):
        """Test /api/experiments/phantom/closed?mode=gabagool returns array"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/closed?mode=gabagool")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_phantom_gabagool_closed_returns_valid_structure(self):
        """Test gabagool closed returns valid array (may be empty after reset)"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/closed?mode=gabagool")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # If there are entries, verify structure
        if len(data) > 0:
            entry = data[0]
            assert 'won' in entry
    
    def test_phantom_gabagool_closed_structure(self):
        """Test gabagool closed entries have correct structure"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/closed?mode=gabagool")
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            entry = data[0]
            assert 'question' in entry
            assert 'yes_entry' in entry
            assert 'no_entry' in entry
            assert 'pair_cost' in entry
            assert 'guaranteed_edge_pct' in entry
            assert 'pnl' in entry
            assert 'won' in entry


class TestPhantomOneSide:
    """Phantom one-side spread positions"""
    
    def test_phantom_unit_positions_returns_array(self):
        """Test /api/experiments/phantom/positions?mode=unit returns array"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/positions?mode=unit")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_phantom_unit_closed_returns_array(self):
        """Test /api/experiments/phantom/closed?mode=unit returns array"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/closed?mode=unit")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestPhantomEvaluations:
    """Phantom evaluations endpoint"""
    
    def test_phantom_evaluations_returns_array(self):
        """Test /api/experiments/phantom/evaluations returns array"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/evaluations")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_phantom_evaluations_has_gabagool_eligible_field(self):
        """Test evaluations have gabagool_eligible field"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/evaluations")
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            entry = data[0]
            assert 'gabagool_eligible' in entry


class TestWhrrariModes:
    """Whrrari 3 sizing modes"""
    
    def test_whrrari_report_returns_valid_status(self):
        """Test /api/experiments/whrrari/report returns valid status"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/report")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] in ['active', 'collecting', 'no_data']
    
    def test_whrrari_report_has_3_mode_stats(self):
        """Test report has unit_size, sandbox_notional, crypto_mirrored stats"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/report")
        assert response.status_code == 200
        data = response.json()
        assert 'unit_size' in data
        assert 'sandbox_notional' in data
        assert 'crypto_mirrored' in data
    
    def test_whrrari_positions_mode_unit(self):
        """Test /api/experiments/whrrari/positions?mode=unit returns array"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/positions?mode=unit")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_whrrari_positions_mode_sandbox(self):
        """Test /api/experiments/whrrari/positions?mode=sandbox returns array"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/positions?mode=sandbox")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_whrrari_positions_mode_crypto(self):
        """Test /api/experiments/whrrari/positions?mode=crypto returns array"""
        response = requests.get(f"{BASE_URL}/api/experiments/whrrari/positions?mode=crypto")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestExperimentsRegistry:
    """Experiments registry endpoint"""
    
    def test_registry_returns_all_6_experiments(self):
        """Test /api/experiments/registry returns all 6 experiments"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        data = response.json()
        assert 'experiments' in data
        assert len(data['experiments']) == 6
    
    def test_registry_experiment_ids(self):
        """Test registry has correct experiment IDs"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        data = response.json()
        exp_ids = [e['id'] for e in data['experiments']]
        expected_ids = ['shadow_sniper', 'moondev', 'phantom', 'whrrari', 'marik', 'argona']
        for exp_id in expected_ids:
            assert exp_id in exp_ids, f"Missing experiment: {exp_id}"
    
    def test_registry_active_experiments(self):
        """Test 4 experiments are active"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        data = response.json()
        active_exps = [e for e in data['experiments'] if e['status'] == 'active']
        assert len(active_exps) == 4
    
    def test_registry_planned_experiments(self):
        """Test 2 experiments are planned"""
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        data = response.json()
        planned_exps = [e for e in data['experiments'] if e['status'] == 'planned']
        assert len(planned_exps) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
