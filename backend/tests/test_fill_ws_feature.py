"""
Test suite for CLOB Fill WebSocket Feature (Phase 8C).

Tests the Fill WebSocket health endpoint, graceful degradation without credentials,
and integration with /api/status and /api/execution/status endpoints.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Ensure BASE_URL is set
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable must be set")


class TestFillWsHealthEndpoint:
    """Test GET /api/health/fill-ws endpoint."""

    def test_fill_ws_health_returns_200(self):
        """Fill WS health endpoint should return 200."""
        response = requests.get(f"{BASE_URL}/api/health/fill-ws")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/health/fill-ws returns 200")

    def test_fill_ws_health_has_required_fields(self):
        """Fill WS health should have all required fields."""
        response = requests.get(f"{BASE_URL}/api/health/fill-ws")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "connected",
            "has_credentials",
            "connect_count",
            "disconnect_count",
            "messages_received",
            "trade_events",
            "confirmed_fills",
            "failed_fills",
            "subscribed_markets",
            "last_message_seconds_ago",
            "last_error",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"PASS: Fill WS health has all {len(required_fields)} required fields")

    def test_fill_ws_connected_is_boolean(self):
        """connected field should be a boolean."""
        response = requests.get(f"{BASE_URL}/api/health/fill-ws")
        data = response.json()
        assert isinstance(data["connected"], bool), "connected should be boolean"
        print(f"PASS: connected is boolean (value: {data['connected']})")

    def test_fill_ws_has_credentials_is_boolean(self):
        """has_credentials field should be a boolean."""
        response = requests.get(f"{BASE_URL}/api/health/fill-ws")
        data = response.json()
        assert isinstance(data["has_credentials"], bool), "has_credentials should be boolean"
        print(f"PASS: has_credentials is boolean (value: {data['has_credentials']})")

    def test_fill_ws_no_credentials_no_connection(self):
        """Without credentials, connected should be false and has_credentials false."""
        response = requests.get(f"{BASE_URL}/api/health/fill-ws")
        data = response.json()
        
        # In test environment without credentials, both should be false
        assert data["connected"] == False, "connected should be False without credentials"
        assert data["has_credentials"] == False, "has_credentials should be False without credentials"
        print("PASS: Without credentials - connected=False, has_credentials=False")

    def test_fill_ws_metrics_initialized_correctly(self):
        """Metric counters should be initialized to valid values."""
        response = requests.get(f"{BASE_URL}/api/health/fill-ws")
        data = response.json()
        
        assert isinstance(data["connect_count"], int), "connect_count should be int"
        assert isinstance(data["disconnect_count"], int), "disconnect_count should be int"
        assert isinstance(data["messages_received"], int), "messages_received should be int"
        assert isinstance(data["trade_events"], int), "trade_events should be int"
        assert isinstance(data["confirmed_fills"], int), "confirmed_fills should be int"
        assert isinstance(data["failed_fills"], int), "failed_fills should be int"
        
        assert data["connect_count"] >= 0, "connect_count should be >= 0"
        assert data["disconnect_count"] >= 0, "disconnect_count should be >= 0"
        assert data["trade_events"] >= 0, "trade_events should be >= 0"
        
        print("PASS: All metric counters are properly initialized integers")

    def test_fill_ws_no_error_without_credentials(self):
        """last_error should be null/None when gracefully degraded (no credentials)."""
        response = requests.get(f"{BASE_URL}/api/health/fill-ws")
        data = response.json()
        
        # Without credentials, should gracefully degrade without errors
        assert data["last_error"] is None, f"Expected no error, got: {data['last_error']}"
        print("PASS: No error when gracefully degraded (no credentials)")


class TestStatusEndpointFillWs:
    """Test that /api/status includes Fill WS health info."""

    def test_status_returns_200(self):
        """GET /api/status should return 200."""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        print("PASS: GET /api/status returns 200")

    def test_status_has_fill_ws_connected(self):
        """stats.health should include fill_ws_connected."""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        
        assert "stats" in data, "Response should have 'stats'"
        assert "health" in data["stats"], "stats should have 'health'"
        health = data["stats"]["health"]
        
        assert "fill_ws_connected" in health, "health should have 'fill_ws_connected'"
        assert isinstance(health["fill_ws_connected"], bool), "fill_ws_connected should be boolean"
        print(f"PASS: stats.health.fill_ws_connected exists (value: {health['fill_ws_connected']})")

    def test_status_has_fill_ws_has_credentials(self):
        """stats.health should include fill_ws_has_credentials."""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        
        health = data["stats"]["health"]
        assert "fill_ws_has_credentials" in health, "health should have 'fill_ws_has_credentials'"
        assert isinstance(health["fill_ws_has_credentials"], bool), "fill_ws_has_credentials should be boolean"
        print(f"PASS: stats.health.fill_ws_has_credentials exists (value: {health['fill_ws_has_credentials']})")

    def test_status_has_fill_ws_health_object(self):
        """stats.health should include fill_ws_health object."""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        
        health = data["stats"]["health"]
        assert "fill_ws_health" in health, "health should have 'fill_ws_health'"
        assert isinstance(health["fill_ws_health"], dict), "fill_ws_health should be a dict"
        
        # Verify nested structure
        fill_ws = health["fill_ws_health"]
        assert "connected" in fill_ws, "fill_ws_health should have 'connected'"
        assert "has_credentials" in fill_ws, "fill_ws_health should have 'has_credentials'"
        assert "trade_events" in fill_ws, "fill_ws_health should have 'trade_events'"
        
        print(f"PASS: stats.health.fill_ws_health object exists with required fields")

    def test_status_has_fill_update_method(self):
        """stats.health should include fill_update_method."""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        
        health = data["stats"]["health"]
        assert "fill_update_method" in health, "health should have 'fill_update_method'"
        assert health["fill_update_method"] in ["polling", "websocket+polling"], \
            f"fill_update_method should be 'polling' or 'websocket+polling', got: {health['fill_update_method']}"
        print(f"PASS: stats.health.fill_update_method exists (value: {health['fill_update_method']})")

    def test_status_fill_update_method_is_polling_without_ws(self):
        """fill_update_method should be 'polling' when WS not connected."""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        
        health = data["stats"]["health"]
        # Without credentials, WS won't connect so method should be polling
        if not health.get("fill_ws_connected", False):
            assert health["fill_update_method"] == "polling", \
                f"Expected 'polling' when WS not connected, got: {health['fill_update_method']}"
            print("PASS: fill_update_method is 'polling' when WS not connected")
        else:
            print("SKIP: WS is connected, cannot verify polling fallback")


class TestExecutionStatusEndpoint:
    """Test GET /api/execution/status includes Fill WS info."""

    def test_execution_status_returns_200(self):
        """GET /api/execution/status should return 200."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        assert response.status_code == 200
        print("PASS: GET /api/execution/status returns 200")

    def test_execution_status_has_live_adapter(self):
        """Response should include live_adapter object."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        assert "live_adapter" in data, "Response should have 'live_adapter'"
        assert isinstance(data["live_adapter"], dict), "live_adapter should be a dict"
        print("PASS: live_adapter object exists")

    def test_execution_status_live_adapter_has_fill_ws_health(self):
        """live_adapter should include fill_ws_health."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data["live_adapter"]
        assert "fill_ws_health" in live_adapter, "live_adapter should have 'fill_ws_health'"
        
        fill_ws = live_adapter["fill_ws_health"]
        assert "connected" in fill_ws, "fill_ws_health should have 'connected'"
        assert "has_credentials" in fill_ws, "fill_ws_health should have 'has_credentials'"
        print(f"PASS: live_adapter.fill_ws_health exists (connected: {fill_ws['connected']})")

    def test_execution_status_live_adapter_has_fill_update_method(self):
        """live_adapter should include fill_update_method."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data["live_adapter"]
        assert "fill_update_method" in live_adapter, "live_adapter should have 'fill_update_method'"
        assert live_adapter["fill_update_method"] in ["polling", "websocket+polling"], \
            f"fill_update_method should be valid, got: {live_adapter['fill_update_method']}"
        print(f"PASS: live_adapter.fill_update_method exists (value: {live_adapter['fill_update_method']})")

    def test_execution_status_live_adapter_has_poll_interval(self):
        """live_adapter should include poll_interval_seconds."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data["live_adapter"]
        assert "poll_interval_seconds" in live_adapter, "live_adapter should have 'poll_interval_seconds'"
        assert isinstance(live_adapter["poll_interval_seconds"], (int, float)), "poll_interval_seconds should be numeric"
        assert live_adapter["poll_interval_seconds"] > 0, "poll_interval_seconds should be positive"
        print(f"PASS: live_adapter.poll_interval_seconds exists (value: {live_adapter['poll_interval_seconds']})")


class TestExecutionModeEndpoint:
    """Test GET /api/execution/mode endpoint."""

    def test_execution_mode_returns_200(self):
        """GET /api/execution/mode should return 200."""
        response = requests.get(f"{BASE_URL}/api/execution/mode")
        assert response.status_code == 200
        print("PASS: GET /api/execution/mode returns 200")

    def test_execution_mode_has_credentials_info(self):
        """Response should include credentials info."""
        response = requests.get(f"{BASE_URL}/api/execution/mode")
        data = response.json()
        
        assert "credentials" in data, "Response should have 'credentials'"
        assert "mode" in data, "Response should have 'mode'"
        assert "live_enabled" in data, "Response should have 'live_enabled'"
        assert "safe_to_switch_live" in data, "Response should have 'safe_to_switch_live'"
        
        print(f"PASS: Execution mode response has all fields (mode: {data['mode']})")


class TestRegressionExistingEndpoints:
    """Verify existing endpoints still work (no regressions)."""

    def test_health_endpoint(self):
        """GET /api/health should return 200."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data, "health should have 'status'"
        print("PASS: GET /api/health works (no regression)")

    def test_config_endpoint(self):
        """GET /api/config should return 200."""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "trading_mode" in data, "config should have 'trading_mode'"
        assert "risk" in data, "config should have 'risk'"
        print("PASS: GET /api/config works (no regression)")

    def test_weather_health_endpoint(self):
        """GET /api/strategies/weather/health should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data, "weather health should have 'config'"
        assert "running" in data, "weather health should have 'running'"
        print("PASS: GET /api/strategies/weather/health works (no regression)")

    def test_arb_health_endpoint(self):
        """GET /api/strategies/arb/health should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data, "arb health should have 'config'"
        assert "running" in data, "arb health should have 'running'"
        print("PASS: GET /api/strategies/arb/health works (no regression)")

    def test_sniper_health_endpoint(self):
        """GET /api/strategies/sniper/health should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data, "sniper health should have 'config'"
        assert "running" in data, "sniper health should have 'running'"
        print("PASS: GET /api/strategies/sniper/health works (no regression)")

    def test_clob_ws_health_endpoint(self):
        """GET /api/health/clob-ws should return 200."""
        response = requests.get(f"{BASE_URL}/api/health/clob-ws")
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data, "clob-ws health should have 'connected'"
        print("PASS: GET /api/health/clob-ws works (no regression)")


class TestGracefulDegradation:
    """Test that system gracefully handles missing credentials."""

    def test_no_errors_in_health_endpoints(self):
        """All health endpoints should return without errors."""
        endpoints = [
            "/api/health",
            "/api/health/fill-ws",
            "/api/health/clob-ws",
            "/api/health/feeds",
        ]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 200, f"{endpoint} failed with {response.status_code}"
        
        print(f"PASS: All {len(endpoints)} health endpoints return 200")

    def test_fill_ws_graceful_degradation(self):
        """Fill WS should gracefully degrade when credentials missing."""
        response = requests.get(f"{BASE_URL}/api/health/fill-ws")
        data = response.json()
        
        # No connection errors
        assert data["last_error"] is None, f"Unexpected error: {data['last_error']}"
        # Not connected but no crash
        assert data["has_credentials"] == False, "Should report no credentials"
        assert data["connected"] == False, "Should not be connected"
        # Zero activity metrics (not errored values)
        assert data["connect_count"] == 0, "connect_count should be 0"
        
        print("PASS: Fill WS gracefully degraded - no errors, not connected, metrics at 0")

    def test_status_endpoint_not_affected_by_missing_creds(self):
        """Status endpoint should work regardless of credentials."""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status should return 200, got {response.status_code}"
        
        data = response.json()
        # Should have basic structure
        assert "status" in data, "Should have status"
        assert "mode" in data, "Should have mode"
        assert "stats" in data, "Should have stats"
        
        print("PASS: Status endpoint unaffected by missing credentials")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
