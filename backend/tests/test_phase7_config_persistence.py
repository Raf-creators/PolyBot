"""
Phase 7: Configuration Persistence System Tests

Tests config persistence to MongoDB across server restarts.
ConfigService handles load/save/apply for engine and strategy configs.
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestConfigPersistence:
    """GET /api/config returns persistence metadata and strategy_configs"""

    def test_config_returns_persisted_true(self):
        """GET /api/config returns 200 with persisted=true"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "persisted" in data
        assert data["persisted"] is True

    def test_config_returns_last_saved_timestamp(self):
        """GET /api/config includes last_saved timestamp"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "last_saved" in data
        # Should be an ISO timestamp string
        assert data["last_saved"] is None or isinstance(data["last_saved"], str)
        if data["last_saved"]:
            assert "T" in data["last_saved"]  # ISO format contains T

    def test_config_includes_strategy_configs(self):
        """GET /api/config includes strategy_configs with arb_scanner and crypto_sniper"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "strategy_configs" in data
        strategy_configs = data["strategy_configs"]
        assert "arb_scanner" in strategy_configs
        assert "crypto_sniper" in strategy_configs

    def test_strategy_configs_arb_fields(self):
        """arb_scanner config includes expected fields"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        arb = response.json()["strategy_configs"]["arb_scanner"]
        expected_fields = [
            "scan_interval", "min_net_edge_bps", "min_liquidity",
            "min_confidence", "max_stale_age_seconds", "max_arb_size",
            "max_concurrent_arbs", "default_size", "maker_taker_rate",
            "resolution_fee_rate", "slippage_base_bps"
        ]
        for field in expected_fields:
            assert field in arb, f"Missing field {field} in arb_scanner config"

    def test_strategy_configs_sniper_fields(self):
        """crypto_sniper config includes expected fields"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        sniper = response.json()["strategy_configs"]["crypto_sniper"]
        expected_fields = [
            "scan_interval", "min_edge_bps", "min_confidence",
            "max_concurrent_signals", "cooldown_seconds"
        ]
        for field in expected_fields:
            assert field in sniper, f"Missing field {field} in crypto_sniper config"


class TestGetStrategyConfigs:
    """GET /api/config/strategies returns detailed strategy parameters"""

    def test_get_strategy_configs_success(self):
        """GET /api/config/strategies returns 200"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200

    def test_strategy_configs_has_both_strategies(self):
        """Response includes arb_scanner and crypto_sniper"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        data = response.json()
        assert "arb_scanner" in data
        assert "crypto_sniper" in data

    def test_strategy_configs_include_enabled_flag(self):
        """Each strategy config includes enabled flag"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        data = response.json()
        assert "enabled" in data["arb_scanner"]
        assert "enabled" in data["crypto_sniper"]
        assert isinstance(data["arb_scanner"]["enabled"], bool)
        assert isinstance(data["crypto_sniper"]["enabled"], bool)


class TestPostConfigUpdate:
    """POST /api/config/update granular strategy parameter updates"""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Save original value before test and restore after"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        self.original_min_edge = response.json()["arb_scanner"]["min_net_edge_bps"]
        yield
        # Restore original value
        requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"arb_scanner": {"min_net_edge_bps": self.original_min_edge}}}
        )

    def test_update_arb_scanner_parameter(self):
        """POST /api/config/update updates arb_scanner min_net_edge_bps"""
        test_value = 88
        response = requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"arb_scanner": {"min_net_edge_bps": test_value}}}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["persisted"] is True
        assert "arb_scanner" in data["changes"]

    def test_update_persists_value(self):
        """POST /api/config/update value actually persists in GET"""
        test_value = 66
        # Update
        requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"arb_scanner": {"min_net_edge_bps": test_value}}}
        )
        # Verify
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        assert response.status_code == 200
        actual = response.json()["arb_scanner"]["min_net_edge_bps"]
        assert actual == test_value, f"Expected {test_value}, got {actual}"

    def test_update_sniper_parameter(self):
        """POST /api/config/update updates crypto_sniper min_edge_bps"""
        response = requests.get(f"{BASE_URL}/api/config/strategies")
        original = response.json()["crypto_sniper"]["min_edge_bps"]
        
        test_value = 250
        update_resp = requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"crypto_sniper": {"min_edge_bps": test_value}}}
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["persisted"] is True

        # Verify and restore
        verify_resp = requests.get(f"{BASE_URL}/api/config/strategies")
        assert verify_resp.json()["crypto_sniper"]["min_edge_bps"] == test_value
        
        # Restore
        requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"crypto_sniper": {"min_edge_bps": original}}}
        )

    def test_update_invalid_value_type_returns_400(self):
        """POST /api/config/update with invalid type returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/config/update",
            json={"strategies": {"arb_scanner": {"min_net_edge_bps": "not_a_number"}}}
        )
        assert response.status_code == 400
        assert "Invalid arb config" in response.json()["detail"]


class TestPutConfig:
    """PUT /api/config now returns persisted=true"""

    def test_put_config_returns_persisted_true(self):
        """PUT /api/config returns persisted=true"""
        response = requests.put(
            f"{BASE_URL}/api/config",
            json={"trading_mode": "paper"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["persisted"] is True


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_health_endpoint(self):
        """GET /api/health returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_alerts_test_endpoint(self):
        """GET /api/alerts/test works"""
        response = requests.get(f"{BASE_URL}/api/alerts/test")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_ticker_feed_returns_array(self):
        """GET /api/ticker/feed returns array"""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pnl_history_works(self):
        """GET /api/analytics/pnl-history works"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        assert "points" in data
        assert "current_pnl" in data

    def test_arb_health_works(self):
        """GET /api/strategies/arb/health works"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200

    def test_sniper_health_works(self):
        """GET /api/strategies/sniper/health works"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200

    def test_status_endpoint(self):
        """GET /api/status returns expected structure"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "stats" in data
