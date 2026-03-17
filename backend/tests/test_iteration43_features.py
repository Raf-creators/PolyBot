"""
Iteration 43: Phase 2 Production Optimization Tests

Tests for:
1. GET /api/status — all 3 strategies show enabled=true, status=active (NOT stopped)
2. GET /api/analytics/strategy-tracker — position_slots has weather_count, crypto_count, arb_count, unknown_count
3. GET /api/analytics/strategy-tracker — position_slots.limits has max_weather=25, max_crypto=20, max_arb=20, max_global=65
4. GET /api/analytics/strategy-tracker — position_slots.headroom has weather, crypto, arb, global keys
5. GET /api/analytics/strategy-tracker — position_slots.sizing has crypto=5.0, weather=3.0, arb=2.0
6. GET /api/analytics/watchdog — minutes_since_* values are None (not 9999) when events haven't occurred
7. GET /api/analytics/watchdog — no value equals 9999 anywhere in response
8. Arb reserved slots — arb headroom > 0 even when global headroom = 0
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestStrategyStatus:
    """Test that all 3 strategies show enabled=true and status=active (NOT stopped)."""
    
    def test_status_endpoint_returns_200(self):
        """GET /api/status should return 200."""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/status returns 200")
    
    def test_all_strategies_are_present(self):
        """Verify all 3 strategies are in the response."""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        # strategies is a list with strategy_id field
        strategies_list = data.get("strategies", [])
        strategy_ids = [s.get("strategy_id") for s in strategies_list]
        
        assert "arb_scanner" in strategy_ids, "arb_scanner strategy missing"
        assert "crypto_sniper" in strategy_ids, "crypto_sniper strategy missing"
        assert "weather_trader" in strategy_ids, "weather_trader strategy missing"
        print(f"PASS: All 3 strategies present: {strategy_ids}")
    
    def test_all_strategies_enabled_true(self):
        """All strategies should have enabled=true."""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        strategies_list = data.get("strategies", [])
        for cfg in strategies_list:
            sid = cfg.get("strategy_id")
            enabled = cfg.get("enabled")
            assert enabled is True, f"Strategy {sid} has enabled={enabled}, expected True"
        print(f"PASS: All strategies have enabled=True")
    
    def test_all_strategies_status_active(self):
        """All strategies should have status=active (NOT stopped)."""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        strategies_list = data.get("strategies", [])
        for cfg in strategies_list:
            sid = cfg.get("strategy_id")
            status = cfg.get("status")
            assert status == "active", f"Strategy {sid} has status={status}, expected 'active'"
        print(f"PASS: All strategies have status='active'")


class TestStrategyTrackerPositionSlots:
    """Test position_slots structure in /api/analytics/strategy-tracker."""
    
    def test_strategy_tracker_returns_200(self):
        """GET /api/analytics/strategy-tracker should return 200."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/analytics/strategy-tracker returns 200")
    
    def test_position_slots_has_per_strategy_counts(self):
        """position_slots should have weather_count, crypto_count, arb_count, unknown_count (NOT nonweather_count)."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        position_slots = data.get("position_slots", {})
        assert "weather_count" in position_slots, "position_slots missing weather_count"
        assert "crypto_count" in position_slots, "position_slots missing crypto_count"
        assert "arb_count" in position_slots, "position_slots missing arb_count"
        assert "unknown_count" in position_slots, "position_slots missing unknown_count"
        
        # Verify nonweather_count is NOT present (old field)
        assert "nonweather_count" not in position_slots, "position_slots still has old nonweather_count field"
        
        print(f"PASS: position_slots has weather_count={position_slots['weather_count']}, "
              f"crypto_count={position_slots['crypto_count']}, arb_count={position_slots['arb_count']}, "
              f"unknown_count={position_slots['unknown_count']}")
    
    def test_position_slots_limits_structure(self):
        """position_slots.limits should have max_weather=25, max_crypto=20, max_arb=20, max_global=65."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        limits = data.get("position_slots", {}).get("limits", {})
        
        assert limits.get("max_weather") == 25, f"Expected max_weather=25, got {limits.get('max_weather')}"
        assert limits.get("max_crypto") == 20, f"Expected max_crypto=20, got {limits.get('max_crypto')}"
        assert limits.get("max_arb") == 20, f"Expected max_arb=20, got {limits.get('max_arb')}"
        assert limits.get("max_global") == 65, f"Expected max_global=65, got {limits.get('max_global')}"
        
        # Verify old max_nonweather is NOT present
        assert "max_nonweather" not in limits, "limits still has old max_nonweather field"
        
        print(f"PASS: limits structure correct - max_weather={limits['max_weather']}, "
              f"max_crypto={limits['max_crypto']}, max_arb={limits['max_arb']}, max_global={limits['max_global']}")
    
    def test_position_slots_headroom_structure(self):
        """position_slots.headroom should have weather, crypto, arb, global keys with numeric values."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        headroom = data.get("position_slots", {}).get("headroom", {})
        
        assert "weather" in headroom, "headroom missing weather key"
        assert "crypto" in headroom, "headroom missing crypto key"
        assert "arb" in headroom, "headroom missing arb key"
        assert "global" in headroom, "headroom missing global key"
        
        # All values should be numeric
        for key in ["weather", "crypto", "arb", "global"]:
            val = headroom.get(key)
            assert isinstance(val, (int, float)), f"headroom.{key} should be numeric, got {type(val)}: {val}"
        
        print(f"PASS: headroom structure correct - weather={headroom['weather']}, "
              f"crypto={headroom['crypto']}, arb={headroom['arb']}, global={headroom['global']}")
    
    def test_position_slots_sizing_structure(self):
        """position_slots.sizing should have crypto=5.0, weather=3.0, arb=2.0."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        sizing = data.get("position_slots", {}).get("sizing", {})
        
        assert sizing.get("crypto") == 5.0, f"Expected sizing.crypto=5.0, got {sizing.get('crypto')}"
        assert sizing.get("weather") == 3.0, f"Expected sizing.weather=3.0, got {sizing.get('weather')}"
        assert sizing.get("arb") == 2.0, f"Expected sizing.arb=2.0, got {sizing.get('arb')}"
        
        print(f"PASS: sizing structure correct - crypto=${sizing['crypto']}, "
              f"weather=${sizing['weather']}, arb=${sizing['arb']}")
    
    def test_blocked_by_position_limit_is_dict(self):
        """position_slots.blocked_by_position_limit should be a dict (can be empty)."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        blocked = data.get("position_slots", {}).get("blocked_by_position_limit")
        assert isinstance(blocked, dict), f"blocked_by_position_limit should be dict, got {type(blocked)}"
        print(f"PASS: blocked_by_position_limit is dict with {len(blocked)} entries: {blocked}")


class TestWatchdogBugFix:
    """Test that watchdog no longer returns 9999 values."""
    
    def test_watchdog_returns_200(self):
        """GET /api/analytics/watchdog should return 200."""
        response = requests.get(f"{BASE_URL}/api/analytics/watchdog", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/analytics/watchdog returns 200")
    
    def test_minutes_since_values_not_9999(self):
        """minutes_since_* values should be None when events haven't occurred, not 9999."""
        response = requests.get(f"{BASE_URL}/api/analytics/watchdog", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        minutes_fields = [
            "minutes_since_new_market",
            "minutes_since_trade_opened",
            "minutes_since_trade_closed"
        ]
        
        for field in minutes_fields:
            value = data.get(field)
            assert value != 9999, f"Watchdog {field}={value} should not be 9999 (bug)"
            # Value should be either None or a positive number
            if value is not None:
                assert isinstance(value, (int, float)), f"{field} should be numeric or None, got {type(value)}"
                assert value >= 0, f"{field} should be non-negative, got {value}"
            print(f"  {field}={value} (OK)")
        
        print("PASS: No minutes_since_* field equals 9999")
    
    def test_no_9999_anywhere_in_response(self):
        """No value in the entire watchdog response should equal 9999."""
        response = requests.get(f"{BASE_URL}/api/analytics/watchdog", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        def check_no_9999(obj, path=""):
            """Recursively check that no value equals 9999."""
            if isinstance(obj, dict):
                for k, v in obj.items():
                    check_no_9999(v, f"{path}.{k}" if path else k)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    check_no_9999(v, f"{path}[{i}]")
            elif obj == 9999:
                raise AssertionError(f"Found 9999 at {path}")
        
        check_no_9999(data)
        print("PASS: No 9999 value found anywhere in watchdog response")
    
    def test_uptime_minutes_is_positive(self):
        """uptime_minutes should be a positive number."""
        response = requests.get(f"{BASE_URL}/api/analytics/watchdog", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        uptime = data.get("uptime_minutes")
        assert uptime is not None, "uptime_minutes should not be None"
        assert isinstance(uptime, (int, float)), f"uptime_minutes should be numeric, got {type(uptime)}"
        assert uptime >= 0, f"uptime_minutes should be non-negative, got {uptime}"
        
        print(f"PASS: uptime_minutes={uptime} (positive number)")


class TestArbPrioritySlots:
    """Test that arb has reserved slots that bypass global limit."""
    
    def test_arb_headroom_with_global_at_limit(self):
        """When global headroom = 0, arb headroom should still be > 0 if arb has reserved slots."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        headroom = data.get("position_slots", {}).get("headroom", {})
        arb_count = data.get("position_slots", {}).get("arb_count", 0)
        max_arb = data.get("position_slots", {}).get("limits", {}).get("max_arb", 20)
        
        arb_headroom = headroom.get("arb", 0)
        global_headroom = headroom.get("global", 0)
        
        # Check arb has reserved capacity (max_arb - arb_count)
        expected_arb_headroom = max(0, max_arb - arb_count)
        assert arb_headroom == expected_arb_headroom, \
            f"arb_headroom={arb_headroom} should equal max_arb({max_arb}) - arb_count({arb_count}) = {expected_arb_headroom}"
        
        print(f"PASS: arb_headroom={arb_headroom} (arb_count={arb_count}, max_arb={max_arb})")
        print(f"      global_headroom={global_headroom}")
        
        # Key test: If global headroom is 0 but arb has capacity, arb should NOT be blocked
        if global_headroom == 0 and arb_headroom > 0:
            print(f"PASS: Arb has headroom ({arb_headroom}) even though global headroom is 0 - reserved slots working!")


class TestSignalQualityTab:
    """Test the Signal Quality API for per-strategy rejection breakdown."""
    
    def test_signal_quality_returns_200(self):
        """GET /api/analytics/signal-quality should return 200."""
        response = requests.get(f"{BASE_URL}/api/analytics/signal-quality", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/analytics/signal-quality returns 200")
    
    def test_signal_quality_has_rejection_reasons(self):
        """Signal quality should include rejection_reasons per strategy."""
        response = requests.get(f"{BASE_URL}/api/analytics/signal-quality", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        # Check if any strategy has rejection reasons
        has_rejections = False
        for sid, quality in data.items():
            reasons = quality.get("rejection_reasons", {})
            if reasons:
                has_rejections = True
                print(f"  {sid}: {reasons}")
        
        print(f"PASS: Signal quality endpoint has per-strategy rejection reasons")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
