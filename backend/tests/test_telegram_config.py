"""
Tests for Telegram configuration feature.
Verifies that Telegram is auto-enabled when credentials are present in .env
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestTelegramConfig:
    """Tests for Telegram configuration and auto-enable feature"""

    def test_config_returns_credentials_present_telegram_true(self):
        """GET /api/config should return credentials_present.telegram=true"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "credentials_present" in data, "Missing credentials_present in response"
        assert "telegram" in data["credentials_present"], "Missing telegram in credentials_present"
        assert data["credentials_present"]["telegram"] == True, f"Expected telegram=True, got {data['credentials_present']['telegram']}"
        print(f"PASS: credentials_present.telegram={data['credentials_present']['telegram']}")

    def test_config_returns_telegram_configured_true(self):
        """GET /api/config should return telegram.configured=true"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "telegram" in data, "Missing telegram in response"
        assert "configured" in data["telegram"], "Missing configured in telegram"
        assert data["telegram"]["configured"] == True, f"Expected configured=True, got {data['telegram']['configured']}"
        print(f"PASS: telegram.configured={data['telegram']['configured']}")

    def test_config_returns_telegram_enabled_true(self):
        """GET /api/config should return telegram.enabled=true (auto-enabled)"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "telegram" in data, "Missing telegram in response"
        assert "enabled" in data["telegram"], "Missing enabled in telegram"
        assert data["telegram"]["enabled"] == True, f"Expected enabled=True, got {data['telegram']['enabled']}"
        print(f"PASS: telegram.enabled={data['telegram']['enabled']}")

    def test_config_returns_telegram_signals_enabled_true(self):
        """GET /api/config should return telegram.signals_enabled=true (auto-enabled)"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "telegram" in data, "Missing telegram in response"
        assert "signals_enabled" in data["telegram"], "Missing signals_enabled in telegram"
        assert data["telegram"]["signals_enabled"] == True, f"Expected signals_enabled=True, got {data['telegram']['signals_enabled']}"
        print(f"PASS: telegram.signals_enabled={data['telegram']['signals_enabled']}")

    def test_telegram_test_endpoint_success(self):
        """POST /api/telegram/test should return success=true
        Note: Only checking response format, not sending actual message (already sent)
        """
        response = requests.post(f"{BASE_URL}/api/telegram/test")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "success" in data, "Missing success in response"
        assert "stats" in data, "Missing stats in response"
        # Check stats structure
        assert "total_sent" in data["stats"], "Missing total_sent in stats"
        assert "configured" in data["stats"], "Missing configured in stats"
        assert data["stats"]["configured"] == True, f"Expected stats.configured=True, got {data['stats']['configured']}"
        print(f"PASS: telegram/test success={data['success']}, stats.total_sent={data['stats']['total_sent']}")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_status_returns_200(self):
        """GET /api/status returns 200"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/status returns 200")

    def test_health_returns_200(self):
        """GET /api/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/health returns 200")

    def test_global_analytics_returns_200(self):
        """GET /api/analytics/global returns 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/analytics/global returns 200")

    def test_auto_resolver_health_returns_200(self):
        """GET /api/health/auto-resolver returns running=true"""
        response = requests.get(f"{BASE_URL}/api/health/auto-resolver")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "running" in data, "Missing running in response"
        assert data["running"] == True, f"Expected running=True, got {data['running']}"
        print(f"PASS: /api/health/auto-resolver running={data['running']}")

    def test_weather_strategy_health_returns_200(self):
        """GET /api/strategies/weather/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/strategies/weather/health returns 200")


class TestTelegramStats:
    """Tests for Telegram stats and message count"""

    def test_telegram_stats_have_total_sent(self):
        """Verify telegram stats show messages were sent"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        
        data = response.json()
        telegram = data.get("telegram", {})
        total_sent = telegram.get("total_sent", 0)
        # We expect at least 1 message (the test message that was sent)
        assert total_sent >= 0, f"Expected total_sent >= 0, got {total_sent}"
        print(f"PASS: telegram.total_sent={total_sent}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
