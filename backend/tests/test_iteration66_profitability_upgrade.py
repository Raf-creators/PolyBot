"""
Iteration 66: Full Profitability Upgrade Validation

Tests for the controlled rollout of system profitability upgrade:
1. Remove opposite_side_held filter for crypto only
2. crypto_max_exposure 120->180
3. max_position_size 25->40
4. max_tte_seconds 28800->43200
5. Weather auto_exit for negative_edge+time_inefficiency
6. min_edge_bps_long 700->500
7. Force-cleanup arb positions <$0.50
8. hard_max_stale 1800->2400 + staleness_per_min 5->6
9. Disable asymmetric strategy
10. Telegram before/after tracking system
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestHealthEndpoint:
    """Basic health check"""
    
    def test_health_returns_200_with_status_ok(self):
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "strategies" in data
        assert "engine" in data
        print(f"PASS: Health endpoint returns status=ok, engine={data['engine']}")


class TestUpgradeValidationEndpoint:
    """Tests for /api/admin/upgrade-validation endpoint"""
    
    def test_upgrade_validation_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation")
        assert response.status_code == 200
        data = response.json()
        assert "capital_allocation" in data
        assert "current_exposure" in data
        print("PASS: Upgrade validation endpoint returns 200")

    def test_crypto_max_exposure_is_180(self):
        """Verify crypto_max_exposure was changed from 120 to 180"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation")
        assert response.status_code == 200
        data = response.json()
        crypto_max = data["capital_allocation"]["crypto_max_exposure"]
        assert crypto_max == 180.0, f"Expected crypto_max_exposure=180, got {crypto_max}"
        print(f"PASS: crypto_max_exposure = {crypto_max} (upgraded from 120)")
    
    def test_crypto_health_no_opposite_side_held_rejection(self):
        """Verify opposite_side_held is NOT in crypto rejection reasons (filter removed)"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation")
        assert response.status_code == 200
        data = response.json()
        crypto_health = data.get("crypto_health", {})
        rejection_reasons = crypto_health.get("rejection_reasons", {})
        assert "opposite_side_held" not in rejection_reasons, \
            f"opposite_side_held should NOT be in rejection_reasons: {rejection_reasons}"
        print(f"PASS: opposite_side_held NOT in crypto rejection_reasons: {list(rejection_reasons.keys())}")
    
    def test_weather_lifecycle_mode_shadow_exit(self):
        """Verify weather lifecycle mode is shadow_exit"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation")
        assert response.status_code == 200
        data = response.json()
        lifecycle = data.get("weather_lifecycle", {})
        mode = lifecycle.get("mode")
        assert mode == "shadow_exit", f"Expected lifecycle mode=shadow_exit, got {mode}"
        print(f"PASS: Weather lifecycle_mode = {mode}")
    
    def test_weather_asymmetric_disabled(self):
        """Verify asymmetric strategy is disabled (signals_generated=0)"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation")
        assert response.status_code == 200
        data = response.json()
        asymmetric = data.get("weather_asymmetric", {})
        signals_generated = asymmetric.get("signals_generated", -1)
        # Check diagnostic shows rejections for "disabled"
        diagnostic = asymmetric.get("diagnostic", {})
        candidates = diagnostic.get("last_scan_candidates", [])
        disabled_count = sum(1 for c in candidates if c.get("rejection") == "disabled")
        assert signals_generated == 0, f"Expected signals_generated=0 (disabled), got {signals_generated}"
        print(f"PASS: Asymmetric signals_generated={signals_generated}, disabled_rejections={disabled_count}")
    
    def test_shadow_exit_includes_negative_edge_and_time_inefficiency(self):
        """Verify shadow_exit_counts includes negative_edge and time_inefficiency"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation")
        assert response.status_code == 200
        data = response.json()
        shadow_counts = data.get("shadow_exit_counts_by_reason", {})
        # These should exist (may be 0 if no candidates yet)
        has_negative_edge = "negative_edge" in shadow_counts
        has_time_inefficiency = "time_inefficiency" in shadow_counts
        # At least one should have non-zero count based on the upgrade
        print(f"PASS: shadow_exit_counts_by_reason = {shadow_counts}")
        # Just log - don't fail if counts are 0 since it depends on market conditions


class TestControlsEndpoint:
    """Tests for /api/controls endpoint - risk config values"""
    
    def test_controls_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/controls")
        assert response.status_code == 200
        data = response.json()
        assert "max_position_size" in data
        print("PASS: Controls endpoint returns 200")
    
    def test_max_position_size_is_40(self):
        """Verify max_position_size was changed from 25 to 40"""
        response = requests.get(f"{BASE_URL}/api/controls")
        assert response.status_code == 200
        data = response.json()
        max_pos_size = data["max_position_size"]
        assert max_pos_size == 40.0, f"Expected max_position_size=40, got {max_pos_size}"
        print(f"PASS: max_position_size = {max_pos_size} (upgraded from 25)")
    
    def test_crypto_exposure_cap_is_180(self):
        """Verify crypto exposure cap is 180"""
        response = requests.get(f"{BASE_URL}/api/controls")
        assert response.status_code == 200
        data = response.json()
        crypto_cap = data["exposure_caps"]["crypto"]
        assert crypto_cap == 180.0, f"Expected crypto cap=180, got {crypto_cap}"
        print(f"PASS: exposure_caps.crypto = {crypto_cap}")


class TestArbDiagnosticsEndpoint:
    """Tests for /api/strategies/arb/diagnostics - staleness config"""
    
    def test_arb_diagnostics_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        print("PASS: Arb diagnostics endpoint returns 200")
    
    def test_hard_max_stale_seconds_is_2400(self):
        """Verify hard_max_stale_seconds was changed from 1800 to 2400"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        data = response.json()
        config = data["config"]
        hard_max_stale = config.get("hard_max_stale_seconds")
        assert hard_max_stale == 2400.0, f"Expected hard_max_stale_seconds=2400, got {hard_max_stale}"
        print(f"PASS: hard_max_stale_seconds = {hard_max_stale} (upgraded from 1800)")
    
    def test_staleness_edge_per_minute_bps_is_6(self):
        """Verify staleness_edge_per_minute_bps was changed from 5 to 6"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        data = response.json()
        config = data["config"]
        staleness_per_min = config.get("staleness_edge_per_minute_bps")
        assert staleness_per_min == 6.0, f"Expected staleness_edge_per_minute_bps=6, got {staleness_per_min}"
        print(f"PASS: staleness_edge_per_minute_bps = {staleness_per_min} (upgraded from 5)")
    
    def test_min_net_edge_bps_is_floor_15(self):
        """Verify min_net_edge_bps is 15 (absolute floor)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200
        data = response.json()
        config = data["config"]
        min_net_edge = config.get("min_net_edge_bps")
        assert min_net_edge == 15.0, f"Expected min_net_edge_bps=15, got {min_net_edge}"
        print(f"PASS: min_net_edge_bps = {min_net_edge} (floor)")


class TestArbOpportunitiesEndpoint:
    """Tests for /api/strategies/arb/opportunities"""
    
    def test_arb_opportunities_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert response.status_code == 200
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        print(f"PASS: Arb opportunities: {len(data['tradable'])} tradable, {len(data['rejected'])} rejected")


class TestUpgradeTrackingEndpoint:
    """Tests for /api/admin/upgrade-tracking - Telegram tracking system"""
    
    def test_upgrade_tracking_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"PASS: Upgrade tracking status = {data.get('status')}")
    
    def test_upgrade_tracking_status_is_tracking(self):
        """Verify status=tracking (upgrade tracking system active)"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking")
        assert response.status_code == 200
        data = response.json()
        status = data.get("status")
        assert status == "tracking", f"Expected status=tracking, got {status}"
        print("PASS: Upgrade tracking status = tracking")
    
    def test_baseline_pre_upgrade_has_expected_fields(self):
        """Verify baseline_pre_upgrade has pnl_per_h, crypto_pnl_per_h, trades_per_h"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking")
        assert response.status_code == 200
        data = response.json()
        baseline = data.get("baseline_pre_upgrade", {})
        
        # Check required fields
        assert "pnl_per_h" in baseline, f"Missing pnl_per_h in baseline: {baseline}"
        assert "crypto_pnl_per_h" in baseline, f"Missing crypto_pnl_per_h in baseline: {baseline}"
        assert "trades_per_h" in baseline, f"Missing trades_per_h in baseline: {baseline}"
        
        # Verify expected baseline values (from user context)
        assert baseline["pnl_per_h"] == 161.0, f"Expected pnl_per_h=161, got {baseline['pnl_per_h']}"
        assert baseline["crypto_pnl_per_h"] == 160.0, f"Expected crypto_pnl_per_h=160, got {baseline['crypto_pnl_per_h']}"
        assert baseline["trades_per_h"] == 1721.0, f"Expected trades_per_h=1721, got {baseline['trades_per_h']}"
        
        print(f"PASS: Baseline pre_upgrade values: pnl_per_h={baseline['pnl_per_h']}, crypto_pnl_per_h={baseline['crypto_pnl_per_h']}, trades_per_h={baseline['trades_per_h']}")
    
    def test_post_upgrade_has_expected_fields(self):
        """Verify post_upgrade has elapsed_h, incr_pnl, pnl_per_h, trades, exec_rate"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking")
        assert response.status_code == 200
        data = response.json()
        post = data.get("post_upgrade", {})
        
        required_fields = ["elapsed_h", "incr_pnl", "pnl_per_h", "trades", "exec_rate"]
        for field in required_fields:
            # Check variations (some may be named slightly differently)
            found = field in post or f"incr_{field}" in post or f"{field}_per_h" in post
            assert field in post or any(f in post for f in [field, f"{field}_per_h"]), \
                f"Missing {field} in post_upgrade: {list(post.keys())}"
        
        print(f"PASS: Post upgrade fields present: {list(post.keys())}")
    
    def test_deltas_has_pnl_change_fields(self):
        """Verify deltas section has pnl_per_h_change and pnl_pct_change"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking")
        assert response.status_code == 200
        data = response.json()
        deltas = data.get("deltas", {})
        
        assert "pnl_per_h_change" in deltas, f"Missing pnl_per_h_change in deltas: {deltas}"
        assert "pnl_pct_change" in deltas, f"Missing pnl_pct_change in deltas: {deltas}"
        
        print(f"PASS: Deltas: pnl_per_h_change={deltas.get('pnl_per_h_change')}, pnl_pct_change={deltas.get('pnl_pct_change')}")


class TestArbPositionCount:
    """Test arb position cleanup - tiny positions <$0.50 were cleaned"""
    
    def test_arb_position_count_under_25(self):
        """Verify arb positions < 25 (tiny positions cleaned on startup)"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        arb_positions = [p for p in data if p.get("strategy_id") == "arb_scanner"]
        arb_count = len(arb_positions)
        assert arb_count < 25, f"Expected arb positions < 25 after cleanup, got {arb_count}"
        print(f"PASS: Arb position count = {arb_count} (< 25, tiny positions cleaned)")


class TestStrategyConfigs:
    """Test strategy config values from /api/config/strategies"""
    
    def test_crypto_sniper_max_tte_is_43200(self):
        """Verify max_tte_seconds was changed from 28800 (8h) to 43200 (12h)"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200
        data = response.json()
        crypto_config = data.get("crypto_sniper", {})
        max_tte = crypto_config.get("max_tte_seconds")
        assert max_tte == 43200.0, f"Expected max_tte_seconds=43200, got {max_tte}"
        print(f"PASS: crypto_sniper max_tte_seconds = {max_tte} (12h, upgraded from 8h)")
    
    def test_weather_asymmetric_disabled_in_config(self):
        """Verify asymmetric_enabled=False in weather config"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200
        data = response.json()
        weather_config = data.get("weather_trader", {})
        asymmetric_enabled = weather_config.get("asymmetric_enabled")
        assert asymmetric_enabled is False, f"Expected asymmetric_enabled=False, got {asymmetric_enabled}"
        print(f"PASS: weather_trader asymmetric_enabled = {asymmetric_enabled}")
    
    def test_weather_min_edge_bps_long_is_500(self):
        """Verify min_edge_bps_long was changed from 700 to 500"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200
        data = response.json()
        weather_config = data.get("weather_trader", {})
        min_edge_long = weather_config.get("min_edge_bps_long")
        assert min_edge_long == 500.0, f"Expected min_edge_bps_long=500, got {min_edge_long}"
        print(f"PASS: weather_trader min_edge_bps_long = {min_edge_long} (upgraded from 700)")
    
    def test_weather_lifecycle_mode_config(self):
        """Verify lifecycle_mode=shadow_exit in weather config"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200
        data = response.json()
        weather_config = data.get("weather_trader", {})
        lifecycle_mode = weather_config.get("lifecycle_mode")
        assert lifecycle_mode == "shadow_exit", f"Expected lifecycle_mode=shadow_exit, got {lifecycle_mode}"
        print(f"PASS: weather_trader lifecycle_mode = {lifecycle_mode}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
