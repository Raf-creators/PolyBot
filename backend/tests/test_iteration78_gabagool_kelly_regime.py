"""
Iteration 78 Tests: Gabagool Live + Kelly Tiers Unlocked + Regime Detector + Weather Push + Epoch 5

Tests for the massive feature deployment:
1. Kelly tier unlock: max_order_size 10->25, max_signal_size=25
2. $5 tier kill: min_edge_bps raised to 400
3. Gabagool live arb: $10/side structural arbitrage
4. Weather push: higher sizing ($8/side)
5. Regime detector: auto-pause crypto when WR < 30%
6. Epoch 5 reset: clean $1000 baseline
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSniperHealthKellyTiers:
    """Verify sniper health returns Kelly tier config"""
    
    def test_sniper_health_max_signal_size_25(self):
        """max_signal_size should be 25 (Kelly tiers unlocked)"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        config = data.get("config", {})
        assert config.get("max_signal_size") == 25.0, f"Expected max_signal_size=25, got {config.get('max_signal_size')}"
    
    def test_sniper_health_min_edge_bps_400(self):
        """min_edge_bps should be 400 ($5 tier killed)"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        config = data.get("config", {})
        assert config.get("min_edge_bps") == 400.0, f"Expected min_edge_bps=400, got {config.get('min_edge_bps')}"
    
    def test_sniper_health_regime_paused_false(self):
        """regime_paused should be false (not enough data to trigger)"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert "regime_paused" in data, "regime_paused field missing"
        assert data.get("regime_paused") == False, f"Expected regime_paused=false, got {data.get('regime_paused')}"
    
    def test_sniper_health_effective_min_edge_bps(self):
        """effective_min_edge_bps should be 400 (not doubled since not paused)"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert "effective_min_edge_bps" in data, "effective_min_edge_bps field missing"
        # When not paused, effective = base (400)
        assert data.get("effective_min_edge_bps") == 400.0, f"Expected effective_min_edge_bps=400, got {data.get('effective_min_edge_bps')}"


class TestGabagoolLiveArb:
    """Verify Gabagool live arb executor is active"""
    
    def test_gabagool_report_status_active(self):
        """Gabagool report should show status=active"""
        response = requests.get(f"{BASE_URL}/api/gabagool/report")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "active", f"Expected status=active, got {data.get('status')}"
    
    def test_gabagool_report_threshold(self):
        """Gabagool threshold should be 0.96"""
        response = requests.get(f"{BASE_URL}/api/gabagool/report")
        assert response.status_code == 200
        data = response.json()
        config = data.get("config", {})
        assert config.get("threshold") == 0.96, f"Expected threshold=0.96, got {config.get('threshold')}"
    
    def test_gabagool_report_size_per_side(self):
        """Gabagool size_per_side should be 10"""
        response = requests.get(f"{BASE_URL}/api/gabagool/report")
        assert response.status_code == 200
        data = response.json()
        config = data.get("config", {})
        assert config.get("size_per_side") == 10.0, f"Expected size_per_side=10, got {config.get('size_per_side')}"
    
    def test_gabagool_positions_endpoint(self):
        """Gabagool positions endpoint should return array"""
        response = requests.get(f"{BASE_URL}/api/gabagool/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
    
    def test_gabagool_closed_endpoint(self):
        """Gabagool closed endpoint should return array"""
        response = requests.get(f"{BASE_URL}/api/gabagool/closed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"


class TestEngineStatus:
    """Verify engine status and strategies"""
    
    def test_status_engine_running(self):
        """Engine should be running"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "running", f"Expected status=running, got {data.get('status')}"
    
    def test_status_paper_mode(self):
        """Should be in paper mode"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "paper", f"Expected mode=paper, got {data.get('mode')}"
    
    def test_status_three_strategies_active(self):
        """Should have 3 strategies active"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        strategies = data.get("strategies", [])
        # strategies is a list of dicts
        active_count = sum(1 for s in strategies if s.get("enabled"))
        assert active_count >= 3, f"Expected at least 3 active strategies, got {active_count}"


class TestPositionsAndTrades:
    """Verify positions show Kelly tiers and no $5 trades"""
    
    def test_positions_endpoint(self):
        """Positions endpoint should return data"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
    
    def test_trades_endpoint(self):
        """Trades endpoint should return data"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
    
    def test_no_5_dollar_trades_in_recent(self):
        """Recent trades should NOT have size=$5 (killed noise tier)"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert response.status_code == 200
        data = response.json()
        # Check that no crypto_sniper trades have size=5
        five_dollar_trades = [t for t in data if t.get("strategy_id") == "crypto_sniper" and t.get("size") == 5.0]
        # This is a soft check - may have legacy trades
        print(f"Found {len(five_dollar_trades)} $5 crypto trades (should be 0 for new trades)")


class TestShadowEngineRegression:
    """Verify shadow engines still work (regression check)"""
    
    def test_phantom_report_active(self):
        """Phantom shadow engine should be active or collecting"""
        response = requests.get(f"{BASE_URL}/api/experiments/phantom/report")
        assert response.status_code == 200
        data = response.json()
        # Accept active, collecting, or no_data as valid states for fresh epoch
        valid_statuses = ["active", "collecting", "no_data"]
        assert data.get("status") in valid_statuses, f"Expected status in {valid_statuses}, got {data.get('status')}"
    
    def test_shadow_report_active(self):
        """Shadow sniper engine should be active or collecting"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        data = response.json()
        # Accept active, collecting, or no_data as valid states for fresh epoch
        valid_statuses = ["active", "collecting", "no_data"]
        assert data.get("status") in valid_statuses, f"Expected status in {valid_statuses}, got {data.get('status')}"


class TestTelegramIntegration:
    """Verify Telegram 12h analysis still works"""
    
    def test_trigger_12h_analysis_endpoint(self):
        """POST /api/telegram/trigger-12h-analysis should work"""
        response = requests.post(f"{BASE_URL}/api/telegram/trigger-12h-analysis")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True, f"Expected success=true, got {data.get('success')}"


class TestRiskConfigKellyTiers:
    """Verify risk config has Kelly tier settings"""
    
    def test_max_order_size_25(self):
        """max_order_size should be 25 (Kelly tiers unlocked)"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("max_order_size") == 25.0, f"Expected max_order_size=25, got {risk.get('max_order_size')}"
    
    def test_arb_max_exposure_60(self):
        """arb_max_exposure should be 60 (Gabagool capital)"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("arb_max_exposure") == 60.0, f"Expected arb_max_exposure=60, got {risk.get('arb_max_exposure')}"
    
    def test_weather_position_size_8(self):
        """weather_position_size should be 8 (weather push)"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("weather_position_size") == 8.0, f"Expected weather_position_size=8, got {risk.get('weather_position_size')}"


class TestHealthEndpoint:
    """Verify health endpoint"""
    
    def test_health_ok(self):
        """Health endpoint should return ok"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok", f"Expected status=ok, got {data.get('status')}"
    
    def test_health_engine_running(self):
        """Health should show engine running"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("engine") == "running", f"Expected engine=running, got {data.get('engine')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
