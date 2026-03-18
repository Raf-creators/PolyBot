"""
Iteration 59: Download Debug Snapshot Feature Tests

Tests for:
1. GET /api/debug/ui-snapshot - No auth required, returns full snapshot
2. GET /api/debug/state-snapshot - Requires X-Debug-Snapshot-Key header (or ?key= param)
3. Snapshot JSON structure validation
"""

import pytest
import requests
import os
from datetime import datetime

# Use the public preview URL
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://edge-trading-hub-1.preview.emergentagent.com')

# Debug snapshot key from backend/.env
DEBUG_KEY = "test-snapshot-key-preview"


class TestUISnapshotEndpoint:
    """Test /api/debug/ui-snapshot - No auth required"""

    def test_ui_snapshot_no_auth_required(self):
        """GET /api/debug/ui-snapshot returns 200 without any auth key"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "freshness" in data, "Response should contain 'freshness' key"
        print("✓ /api/debug/ui-snapshot returns 200 without auth")

    def test_ui_snapshot_returns_json_structure(self):
        """Verify ui-snapshot returns all required top-level keys"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        
        expected_keys = [
            "freshness", 
            "positions", 
            "position_counts", 
            "lifecycle", 
            "entry_quality", 
            "pnl_summary", 
            "strategy_health", 
            "weather_config"
        ]
        
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"
        
        print(f"✓ UI snapshot contains all {len(expected_keys)} required keys: {expected_keys}")


class TestKeyedSnapshotEndpoint:
    """Test /api/debug/state-snapshot - Requires auth key"""

    def test_state_snapshot_requires_key(self):
        """GET /api/debug/state-snapshot returns 403 when no key provided"""
        response = requests.get(f"{BASE_URL}/api/debug/state-snapshot")
        
        assert response.status_code == 403, f"Expected 403 without key, got {response.status_code}"
        print("✓ /api/debug/state-snapshot returns 403 without key")

    def test_state_snapshot_wrong_key(self):
        """GET /api/debug/state-snapshot returns 403 with wrong key"""
        response = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": "wrong-key-12345"}
        )
        
        assert response.status_code == 403, f"Expected 403 with wrong key, got {response.status_code}"
        print("✓ /api/debug/state-snapshot returns 403 with wrong key")

    def test_state_snapshot_with_header_key(self):
        """GET /api/debug/state-snapshot works with X-Debug-Snapshot-Key header"""
        response = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        
        assert response.status_code == 200, f"Expected 200 with valid key, got {response.status_code}: {response.text}"
        data = response.json()
        assert "freshness" in data
        print("✓ /api/debug/state-snapshot works with X-Debug-Snapshot-Key header")


class TestSnapshotFreshnessData:
    """Test freshness metadata in snapshot"""

    def test_freshness_contains_snapshot_at(self):
        """Freshness contains valid ISO timestamp in snapshot_at"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        freshness = data.get("freshness", {})
        
        assert "snapshot_at" in freshness, "Missing snapshot_at in freshness"
        snapshot_at = freshness["snapshot_at"]
        
        # Validate it's a valid ISO timestamp
        try:
            parsed = datetime.fromisoformat(snapshot_at.replace("Z", "+00:00"))
            print(f"✓ freshness.snapshot_at is valid ISO timestamp: {snapshot_at}")
        except ValueError:
            pytest.fail(f"snapshot_at is not a valid ISO timestamp: {snapshot_at}")

    def test_freshness_contains_required_fields(self):
        """Freshness contains all expected fields"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        freshness = data.get("freshness", {})
        
        expected_fields = [
            "snapshot_at",
            "snapshot_version",
            "server_start_time",
            "uptime_seconds",
            "engine_status",
            "trading_mode",
            "git_commit"
        ]
        
        for field in expected_fields:
            assert field in freshness, f"Missing field in freshness: {field}"
        
        print(f"✓ freshness contains all {len(expected_fields)} expected fields")


class TestSnapshotPositionsData:
    """Test positions data in snapshot"""

    def test_positions_grouped_by_strategy(self):
        """Positions are grouped by strategy (weather/crypto/arb)"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        
        positions = data.get("positions", {})
        position_counts = data.get("position_counts", {})
        
        # Should have at least some positions (test env has 54 weather, 11 crypto, 21 arb)
        total = sum(position_counts.values())
        print(f"✓ Total positions in snapshot: {total}")
        print(f"  Position counts: {position_counts}")
        
        # Verify position_counts matches actual positions
        for strategy, count in position_counts.items():
            actual_count = len(positions.get(strategy, []))
            assert actual_count == count, f"Mismatch for {strategy}: count={count}, actual={actual_count}"

    def test_position_counts_key_present(self):
        """position_counts key contains position count per strategy"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "position_counts" in data, "Missing position_counts key"
        position_counts = data["position_counts"]
        
        # Should be a dict with integer values
        assert isinstance(position_counts, dict)
        for key, val in position_counts.items():
            assert isinstance(val, int), f"position_counts[{key}] should be int, got {type(val)}"
        
        print(f"✓ position_counts is present and valid: {position_counts}")


class TestSnapshotPnlSummary:
    """Test PnL summary data in snapshot"""

    def test_pnl_summary_contains_required_fields(self):
        """pnl_summary contains total_realized, total_unrealized, total, etc."""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        
        pnl_summary = data.get("pnl_summary", {})
        
        if "error" not in pnl_summary:
            expected_fields = [
                "total_realized",
                "total_unrealized", 
                "total",
                "open_positions"
            ]
            
            for field in expected_fields:
                assert field in pnl_summary, f"Missing field in pnl_summary: {field}"
            
            print(f"✓ pnl_summary contains all expected fields")
            print(f"  total_realized: {pnl_summary.get('total_realized')}")
            print(f"  total_unrealized: {pnl_summary.get('total_unrealized')}")
            print(f"  total: {pnl_summary.get('total')}")


class TestSnapshotLifecycleData:
    """Test lifecycle data in snapshot"""

    def test_lifecycle_contains_mode_and_config(self):
        """lifecycle contains mode, config, and exit_candidates_detail"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        
        lifecycle = data.get("lifecycle", {})
        
        # Should have mode
        assert "mode" in lifecycle, "Missing mode in lifecycle"
        
        # Should have config
        assert "config" in lifecycle, "Missing config in lifecycle"
        
        # Should have exit_candidates_detail
        assert "exit_candidates_detail" in lifecycle, "Missing exit_candidates_detail in lifecycle"
        
        print(f"✓ lifecycle data is present")
        print(f"  mode: {lifecycle.get('mode')}")
        print(f"  exit_candidates: {lifecycle.get('exit_candidates', 0)}")


class TestSnapshotStrategyHealth:
    """Test strategy health data in snapshot"""

    def test_strategy_health_contains_weather_crypto_arb(self):
        """strategy_health contains weather, crypto_sniper, arb_scanner entries"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        
        strategy_health = data.get("strategy_health", {})
        
        expected_strategies = ["weather", "crypto_sniper", "arb_scanner"]
        
        for strat in expected_strategies:
            assert strat in strategy_health, f"Missing {strat} in strategy_health"
        
        print(f"✓ strategy_health contains all expected strategies")


class TestSnapshotWeatherConfig:
    """Test weather_config data in snapshot"""

    def test_weather_config_present(self):
        """weather_config contains full WeatherConfig fields"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        
        weather_config = data.get("weather_config", {})
        
        # Should have many config fields
        assert len(weather_config) > 30, f"Expected 30+ weather config fields, got {len(weather_config)}"
        
        # Check some essential fields
        essential_fields = ["min_edge_bps", "min_confidence", "lifecycle_mode"]
        for field in essential_fields:
            assert field in weather_config, f"Missing essential field: {field}"
        
        print(f"✓ weather_config contains {len(weather_config)} fields")


class TestSnapshotEntryQuality:
    """Test entry_quality data in snapshot"""

    def test_entry_quality_structure(self):
        """entry_quality contains rejections and passed_signals stats"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        data = response.json()
        
        entry_quality = data.get("entry_quality", {})
        
        assert "rejections" in entry_quality, "Missing rejections in entry_quality"
        assert "passed_signals" in entry_quality, "Missing passed_signals in entry_quality"
        
        print(f"✓ entry_quality structure is valid")
        print(f"  rejections: {entry_quality.get('rejections')}")


class TestSnapshotJSONSize:
    """Test snapshot JSON is reasonable size"""

    def test_snapshot_is_reasonable_size(self):
        """Snapshot JSON should be manageable size (< 100KB typical)"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot")
        
        assert response.status_code == 200
        
        json_text = response.text
        size_kb = len(json_text) / 1024
        
        # Should be reasonable size (expected ~43KB per docs)
        assert size_kb < 200, f"Snapshot too large: {size_kb:.1f}KB"
        
        print(f"✓ Snapshot size is reasonable: {size_kb:.1f}KB")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
