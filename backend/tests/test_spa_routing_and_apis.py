"""
Test Suite: SPA Routing and Core API Verification
Tests that all dashboard routes return HTML and API endpoints return JSON.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

if not BASE_URL:
    BASE_URL = "https://edge-trading-hub-1.preview.emergentagent.com"


class TestSPARouting:
    """Test that all SPA routes return HTML (not JSON 404)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "text/html"})
    
    def test_root_returns_html(self):
        """GET / should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: Root (/) returns HTML")
    
    def test_positions_page_returns_html(self):
        """GET /positions should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/positions")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /positions returns HTML")
    
    def test_sniper_page_returns_html(self):
        """GET /sniper should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/sniper")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /sniper returns HTML")
    
    def test_weather_page_returns_html(self):
        """GET /weather should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/weather")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /weather returns HTML")
    
    def test_analytics_page_returns_html(self):
        """GET /analytics should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/analytics")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /analytics returns HTML")
    
    def test_global_analytics_page_returns_html(self):
        """GET /global-analytics should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/global-analytics")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /global-analytics returns HTML")
    
    def test_risk_page_returns_html(self):
        """GET /risk should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/risk")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /risk returns HTML")
    
    def test_markets_page_returns_html(self):
        """GET /markets should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/markets")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /markets returns HTML")
    
    def test_settings_page_returns_html(self):
        """GET /settings should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/settings")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /settings returns HTML")
    
    def test_arbitrage_page_returns_html(self):
        """GET /arbitrage should return HTML dashboard"""
        resp = self.session.get(f"{BASE_URL}/arbitrage")
        assert resp.status_code == 200
        assert "<!doctype html>" in resp.text.lower() or "<!DOCTYPE html>" in resp.text
        print("PASS: /arbitrage returns HTML")


class TestCoreAPIs:
    """Test core API endpoints return JSON with correct status"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_api_health_returns_json(self):
        """GET /api/health should return JSON with status=ok"""
        resp = self.session.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"
        assert "engine" in data
        assert "strategies" in data
        print(f"PASS: /api/health returns status={data['status']}, engine={data['engine']}")
    
    def test_api_positions_returns_json_array(self):
        """GET /api/positions should return JSON array"""
        resp = self.session.get(f"{BASE_URL}/api/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: /api/positions returns array with {len(data)} positions")
    
    def test_api_health_discovery_returns_json(self):
        """GET /api/health/discovery should return JSON discovery stats"""
        resp = self.session.get(f"{BASE_URL}/api/health/discovery")
        assert resp.status_code == 200
        data = resp.json()
        # Should have crypto market discovery stats
        assert "crypto_markets_discovered" in data or "broad_markets_loaded" in data
        print(f"PASS: /api/health/discovery returns discovery stats")
    
    def test_api_status_returns_json(self):
        """GET /api/status should return full engine status"""
        resp = self.session.get(f"{BASE_URL}/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data
        assert "positions" in data or "strategies" in data
        print(f"PASS: /api/status returns engine status")
    
    def test_api_config_returns_json(self):
        """GET /api/config should return configuration"""
        resp = self.session.get(f"{BASE_URL}/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "trading_mode" in data
        assert "strategies" in data
        print(f"PASS: /api/config returns trading_mode={data['trading_mode']}")
    
    def test_api_markets_returns_json(self):
        """GET /api/markets should return market list"""
        resp = self.session.get(f"{BASE_URL}/api/markets")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: /api/markets returns {len(data)} markets")
    
    def test_api_trades_returns_json(self):
        """GET /api/trades should return trade list"""
        resp = self.session.get(f"{BASE_URL}/api/trades")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: /api/trades returns {len(data)} trades")
    
    def test_api_orders_returns_json(self):
        """GET /api/orders should return order list"""
        resp = self.session.get(f"{BASE_URL}/api/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: /api/orders returns {len(data)} orders")


class TestStrategyAPIs:
    """Test strategy-specific API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_api_sniper_health(self):
        """GET /api/strategies/sniper/health returns health status"""
        resp = self.session.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        print(f"PASS: /api/strategies/sniper/health returns running={data.get('running')}")
    
    def test_api_weather_health(self):
        """GET /api/strategies/weather/health returns health status"""
        resp = self.session.get(f"{BASE_URL}/api/strategies/weather/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        print(f"PASS: /api/strategies/weather/health returns running={data.get('running')}")
    
    def test_api_arb_health(self):
        """GET /api/strategies/arb/health returns health status"""
        resp = self.session.get(f"{BASE_URL}/api/strategies/arb/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data or "total_scans" in data
        print(f"PASS: /api/strategies/arb/health returns data")
    
    def test_api_market_resolver_health(self):
        """GET /api/health/market-resolver returns resolver status"""
        resp = self.session.get(f"{BASE_URL}/api/health/market-resolver")
        assert resp.status_code == 200
        data = resp.json()
        # Resolver should be running
        assert "running" in data
        print(f"PASS: /api/health/market-resolver returns running={data.get('running')}")


class TestTelegramNotifierEndpoints:
    """Test Telegram notification endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_api_alerts_status(self):
        """GET /api/alerts/status returns Telegram configuration"""
        resp = self.session.get(f"{BASE_URL}/api/alerts/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "configured" in data
        assert "enabled" in data
        print(f"PASS: /api/alerts/status configured={data.get('configured')}, enabled={data.get('enabled')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
