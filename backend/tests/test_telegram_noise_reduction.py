"""
Telegram Noise Reduction Test Suite
====================================
Tests for reduced Telegram notifications:
- Only TRADE EXECUTED and TRADE CLOSED alerts sent
- Weather alerts no longer sent to Telegram (total_telegram_sent=0)
- TelegramNotifier only subscribes to ORDER_UPDATE events
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestTelegramConfig:
    """Test Telegram configuration endpoints"""
    
    def test_telegram_configured(self):
        """GET /api/config returns telegram.configured=true"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data.get('telegram', {}).get('configured') is True, "Telegram should be configured"
    
    def test_telegram_enabled(self):
        """GET /api/config returns telegram.enabled=true"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data.get('telegram', {}).get('enabled') is True, "Telegram should be enabled"
    
    def test_telegram_credentials_present(self):
        """GET /api/config returns credentials_present.telegram=true"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert data.get('credentials_present', {}).get('telegram') is True


class TestWeatherAlertsTelegramRemoved:
    """Test that weather alerts no longer send to Telegram"""
    
    def test_weather_alerts_total_telegram_sent_zero(self):
        """GET /api/strategies/weather/alerts shows total_telegram_sent=0"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/alerts")
        assert response.status_code == 200
        data = response.json()
        stats = data.get('stats', {})
        assert stats.get('total_telegram_sent') == 0, \
            f"Expected total_telegram_sent=0, got {stats.get('total_telegram_sent')}"
    
    def test_weather_alerts_endpoint_returns_stats(self):
        """GET /api/strategies/weather/alerts returns proper stats structure"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/alerts")
        assert response.status_code == 200
        data = response.json()
        
        # Verify stats structure
        assert 'stats' in data
        stats = data['stats']
        assert 'total_generated' in stats
        assert 'total_debounced' in stats
        assert 'total_telegram_sent' in stats
        assert 'active_cooldowns' in stats
        assert 'alerts_buffered' in stats
        assert 'enabled' in stats


class TestTelegramTestEndpoint:
    """Test Telegram test message endpoint"""
    
    def test_telegram_test_returns_success_format(self):
        """POST /api/telegram/test returns success=true (Note: Only testing once per instruction)"""
        # NOTE: Per agent instructions, DO NOT send multiple test messages to Telegram
        # Just verify the endpoint is accessible and returns proper format
        response = requests.post(f"{BASE_URL}/api/telegram/test")
        assert response.status_code == 200
        data = response.json()
        
        # Should have success and stats keys
        assert 'success' in data, "Response should have 'success' key"
        assert 'stats' in data, "Response should have 'stats' key"
        assert data['success'] is True, "Test message should succeed"


class TestRegressionEndpoints:
    """Regression tests for all critical endpoints"""
    
    def test_status_endpoint(self):
        """Regression: GET /api/status returns 200"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data
        assert 'mode' in data
    
    def test_health_endpoint(self):
        """Regression: GET /api/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'
    
    def test_global_analytics_endpoint(self):
        """Regression: GET /api/analytics/global returns 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        assert response.status_code == 200
        data = response.json()
        assert 'strategy_performance' in data
        assert 'forecast_quality' in data
    
    def test_auto_resolver_health(self):
        """Regression: GET /api/health/auto-resolver returns running=true"""
        response = requests.get(f"{BASE_URL}/api/health/auto-resolver")
        assert response.status_code == 200
        data = response.json()
        assert data.get('running') is True, "Auto-resolver should be running"
    
    def test_weather_strategy_health(self):
        """Regression: GET /api/strategies/weather/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        # Verify key health fields exist
        assert 'total_scans' in data
        assert 'config' in data
        assert 'alert_stats' in data
    
    def test_arb_strategy_health(self):
        """Regression: GET /api/strategies/arb/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        data = response.json()
        assert 'config' in data
        assert 'running' in data
    
    def test_sniper_strategy_health(self):
        """Regression: GET /api/strategies/sniper/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert 'config' in data
        assert 'running' in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
