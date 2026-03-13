"""
Phase 5B: Crypto Sniper Dashboard Integration Tests
Tests for sniper backend APIs supporting the frontend dashboard.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestSniperSignalsEndpoint:
    """GET /api/strategies/sniper/signals tests"""

    def test_signals_endpoint_returns_200(self):
        """Signals endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert response.status_code == 200

    def test_signals_has_correct_structure(self):
        """Response should have tradable, rejected, total_tradable, total_rejected"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        assert "total_tradable" in data
        assert "total_rejected" in data
        assert isinstance(data["tradable"], list)
        assert isinstance(data["rejected"], list)

    def test_signals_limit_parameter(self):
        """Limit parameter should be accepted"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals?limit=10")
        assert response.status_code == 200


class TestSniperExecutionsEndpoint:
    """GET /api/strategies/sniper/executions tests"""

    def test_executions_endpoint_returns_200(self):
        """Executions endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/executions")
        assert response.status_code == 200

    def test_executions_has_correct_structure(self):
        """Response should have active and completed lists"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/executions")
        data = response.json()
        assert "active" in data
        assert "completed" in data
        assert isinstance(data["active"], list)
        assert isinstance(data["completed"], list)


class TestSniperHealthEndpoint:
    """GET /api/strategies/sniper/health tests"""

    def test_health_endpoint_returns_200(self):
        """Health endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200

    def test_health_has_config(self):
        """Response should have config object"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        assert "config" in data
        config = data["config"]
        # Check key config fields that frontend displays
        assert "scan_interval" in config
        assert "min_edge_bps" in config
        assert "min_liquidity" in config
        assert "min_confidence" in config
        assert "max_spread" in config
        assert "min_tte_seconds" in config
        assert "max_tte_seconds" in config

    def test_health_has_running_state(self):
        """Response should have running boolean"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        assert "running" in data
        assert isinstance(data["running"], bool)

    def test_health_has_price_buffer_sizes(self):
        """Response should have price_buffer_sizes for BTC and ETH"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        assert "price_buffer_sizes" in data

    def test_health_has_scanner_metrics(self):
        """Response should have scanner metrics displayed in frontend"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        # Check metrics shown in Scanner Metrics section
        assert "total_scans" in data
        assert "last_scan_duration_ms" in data
        assert "markets_classified" in data
        assert "markets_evaluated" in data
        assert "signals_generated" in data
        assert "signals_rejected" in data
        assert "signals_executed" in data
        assert "signals_filled" in data
        assert "active_executions" in data
        assert "completed_executions" in data
        assert "stale_feed_skips" in data

    def test_health_has_rejection_reasons(self):
        """Response should have rejection_reasons dict"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        assert "rejection_reasons" in data
        assert isinstance(data["rejection_reasons"], dict)

    def test_health_has_volatility_data(self):
        """Response should have volatility data for frontend display"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        # These are displayed in Volatility section
        assert "btc_realized_vol" in data or "btc_realized_vol" is None
        assert "eth_realized_vol" in data or "eth_realized_vol" is None


class TestExistingEndpointsRegression:
    """Ensure existing endpoints still work after Phase 5B"""

    def test_health_endpoint(self):
        """GET /api/health should return healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_status_shows_crypto_sniper_strategy(self):
        """GET /api/status should show crypto_sniper in strategies"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        strategy_names = [s["name"] for s in data["strategies"]]
        # Strategy name is "Crypto Sniper" (display name)
        assert "Crypto Sniper" in strategy_names

    def test_arb_opportunities_endpoint(self):
        """GET /api/strategies/arb/opportunities should still work"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert response.status_code == 200
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data

    def test_arb_health_endpoint(self):
        """GET /api/strategies/arb/health should still work"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200

    def test_arb_executions_endpoint(self):
        """GET /api/strategies/arb/executions should still work"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/executions")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "completed" in data

    def test_positions_endpoint(self):
        """GET /api/positions should return list"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_trades_endpoint(self):
        """GET /api/trades should return list"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_orders_endpoint(self):
        """GET /api/orders should return list"""
        response = requests.get(f"{BASE_URL}/api/orders")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_markets_endpoint(self):
        """GET /api/markets should return list"""
        response = requests.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_config_endpoint(self):
        """GET /api/config should return config with strategies"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        # Should have crypto_sniper strategy config
        assert "crypto_sniper" in data["strategies"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
