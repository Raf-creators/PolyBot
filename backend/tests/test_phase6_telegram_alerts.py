"""
Phase 6: Telegram Alerts Integration Tests
Tests the TelegramNotifier service and related API endpoints.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestTelegramAlertEndpoints:
    """Tests for Telegram alert-related API endpoints"""

    def test_alerts_test_returns_skipped_when_no_credentials(self):
        """GET /api/alerts/test returns 200 with status='skipped' when no Telegram credentials"""
        response = requests.get(f"{BASE_URL}/api/alerts/test")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "skipped"
        assert "reason" in data
        assert "credentials" in data["reason"].lower()

    def test_alerts_status_returns_correct_structure(self):
        """GET /api/alerts/status returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/alerts/status")
        assert response.status_code == 200
        data = response.json()
        # Verify all expected fields are present
        assert "configured" in data
        assert "enabled" in data
        assert "signals_enabled" in data
        assert "total_sent" in data
        assert "total_failed" in data
        # Verify types
        assert isinstance(data["configured"], bool)
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["signals_enabled"], bool)
        assert isinstance(data["total_sent"], int)
        assert isinstance(data["total_failed"], int)

    def test_config_includes_telegram_section(self):
        """GET /api/config includes telegram section with all required fields"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        # Verify telegram section exists
        assert "telegram" in data
        tg = data["telegram"]
        # Verify all fields
        assert "configured" in tg
        assert "enabled" in tg
        assert "signals_enabled" in tg
        assert "total_sent" in tg
        assert "total_failed" in tg
        # Also verify credentials_present includes telegram
        assert "credentials_present" in data
        assert "telegram" in data["credentials_present"]


class TestTelegramConfigUpdates:
    """Tests for updating Telegram configuration via PUT /api/config"""

    def test_enable_telegram_alerts(self):
        """PUT /api/config with telegram_enabled=true updates the notifier state"""
        # First reset to false
        requests.put(f"{BASE_URL}/api/config", json={"telegram_enabled": False})
        
        # Enable
        response = requests.put(f"{BASE_URL}/api/config", json={"telegram_enabled": True})
        assert response.status_code == 200
        assert response.json().get("status") == "updated"
        
        # Verify status changed
        status = requests.get(f"{BASE_URL}/api/alerts/status").json()
        assert status["enabled"] is True

    def test_disable_telegram_alerts(self):
        """PUT /api/config with telegram_enabled=false reverts the notifier state"""
        # First enable
        requests.put(f"{BASE_URL}/api/config", json={"telegram_enabled": True})
        
        # Disable
        response = requests.put(f"{BASE_URL}/api/config", json={"telegram_enabled": False})
        assert response.status_code == 200
        assert response.json().get("status") == "updated"
        
        # Verify status changed
        status = requests.get(f"{BASE_URL}/api/alerts/status").json()
        assert status["enabled"] is False

    def test_enable_telegram_signals(self):
        """PUT /api/config with telegram_signals_enabled=true works"""
        # Reset
        requests.put(f"{BASE_URL}/api/config", json={"telegram_signals_enabled": False})
        
        # Enable signals
        response = requests.put(f"{BASE_URL}/api/config", json={"telegram_signals_enabled": True})
        assert response.status_code == 200
        
        # Verify
        status = requests.get(f"{BASE_URL}/api/alerts/status").json()
        assert status["signals_enabled"] is True

    def test_toggle_preserves_other_setting(self):
        """Enabling one toggle doesn't reset the other"""
        # Enable both
        requests.put(f"{BASE_URL}/api/config", json={"telegram_enabled": True, "telegram_signals_enabled": True})
        
        # Toggle just signals off
        requests.put(f"{BASE_URL}/api/config", json={"telegram_signals_enabled": False})
        
        # Verify enabled is still true
        status = requests.get(f"{BASE_URL}/api/alerts/status").json()
        assert status["enabled"] is True
        assert status["signals_enabled"] is False
        
        # Toggle signals back on
        requests.put(f"{BASE_URL}/api/config", json={"telegram_signals_enabled": True})
        status = requests.get(f"{BASE_URL}/api/alerts/status").json()
        assert status["enabled"] is True
        assert status["signals_enabled"] is True


class TestTelegramNotifierNoCredentials:
    """Tests verifying graceful behavior without credentials"""

    def test_notifier_not_configured(self):
        """Telegram notifier reports configured=false when no credentials set"""
        response = requests.get(f"{BASE_URL}/api/alerts/status")
        assert response.status_code == 200
        assert response.json()["configured"] is False

    def test_test_alert_skips_gracefully(self):
        """Test alert endpoint gracefully skips without error when not configured"""
        response = requests.get(f"{BASE_URL}/api/alerts/test")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        # Should not have 'failed' status even without credentials


class TestRegressionApis:
    """Regression tests for existing APIs"""

    def test_health_endpoint(self):
        """GET /api/health returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_ticker_feed_returns_array(self):
        """GET /api/ticker/feed returns array"""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_pnl_history_returns_correct_structure(self):
        """GET /api/analytics/pnl-history returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        assert "points" in data
        assert "current_pnl" in data
        assert "peak_pnl" in data
        assert "trough_pnl" in data
        assert "max_drawdown" in data
        assert "total_trades" in data

    def test_status_endpoint(self):
        """GET /api/status returns expected structure"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data  # engine status
        assert "mode" in data  # trading mode

    def test_strategies_arb_health(self):
        """GET /api/strategies/arb/health works"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200

    def test_strategies_sniper_health(self):
        """GET /api/strategies/sniper/health works"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
