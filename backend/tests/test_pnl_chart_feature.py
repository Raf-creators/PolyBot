"""
Test suite for P&L Chart feature - Phase 6: P&L Equity Curve
Tests the new /api/analytics/pnl-history endpoint and regression tests for existing APIs
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestPnlHistoryEndpoint:
    """Tests for GET /api/analytics/pnl-history endpoint"""

    def test_pnl_history_returns_200(self):
        """Verify endpoint returns 200 status"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ GET /api/analytics/pnl-history returns 200")

    def test_pnl_history_structure(self):
        """Verify response has correct structure: points, current_pnl, peak_pnl, trough_pnl, max_drawdown, total_trades"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        required_fields = ['points', 'current_pnl', 'peak_pnl', 'trough_pnl', 'max_drawdown', 'total_trades']
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Type checks
        assert isinstance(data['points'], list), "points should be a list"
        assert isinstance(data['current_pnl'], (int, float)), "current_pnl should be numeric"
        assert isinstance(data['peak_pnl'], (int, float)), "peak_pnl should be numeric"
        assert isinstance(data['trough_pnl'], (int, float)), "trough_pnl should be numeric"
        assert isinstance(data['max_drawdown'], (int, float)), "max_drawdown should be numeric"
        assert isinstance(data['total_trades'], int), "total_trades should be an integer"
        
        print(f"✓ Response structure valid with {len(required_fields)} required fields")

    def test_pnl_history_empty_state(self):
        """When no trades exist, points should be empty array and metrics should be zero"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        
        # With no trades, we expect:
        # - points: [] (empty array)
        # - current_pnl: 0.0
        # - peak_pnl: 0.0
        # - trough_pnl: 0.0
        # - max_drawdown: 0.0
        # - total_trades: 0
        if data['total_trades'] == 0:
            assert data['points'] == [], "points should be empty when no trades"
            assert data['current_pnl'] == 0.0, "current_pnl should be 0 when no trades"
            assert data['peak_pnl'] == 0.0, "peak_pnl should be 0 when no trades"
            assert data['trough_pnl'] == 0.0, "trough_pnl should be 0 when no trades"
            assert data['max_drawdown'] == 0.0, "max_drawdown should be 0 when no trades"
            print("✓ Empty state verified: all metrics are zero")
        else:
            print(f"✓ Trades exist ({data['total_trades']}), skipping empty state check")

    def test_pnl_history_point_structure(self):
        """If points exist, each point should have timestamp, cumulative_pnl, trade_pnl, strategy"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        
        if data['points']:
            point = data['points'][0]
            expected_fields = ['timestamp', 'cumulative_pnl', 'trade_pnl', 'strategy']
            for field in expected_fields:
                assert field in point, f"Point missing field: {field}"
            print(f"✓ Point structure valid with {len(expected_fields)} fields")
        else:
            print("✓ No points to check (empty state)")


class TestRegressionEndpoints:
    """Regression tests for existing API endpoints"""

    def test_health_endpoint(self):
        """GET /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy', f"Expected healthy, got {data['status']}"
        print("✓ GET /api/health returns healthy")

    def test_status_endpoint(self):
        """GET /api/status returns status snapshot"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data, "Missing status field"
        assert 'mode' in data, "Missing mode field"
        assert 'strategies' in data, "Missing strategies field"
        print("✓ GET /api/status returns valid snapshot")

    def test_sniper_health_endpoint(self):
        """GET /api/strategies/sniper/health works"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert 'config' in data, "Missing config in sniper health"
        assert 'running' in data, "Missing running in sniper health"
        print("✓ GET /api/strategies/sniper/health works")

    def test_arb_health_endpoint(self):
        """GET /api/strategies/arb/health works"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        data = response.json()
        assert 'config' in data, "Missing config in arb health"
        assert 'running' in data, "Missing running in arb health"
        print("✓ GET /api/strategies/arb/health works")

    def test_positions_endpoint(self):
        """GET /api/positions returns list"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "positions should return a list"
        print("✓ GET /api/positions returns list")

    def test_trades_endpoint(self):
        """GET /api/trades returns list"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "trades should return a list"
        print("✓ GET /api/trades returns list")

    def test_orders_endpoint(self):
        """GET /api/orders returns list"""
        response = requests.get(f"{BASE_URL}/api/orders")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "orders should return a list"
        print("✓ GET /api/orders returns list")

    def test_markets_endpoint(self):
        """GET /api/markets returns list"""
        response = requests.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "markets should return a list"
        print("✓ GET /api/markets returns list")

    def test_config_endpoint(self):
        """GET /api/config returns configuration"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert 'trading_mode' in data, "Missing trading_mode in config"
        assert 'strategies' in data, "Missing strategies in config"
        print("✓ GET /api/config returns valid config")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
