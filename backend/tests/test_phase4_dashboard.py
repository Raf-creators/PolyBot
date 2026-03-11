"""
Phase 4 Trading Dashboard - Backend API Tests
Tests for all dashboard-related endpoints: status, config, engine control, positions, arb data
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestHealthEndpoints:
    """Test basic health and status endpoints"""
    
    def test_root_endpoint(self, api_client):
        """GET / - API root returns info"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert data["name"] == "Polymarket Edge OS"
        assert data["status"] == "online"
    
    def test_health_endpoint(self, api_client):
        """GET /health - Returns engine health"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "engine" in data
        assert "mode" in data
    
    def test_status_endpoint(self, api_client):
        """GET /status - Returns full state snapshot"""
        response = api_client.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        # Verify required fields for dashboard
        assert "status" in data
        assert "mode" in data
        assert "strategies" in data
        assert "risk" in data
        assert "stats" in data
        assert isinstance(data["strategies"], list)


class TestConfigEndpoints:
    """Test configuration endpoints"""
    
    def test_get_config(self, api_client):
        """GET /config - Returns trading config"""
        response = api_client.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "trading_mode" in data
        assert "risk" in data
        assert "strategies" in data
        assert "credentials_present" in data
        # Verify risk config structure
        risk = data["risk"]
        assert "max_daily_loss" in risk
        assert "max_order_size" in risk
    
    def test_update_risk_config(self, api_client):
        """PUT /config - Update risk settings"""
        # Get current config
        get_resp = api_client.get(f"{BASE_URL}/api/config")
        original_risk = get_resp.json()["risk"]
        
        # Update risk config
        new_risk = {
            "risk": {
                **original_risk,
                "max_order_size": 15.0
            }
        }
        response = api_client.put(f"{BASE_URL}/api/config", json=new_risk)
        assert response.status_code == 200
        
        # Verify update persisted
        verify_resp = api_client.get(f"{BASE_URL}/api/config")
        assert verify_resp.json()["risk"]["max_order_size"] == 15.0
        
        # Restore original
        restore_risk = {"risk": original_risk}
        api_client.put(f"{BASE_URL}/api/config", json=restore_risk)
    
    def test_mode_change_without_credentials(self, api_client):
        """PUT /config - Live mode requires credentials"""
        response = api_client.put(f"{BASE_URL}/api/config", json={"trading_mode": "live"})
        # Should fail without Polymarket credentials
        assert response.status_code == 400


class TestEngineControl:
    """Test engine start/stop"""
    
    def test_start_engine(self, api_client):
        """POST /engine/start - Start trading engine"""
        # First ensure engine is stopped
        api_client.post(f"{BASE_URL}/api/engine/stop")
        time.sleep(0.5)
        
        response = api_client.post(f"{BASE_URL}/api/engine/start")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert "mode" in data
        
        # Verify status changed
        status_resp = api_client.get(f"{BASE_URL}/api/status")
        assert status_resp.json()["status"] == "running"
    
    def test_start_already_running(self, api_client):
        """POST /engine/start - Returns 400 if already running"""
        # Start engine first
        api_client.post(f"{BASE_URL}/api/engine/start")
        time.sleep(0.5)
        
        response = api_client.post(f"{BASE_URL}/api/engine/start")
        assert response.status_code == 400
    
    def test_stop_engine(self, api_client):
        """POST /engine/stop - Stop trading engine"""
        # Ensure running first
        api_client.post(f"{BASE_URL}/api/engine/start")
        time.sleep(0.5)
        
        response = api_client.post(f"{BASE_URL}/api/engine/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        
        # Verify status changed
        status_resp = api_client.get(f"{BASE_URL}/api/status")
        assert status_resp.json()["status"] == "stopped"
    
    def test_stop_already_stopped(self, api_client):
        """POST /engine/stop - Returns 400 if not running"""
        api_client.post(f"{BASE_URL}/api/engine/stop")
        time.sleep(0.5)
        
        response = api_client.post(f"{BASE_URL}/api/engine/stop")
        assert response.status_code == 400


class TestRiskControls:
    """Test risk management endpoints"""
    
    def test_activate_kill_switch(self, api_client):
        """POST /risk/kill-switch/activate - Activate kill switch"""
        response = api_client.post(f"{BASE_URL}/api/risk/kill-switch/activate")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "kill_switch_activated"
        
        # Verify in status
        status = api_client.get(f"{BASE_URL}/api/status").json()
        assert status["risk"]["kill_switch_active"] == True
    
    def test_deactivate_kill_switch(self, api_client):
        """POST /risk/kill-switch/deactivate - Deactivate kill switch"""
        # Activate first
        api_client.post(f"{BASE_URL}/api/risk/kill-switch/activate")
        
        response = api_client.post(f"{BASE_URL}/api/risk/kill-switch/deactivate")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "kill_switch_deactivated"
        
        # Verify in status
        status = api_client.get(f"{BASE_URL}/api/status").json()
        assert status["risk"]["kill_switch_active"] == False


class TestDataEndpoints:
    """Test positions, trades, orders, markets endpoints"""
    
    def test_get_positions(self, api_client):
        """GET /positions - Returns positions list"""
        response = api_client.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_trades(self, api_client):
        """GET /trades - Returns trades list"""
        response = api_client.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_orders(self, api_client):
        """GET /orders - Returns orders list"""
        response = api_client.get(f"{BASE_URL}/api/orders")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_markets(self, api_client):
        """GET /markets - Returns markets list"""
        response = api_client.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_markets_summary(self, api_client):
        """GET /markets/summary - Returns market summary"""
        response = api_client.get(f"{BASE_URL}/api/markets/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_markets" in data
        assert "top_by_volume" in data


class TestArbStrategyEndpoints:
    """Test arbitrage strategy endpoints"""
    
    def test_get_arb_opportunities(self, api_client):
        """GET /strategies/arb/opportunities - Returns arb opportunities"""
        response = api_client.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert response.status_code == 200
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        assert "total_tradable" in data
        assert "total_rejected" in data
    
    def test_get_arb_executions(self, api_client):
        """GET /strategies/arb/executions - Returns arb executions"""
        response = api_client.get(f"{BASE_URL}/api/strategies/arb/executions")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "completed" in data
    
    def test_get_arb_health(self, api_client):
        """GET /strategies/arb/health - Returns arb scanner health"""
        response = api_client.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "total_scans" in data
        assert "config" in data


class TestFeedHealth:
    """Test feed health endpoint"""
    
    def test_get_feed_health(self, api_client):
        """GET /health/feeds - Returns feed health status"""
        response = api_client.get(f"{BASE_URL}/api/health/feeds")
        assert response.status_code == 200
        data = response.json()
        # Health data should have feed status fields
        assert isinstance(data, dict)


class TestInjectTestData:
    """Test data injection for demo/testing"""
    
    def test_inject_arb_opportunity(self, api_client):
        """POST /test/inject-arb-opportunity - Injects test arb data"""
        # Start engine first
        api_client.post(f"{BASE_URL}/api/engine/start")
        time.sleep(0.5)
        
        response = api_client.post(f"{BASE_URL}/api/test/inject-arb-opportunity")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "injected"
        assert "condition_id" in data
        assert "yes_token_id" in data
        assert "no_token_id" in data
        
        # Clean up
        api_client.post(f"{BASE_URL}/api/engine/stop")


class TestCleanup:
    """Clean up after all tests"""
    
    def test_final_cleanup(self, api_client):
        """Ensure engine is stopped and kill switch off"""
        api_client.post(f"{BASE_URL}/api/engine/stop")
        api_client.post(f"{BASE_URL}/api/risk/kill-switch/deactivate")
        
        status = api_client.get(f"{BASE_URL}/api/status").json()
        assert status["risk"]["kill_switch_active"] == False
