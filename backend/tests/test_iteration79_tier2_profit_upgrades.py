"""
Iteration 79: Tier 1 + Tier 2 Profit Optimization Upgrades Testing

Tests the config-only changes from overnight analysis:
- (A) crypto_max_exposure $80→$150
- (B) max_position_size 25→35, max_order_size 25→35, new $35 Kelly tier at >=1200bps, window caps raised
- (C) arb_max_exposure $250→$40, arb_reserved_capital $250→$40, max_arb_positions 45→12
- (D) Gabagool threshold 0.985→0.960
- (E) Weather profit_capture_threshold 2.0→1.5
- (F) Crypto cooldown 60s→30s
- (G) Daily loss limit $100→$150
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://edge-trading-hub-1.preview.emergentagent.com').rstrip('/')


class TestStatusEndpoint:
    """Test /api/status returns correct status"""
    
    def test_status_returns_200(self):
        """Status endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/status returns 200")
    
    def test_engine_running(self):
        """Engine should be running"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        data = response.json()
        assert data.get("status") == "running", f"Expected running, got {data.get('status')}"
        print("PASS: Engine status=running")
    
    def test_paper_mode(self):
        """Should be in paper mode"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        data = response.json()
        assert data.get("mode") == "paper", f"Expected paper, got {data.get('mode')}"
        print("PASS: mode=paper")


class TestRiskConfigValues:
    """Test risk config values from /api/config"""
    
    def test_max_position_size_35(self):
        """max_position_size should be 35 (raised from 25)"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("max_position_size") == 35.0, f"Expected 35.0, got {risk.get('max_position_size')}"
        print("PASS: max_position_size=35.0")
    
    def test_max_order_size_35(self):
        """max_order_size should be 35 (raised from 25)"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("max_order_size") == 35.0, f"Expected 35.0, got {risk.get('max_order_size')}"
        print("PASS: max_order_size=35.0")
    
    def test_max_daily_loss_150(self):
        """max_daily_loss should be 150 (raised from 100)"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("max_daily_loss") == 150.0, f"Expected 150.0, got {risk.get('max_daily_loss')}"
        print("PASS: max_daily_loss=150.0")
    
    def test_crypto_max_exposure_150(self):
        """crypto_max_exposure should be 150 (raised from 80)"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("crypto_max_exposure") == 150.0, f"Expected 150.0, got {risk.get('crypto_max_exposure')}"
        print("PASS: crypto_max_exposure=150.0")
    
    def test_arb_max_exposure_40(self):
        """arb_max_exposure should be 40 (reduced from 250)"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("arb_max_exposure") == 40.0, f"Expected 40.0, got {risk.get('arb_max_exposure')}"
        print("PASS: arb_max_exposure=40.0")
    
    def test_arb_reserved_capital_40(self):
        """arb_reserved_capital should be 40 (reduced from 250)"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("arb_reserved_capital") == 40.0, f"Expected 40.0, got {risk.get('arb_reserved_capital')}"
        print("PASS: arb_reserved_capital=40.0")
    
    def test_max_arb_positions_12(self):
        """max_arb_positions should be 12 (reduced from 45)"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        data = response.json()
        risk = data.get("risk", {})
        assert risk.get("max_arb_positions") == 12, f"Expected 12, got {risk.get('max_arb_positions')}"
        print("PASS: max_arb_positions=12")


class TestGabagoolReport:
    """Test /api/gabagool/report returns correct threshold"""
    
    def test_gabagool_report_returns_200(self):
        """Gabagool report endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/gabagool/report", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/gabagool/report returns 200")
    
    def test_gabagool_threshold_0_96(self):
        """Gabagool threshold should be 0.96 (lowered from 0.985)"""
        response = requests.get(f"{BASE_URL}/api/gabagool/report", timeout=30)
        data = response.json()
        config = data.get("config", {})
        threshold = config.get("threshold")
        assert threshold == 0.96 or threshold == 0.960, f"Expected 0.96, got {threshold}"
        print(f"PASS: Gabagool threshold={threshold}")
    
    def test_gabagool_status_active(self):
        """Gabagool should be active"""
        response = requests.get(f"{BASE_URL}/api/gabagool/report", timeout=30)
        data = response.json()
        assert data.get("status") == "active", f"Expected active, got {data.get('status')}"
        print("PASS: Gabagool status=active")


class TestCryptoSniperConfig:
    """Test crypto sniper config from /api/config/strategies"""
    
    def test_sniper_config_returns_200(self):
        """Strategy config endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/config/strategies", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/config/strategies returns 200")
    
    def test_sniper_max_signal_size_35(self):
        """max_signal_size should be 35 (raised from 25)"""
        response = requests.get(f"{BASE_URL}/api/config/strategies", timeout=30)
        data = response.json()
        config = data.get("crypto_sniper", {})
        assert config.get("max_signal_size") == 35.0, f"Expected 35.0, got {config.get('max_signal_size')}"
        print("PASS: crypto max_signal_size=35.0")
    
    def test_sniper_cooldown_30(self):
        """cooldown_seconds should be 30 (reduced from 60)"""
        response = requests.get(f"{BASE_URL}/api/config/strategies", timeout=30)
        data = response.json()
        config = data.get("crypto_sniper", {})
        assert config.get("cooldown_seconds") == 30.0, f"Expected 30.0, got {config.get('cooldown_seconds')}"
        print("PASS: crypto cooldown_seconds=30.0")
    
    def test_sniper_min_edge_bps_400(self):
        """min_edge_bps should be 400 (kills $5 tier)"""
        response = requests.get(f"{BASE_URL}/api/config/strategies", timeout=30)
        data = response.json()
        config = data.get("crypto_sniper", {})
        assert config.get("min_edge_bps") == 400.0, f"Expected 400.0, got {config.get('min_edge_bps')}"
        print("PASS: crypto min_edge_bps=400.0")


class TestWeatherConfig:
    """Test weather config from /api/config/strategies"""
    
    def test_weather_config_returns_200(self):
        """Strategy config endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/config/strategies", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/config/strategies returns 200")
    
    def test_weather_profit_capture_threshold_1_5(self):
        """profit_capture_threshold should be 1.5 (lowered from 2.0)"""
        response = requests.get(f"{BASE_URL}/api/config/strategies", timeout=30)
        data = response.json()
        config = data.get("weather_trader", {})
        threshold = config.get("profit_capture_threshold")
        assert threshold == 1.5, f"Expected 1.5, got {threshold}"
        print(f"PASS: weather profit_capture_threshold={threshold}")


class TestHealthEndpoint:
    """Test /api/health endpoint"""
    
    def test_health_returns_200(self):
        """Health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/health returns 200")
    
    def test_health_status_ok(self):
        """Health status should be ok"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        data = response.json()
        assert data.get("status") == "ok", f"Expected ok, got {data.get('status')}"
        print("PASS: health status=ok")
    
    def test_health_engine_running(self):
        """Engine should be running"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        data = response.json()
        assert data.get("engine") == "running", f"Expected running, got {data.get('engine')}"
        print("PASS: health engine=running")


class TestConfigEndpoint:
    """Test /api/config endpoint for strategy configs"""
    
    def test_config_returns_200(self):
        """Config endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/config returns 200")
    
    def test_config_has_strategy_configs(self):
        """Config should have strategy_configs"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=30)
        data = response.json()
        assert "strategy_configs" in data, "Missing strategy_configs"
        assert "crypto_sniper" in data["strategy_configs"], "Missing crypto_sniper config"
        assert "weather_trader" in data["strategy_configs"], "Missing weather_trader config"
        print("PASS: config has strategy_configs")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
