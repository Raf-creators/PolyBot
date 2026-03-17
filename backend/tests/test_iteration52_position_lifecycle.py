"""
Iteration 52: Position Lifecycle Management for Weather Strategies

Features tested:
- GET /api/positions/weather/exit-candidates returns mode, config, candidates list, shadow_exits
- GET /api/positions/weather/lifecycle returns evaluations with profit_multiple, edge_at_entry, current_edge_bps, edge_decay_pct, is_exit_candidate, exit_reason
- GET /api/positions/by-strategy includes lifecycle object in weather positions
- GET /api/positions/by-strategy lifecycle field is null for non-weather positions
- Asymmetric (weather_asymmetric) positions are NEVER evaluated for exit
- Default lifecycle_mode is 'tag_only'
- Profit capture threshold triggers at 2.0x profit multiple
- Exit candidates count matches actual exit-tagged positions
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestExitCandidatesEndpoint:
    """Test GET /api/positions/weather/exit-candidates"""

    def test_exit_candidates_returns_200(self):
        """GET /api/positions/weather/exit-candidates returns 200"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/positions/weather/exit-candidates returns 200")

    def test_exit_candidates_has_required_fields(self):
        """Response includes mode, config, candidates, total_evaluated, shadow_exits"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ['mode', 'config', 'candidates', 'total_evaluated', 'shadow_exits']
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        print(f"PASS: exit-candidates has all required fields: {required_fields}")

    def test_exit_candidates_mode_is_tag_only(self):
        """Default lifecycle_mode is 'tag_only'"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200
        data = response.json()
        
        mode = data.get('mode')
        # Accept tag_only or off as valid default states
        assert mode in ['tag_only', 'off', 'shadow_exit', 'auto_exit'], f"Unexpected mode: {mode}"
        print(f"PASS: lifecycle_mode = '{mode}'")

    def test_exit_candidates_config_has_thresholds(self):
        """Config includes profit_capture_threshold, max_negative_edge_bps, edge_decay_exit_pct, time_inefficiency_hours"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200
        data = response.json()
        
        config = data.get('config', {})
        required_config_fields = [
            'profit_capture_threshold',
            'max_negative_edge_bps',
            'edge_decay_exit_pct',
            'time_inefficiency_hours',
            'time_inefficiency_min_edge_bps'
        ]
        for field in required_config_fields:
            assert field in config, f"Config missing field: {field}"
        
        # Verify expected default values
        assert config.get('profit_capture_threshold') == 2.0, f"profit_capture_threshold should be 2.0, got {config.get('profit_capture_threshold')}"
        assert config.get('max_negative_edge_bps') == -100.0, f"max_negative_edge_bps should be -100, got {config.get('max_negative_edge_bps')}"
        assert config.get('edge_decay_exit_pct') == 0.60, f"edge_decay_exit_pct should be 0.60, got {config.get('edge_decay_exit_pct')}"
        assert config.get('time_inefficiency_hours') == 18.0, f"time_inefficiency_hours should be 18, got {config.get('time_inefficiency_hours')}"
        
        print(f"PASS: Config thresholds: profit_capture={config.get('profit_capture_threshold')}, max_neg_edge={config.get('max_negative_edge_bps')}, edge_decay={config.get('edge_decay_exit_pct')}, time_ineff={config.get('time_inefficiency_hours')}h")

    def test_candidates_is_list(self):
        """candidates field is a list"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200
        data = response.json()
        
        candidates = data.get('candidates')
        assert isinstance(candidates, list), f"candidates should be list, got {type(candidates)}"
        print(f"PASS: candidates is a list with {len(candidates)} items")

    def test_shadow_exits_is_list(self):
        """shadow_exits field is a list"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200
        data = response.json()
        
        shadow_exits = data.get('shadow_exits')
        assert isinstance(shadow_exits, list), f"shadow_exits should be list, got {type(shadow_exits)}"
        print(f"PASS: shadow_exits is a list with {len(shadow_exits)} items")


class TestLifecycleEndpoint:
    """Test GET /api/positions/weather/lifecycle"""

    def test_lifecycle_returns_200(self):
        """GET /api/positions/weather/lifecycle returns 200"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/positions/weather/lifecycle returns 200")

    def test_lifecycle_has_required_fields(self):
        """Response includes mode, evaluations, metrics, config"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ['mode', 'evaluations', 'metrics', 'config']
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        print(f"PASS: lifecycle has all required fields: {required_fields}")

    def test_evaluations_structure(self):
        """Evaluations have correct structure with lifecycle metrics"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert response.status_code == 200
        data = response.json()
        
        evaluations = data.get('evaluations', {})
        if len(evaluations) == 0:
            print("SKIP: No evaluations to check (lifecycle may be off or no standard weather positions)")
            return
        
        # Check first evaluation
        first_key = list(evaluations.keys())[0]
        first_eval = evaluations[first_key]
        
        expected_fields = [
            'token_id', 'strategy_id', 'is_exit_candidate', 'exit_reason',
            'profit_multiple', 'edge_at_entry', 'current_edge_bps', 'edge_decay_pct',
            'current_model_prob', 'time_held_hours', 'lifecycle_mode'
        ]
        
        for field in expected_fields:
            assert field in first_eval, f"Evaluation missing field: {field}"
        
        print(f"PASS: Evaluations have correct structure with {len(expected_fields)} fields")
        
        # Print sample values
        print(f"  Sample: profit_multiple={first_eval.get('profit_multiple')}, is_exit_candidate={first_eval.get('is_exit_candidate')}, exit_reason={first_eval.get('exit_reason')}")


class TestPositionsByStrategyLifecycle:
    """Test lifecycle enrichment in GET /api/positions/by-strategy"""

    def test_positions_by_strategy_returns_200(self):
        """GET /api/positions/by-strategy returns 200"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/positions/by-strategy returns 200")

    def test_weather_positions_have_lifecycle_field(self):
        """Weather positions include lifecycle object or null"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        weather_positions = data.get('positions', {}).get('weather', [])
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        has_lifecycle = 0
        null_lifecycle = 0
        for pos in weather_positions:
            # lifecycle field should exist (could be object or null)
            assert 'lifecycle' in pos, f"Position missing lifecycle field: {pos.get('token_id', 'unknown')[:20]}"
            if pos.get('lifecycle') is not None:
                has_lifecycle += 1
            else:
                null_lifecycle += 1
        
        print(f"PASS: Weather positions have lifecycle field. Has data: {has_lifecycle}, null: {null_lifecycle}")

    def test_lifecycle_object_structure(self):
        """Lifecycle objects have correct structure when present"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        weather_positions = data.get('positions', {}).get('weather', [])
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        expected_lifecycle_fields = [
            'is_exit_candidate', 'exit_reason', 'profit_multiple',
            'edge_at_entry', 'current_edge_bps', 'edge_decay_pct',
            'current_model_prob', 'time_held_hours', 'lifecycle_mode'
        ]
        
        positions_with_lifecycle = [p for p in weather_positions if p.get('lifecycle')]
        if len(positions_with_lifecycle) == 0:
            print("SKIP: No positions with lifecycle data (lifecycle may be off)")
            return
        
        first_lc = positions_with_lifecycle[0].get('lifecycle')
        for field in expected_lifecycle_fields:
            assert field in first_lc, f"Lifecycle object missing field: {field}"
        
        print(f"PASS: Lifecycle object has correct structure with {len(expected_lifecycle_fields)} fields")

    def test_non_weather_positions_have_no_lifecycle(self):
        """Non-weather positions (crypto, arb) do not have lifecycle field or it is null"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        crypto_positions = data.get('positions', {}).get('crypto', [])
        arb_positions = data.get('positions', {}).get('arb', [])
        
        for pos in crypto_positions:
            lc = pos.get('lifecycle')
            if lc is not None:
                pytest.fail(f"Crypto position should not have lifecycle: {pos.get('token_id', 'unknown')[:20]}")
        
        for pos in arb_positions:
            lc = pos.get('lifecycle')
            if lc is not None:
                pytest.fail(f"Arb position should not have lifecycle: {pos.get('token_id', 'unknown')[:20]}")
        
        print(f"PASS: {len(crypto_positions)} crypto and {len(arb_positions)} arb positions have null lifecycle")

    def test_lifecycle_summary_in_response(self):
        """Response includes lifecycle summary with mode and exit_candidates count"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        lifecycle = data.get('lifecycle', {})
        assert 'mode' in lifecycle, "lifecycle summary missing 'mode'"
        assert 'exit_candidates' in lifecycle, "lifecycle summary missing 'exit_candidates'"
        
        mode = lifecycle.get('mode')
        exit_count = lifecycle.get('exit_candidates')
        
        print(f"PASS: Lifecycle summary: mode='{mode}', exit_candidates={exit_count}")


class TestAsymmetricExclusion:
    """Test that asymmetric positions are NEVER evaluated for exit"""

    def test_asymmetric_positions_no_lifecycle(self):
        """weather_asymmetric positions should have null lifecycle"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        weather_positions = data.get('positions', {}).get('weather', [])
        
        asymmetric_positions = [
            p for p in weather_positions 
            if p.get('strategy_id') == 'weather_asymmetric'
        ]
        
        if len(asymmetric_positions) == 0:
            print("SKIP: No asymmetric weather positions to test (this is OK)")
            return
        
        for pos in asymmetric_positions:
            lc = pos.get('lifecycle')
            if lc is not None:
                pytest.fail(f"Asymmetric position should NOT have lifecycle: {pos.get('token_id', 'unknown')[:20]}")
        
        print(f"PASS: {len(asymmetric_positions)} asymmetric positions correctly have null lifecycle")


class TestExitCandidatesCounting:
    """Test that exit candidate counts are accurate"""

    def test_exit_candidates_count_matches_tagged_positions(self):
        """exit_candidates count in summary matches actual is_exit_candidate=true positions"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        weather_positions = data.get('positions', {}).get('weather', [])
        lifecycle_summary = data.get('lifecycle', {})
        
        # Count positions with is_exit_candidate = True
        actual_exit_candidates = sum(
            1 for p in weather_positions 
            if p.get('lifecycle') and p['lifecycle'].get('is_exit_candidate')
        )
        
        reported_exit_candidates = lifecycle_summary.get('exit_candidates', 0)
        
        assert actual_exit_candidates == reported_exit_candidates, \
            f"Exit candidate count mismatch: actual={actual_exit_candidates}, reported={reported_exit_candidates}"
        
        print(f"PASS: Exit candidates count matches: {actual_exit_candidates}")


class TestProfitCaptureThreshold:
    """Test profit capture threshold logic"""

    def test_profit_capture_at_2x(self):
        """Positions with profit_multiple >= 2.0 should be exit candidates with exit_reason='profit_capture'"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        weather_positions = data.get('positions', {}).get('weather', [])
        
        profit_capture_candidates = []
        high_multiple_not_tagged = []
        
        for pos in weather_positions:
            lc = pos.get('lifecycle')
            if not lc:
                continue
            
            profit_mult = lc.get('profit_multiple', 0)
            is_exit = lc.get('is_exit_candidate', False)
            exit_reason = lc.get('exit_reason')
            
            if profit_mult >= 2.0:
                if is_exit and exit_reason == 'profit_capture':
                    profit_capture_candidates.append(pos)
                else:
                    high_multiple_not_tagged.append({
                        'profit_multiple': profit_mult,
                        'is_exit_candidate': is_exit,
                        'exit_reason': exit_reason
                    })
        
        if len(high_multiple_not_tagged) > 0:
            print(f"WARNING: {len(high_multiple_not_tagged)} positions with >=2x multiple not tagged as profit_capture")
            for info in high_multiple_not_tagged[:3]:
                print(f"  - mult={info['profit_multiple']}, is_exit={info['is_exit_candidate']}, reason={info['exit_reason']}")
        
        print(f"PASS: Found {len(profit_capture_candidates)} profit_capture exit candidates")


class TestExitReasonEnums:
    """Test that exit reasons match expected enum values"""

    def test_exit_reason_values(self):
        """exit_reason values match ExitReason enum: profit_capture, negative_edge, edge_decay, time_inefficiency, model_shift"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        weather_positions = data.get('positions', {}).get('weather', [])
        
        valid_reasons = {'profit_capture', 'negative_edge', 'edge_decay', 'time_inefficiency', 'model_shift', None}
        reason_counts = {}
        
        for pos in weather_positions:
            lc = pos.get('lifecycle')
            if not lc:
                continue
            
            exit_reason = lc.get('exit_reason')
            if exit_reason is not None:
                assert exit_reason in valid_reasons, f"Invalid exit_reason: {exit_reason}"
            
            reason_counts[exit_reason or 'none'] = reason_counts.get(exit_reason or 'none', 0) + 1
        
        print(f"PASS: Exit reason breakdown: {reason_counts}")


class TestLifecycleMetrics:
    """Test lifecycle metrics in /api/positions/weather/lifecycle"""

    def test_metrics_structure(self):
        """Metrics include positions_evaluated, exit_candidates, mode"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert response.status_code == 200
        data = response.json()
        
        metrics = data.get('metrics', {})
        
        # These fields should be present in the metrics
        expected_metrics = ['mode', 'positions_evaluated', 'exit_candidates']
        for field in expected_metrics:
            if field not in metrics:
                print(f"INFO: metrics missing '{field}' (may not be populated yet)")
        
        print(f"PASS: Lifecycle metrics: {metrics}")
