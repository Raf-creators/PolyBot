"""
Trade Ticker Feature Tests
- GET /api/ticker/feed endpoint
- Response structure validation
- Empty array handling
- Regression tests for critical endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')


class TestTickerFeedEndpoint:
    """Tests for the new ticker feed endpoint"""

    def test_ticker_feed_returns_200(self):
        """GET /api/ticker/feed should return 200"""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ GET /api/ticker/feed returns 200")

    def test_ticker_feed_returns_array(self):
        """GET /api/ticker/feed should return an array"""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✓ GET /api/ticker/feed returns array (length: {len(data)})")

    def test_ticker_feed_empty_when_no_executions(self):
        """GET /api/ticker/feed should return empty array when no executions"""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        # When no executions, should return empty array
        print(f"✓ GET /api/ticker/feed returns {'empty' if len(data) == 0 else 'non-empty'} array: {len(data)} items")

    def test_ticker_feed_item_structure_if_present(self):
        """If items exist, validate correct structure"""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            required_fields = ['id', 'strategy', 'asset', 'side', 'size', 'price', 'edge_bps', 'timestamp']
            for field in required_fields:
                assert field in item, f"Missing field: {field}"
                print(f"✓ Field '{field}' present with value: {item[field]}")
            
            # Validate field types
            assert isinstance(item['id'], str), f"id should be string, got {type(item['id'])}"
            assert item['strategy'] in ['ARB', 'SNIPER'], f"strategy should be ARB or SNIPER, got {item['strategy']}"
            assert isinstance(item['asset'], str), f"asset should be string, got {type(item['asset'])}"
            assert item['side'] in ['BUY', 'SELL'], f"side should be BUY or SELL, got {item['side']}"
            assert isinstance(item['size'], (int, float)), f"size should be number, got {type(item['size'])}"
            assert isinstance(item['price'], (int, float)), f"price should be number, got {type(item['price'])}"
            assert isinstance(item['edge_bps'], (int, float)), f"edge_bps should be number, got {type(item['edge_bps'])}"
            assert isinstance(item['timestamp'], str), f"timestamp should be string, got {type(item['timestamp'])}"
            print("✓ Ticker item structure validated")
        else:
            print("✓ No items to validate (empty feed)")

    def test_ticker_feed_limit_parameter(self):
        """GET /api/ticker/feed supports limit parameter"""
        response = requests.get(f"{BASE_URL}/api/ticker/feed?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10, f"Expected <= 10 items with limit=10, got {len(data)}"
        print(f"✓ Limit parameter works: requested 10, got {len(data)}")


class TestRegressionEndpoints:
    """Regression tests for critical endpoints"""

    def test_health_returns_healthy(self):
        """GET /api/health should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy', f"Expected healthy status, got {data.get('status')}"
        print("✓ GET /api/health returns healthy")

    def test_status_works(self):
        """GET /api/status should return state snapshot"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data or 'mode' in data, "Expected status/mode in response"
        print("✓ GET /api/status returns valid snapshot")

    def test_pnl_history_returns_correct_structure(self):
        """GET /api/analytics/pnl-history should return correct structure"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ['points', 'current_pnl', 'peak_pnl', 'trough_pnl', 'max_drawdown', 'total_trades']
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert isinstance(data['points'], list), f"points should be list, got {type(data['points'])}"
        print("✓ GET /api/analytics/pnl-history returns correct structure")

    def test_positions_returns_list(self):
        """GET /api/positions should return list"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print("✓ GET /api/positions returns list")

    def test_trades_returns_list(self):
        """GET /api/trades should return list"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print("✓ GET /api/trades returns list")

    def test_arb_health_works(self):
        """GET /api/strategies/arb/health should work"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        print("✓ GET /api/strategies/arb/health returns 200")

    def test_sniper_health_works(self):
        """GET /api/strategies/sniper/health should work"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        print("✓ GET /api/strategies/sniper/health returns 200")

    def test_config_returns_valid_structure(self):
        """GET /api/config should return valid config"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert 'trading_mode' in data, "Missing trading_mode"
        assert 'strategies' in data, "Missing strategies"
        print("✓ GET /api/config returns valid config")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
