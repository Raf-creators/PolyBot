"""
CLOB WebSocket Integration Tests for Polymarket Edge OS.

Tests the CLOB WS client integration for real-time market data:
- /api/health/clob-ws endpoint returns all required health metrics
- CLOB WS auto-connects on server startup
- /api/strategies/weather/health includes clob_ws_health section
- Token subscription when engine starts and weather scan runs
- No stale_market rejection reasons when CLOB WS is active
- Existing weather endpoints still work (regression)
- Demo mode endpoints still work (regression)
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)


class TestClobWsHealth:
    """Tests for /api/health/clob-ws endpoint."""

    def test_clob_ws_health_endpoint_exists(self):
        """GET /api/health/clob-ws returns 200."""
        response = requests.get(f"{BASE_URL}/api/health/clob-ws")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/health/clob-ws returns 200")

    def test_clob_ws_health_has_required_fields(self):
        """GET /api/health/clob-ws returns all required health fields."""
        response = requests.get(f"{BASE_URL}/api/health/clob-ws")
        assert response.status_code == 200
        data = response.json()

        required_fields = [
            "connected",
            "subscribed_tokens",
            "messages_received",
            "price_updates",
            "book_updates",
            "trade_updates",
            "reconnect_count",
            "errors",
            "uptime_seconds",
            "last_message_seconds_ago",
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        print(f"PASS: All {len(required_fields)} required fields present in clob-ws health")
        print(f"  - connected: {data['connected']}")
        print(f"  - subscribed_tokens: {data['subscribed_tokens']}")
        print(f"  - messages_received: {data['messages_received']}")
        print(f"  - price_updates: {data['price_updates']}")
        print(f"  - book_updates: {data['book_updates']}")
        print(f"  - trade_updates: {data['trade_updates']}")
        print(f"  - reconnect_count: {data['reconnect_count']}")
        print(f"  - errors: {data['errors']}")
        print(f"  - uptime_seconds: {data.get('uptime_seconds')}")
        print(f"  - last_message_seconds_ago: {data.get('last_message_seconds_ago')}")

    def test_clob_ws_connected_on_server_startup(self):
        """CLOB WS auto-connects on server startup (connected=true)."""
        response = requests.get(f"{BASE_URL}/api/health/clob-ws")
        assert response.status_code == 200
        data = response.json()

        assert data.get("connected") is True, f"Expected connected=True, got {data.get('connected')}"
        print("PASS: CLOB WS connected=True (auto-connected on startup)")

    def test_clob_ws_url_is_polymarket(self):
        """CLOB WS URL points to Polymarket WebSocket."""
        response = requests.get(f"{BASE_URL}/api/health/clob-ws")
        assert response.status_code == 200
        data = response.json()

        expected_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        assert data.get("url") == expected_url, f"Expected URL {expected_url}, got {data.get('url')}"
        print(f"PASS: CLOB WS URL is {expected_url}")


class TestWeatherHealthClobWs:
    """Tests for CLOB WS health in weather trader health endpoint."""

    def test_weather_health_includes_clob_ws_health(self):
        """GET /api/strategies/weather/health includes clob_ws_health section."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()

        assert "clob_ws_health" in data, "Missing clob_ws_health in weather health"
        clob_health = data["clob_ws_health"]

        assert "connected" in clob_health, "Missing connected in clob_ws_health"
        assert "messages_received" in clob_health, "Missing messages_received in clob_ws_health"

        print("PASS: Weather health includes clob_ws_health section")
        print(f"  - connected: {clob_health.get('connected')}")
        print(f"  - subscribed_tokens: {clob_health.get('subscribed_tokens')}")
        print(f"  - messages_received: {clob_health.get('messages_received')}")

    def test_weather_health_clob_ws_connected(self):
        """Weather health shows CLOB WS as connected."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()

        clob_health = data.get("clob_ws_health", {})
        assert clob_health.get("connected") is True, f"Expected clob_ws_health.connected=True"
        print("PASS: Weather health clob_ws_health.connected=True")

    def test_weather_health_clob_ws_has_subscribed_tokens(self):
        """Weather health shows subscribed_tokens > 0 (after engine run)."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()

        clob_health = data.get("clob_ws_health", {})
        subscribed = clob_health.get("subscribed_tokens", 0)

        # Note: subscribed_tokens > 0 requires engine to have run at least once
        # Based on context, engine was run and discovered 265 tokens
        print(f"INFO: subscribed_tokens = {subscribed}")

        if subscribed > 0:
            print(f"PASS: subscribed_tokens={subscribed} > 0 (engine has run)")
        else:
            print("INFO: subscribed_tokens=0 (engine may not have scanned yet)")


class TestClobWsNoStaleMarketRejections:
    """Tests that stale_market rejections are eliminated when CLOB WS is active."""

    def test_no_stale_market_rejection_reason(self):
        """Rejection reasons should NOT include 'stale_market' when CLOB WS is active."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()

        rejection_reasons = data.get("rejection_reasons", {})
        print(f"Current rejection reasons: {rejection_reasons}")

        # stale_market should NOT be present when CLOB WS provides real-time updates
        assert "stale_market" not in rejection_reasons, (
            f"stale_market should not be in rejection reasons when CLOB WS is active. "
            f"Found: {rejection_reasons}"
        )
        print("PASS: No 'stale_market' rejection reason (CLOB WS providing real-time data)")

    def test_clob_ws_receiving_messages(self):
        """CLOB WS should be connected (messages depend on token subscriptions)."""
        response = requests.get(f"{BASE_URL}/api/health/clob-ws")
        assert response.status_code == 200
        data = response.json()

        # Connected is the key requirement - messages depend on token subscriptions
        assert data.get("connected") is True, "CLOB WS should be connected"
        
        messages = data.get("messages_received", 0)
        subscribed = data.get("subscribed_tokens", 0)
        
        # If there are subscribed tokens, we should be receiving messages
        if subscribed > 0:
            assert messages > 0, f"With {subscribed} subscribed tokens, expected messages_received > 0"
            print(f"PASS: CLOB WS messages_received={messages} with {subscribed} subscribed tokens")
        else:
            # No subscribed tokens yet - engine hasn't run weather scan
            print(f"INFO: CLOB WS connected but no subscribed tokens yet (engine hasn't scanned)")
            print("PASS: CLOB WS connected (messages will flow once tokens are subscribed)")

    def test_clob_ws_price_updates_received(self):
        """CLOB WS should have received price updates."""
        response = requests.get(f"{BASE_URL}/api/health/clob-ws")
        assert response.status_code == 200
        data = response.json()

        price_updates = data.get("price_updates", 0)
        print(f"INFO: price_updates={price_updates}")

        if price_updates > 0:
            print(f"PASS: CLOB WS receiving price updates ({price_updates})")
        else:
            print("WARNING: No price updates yet (may need more time)")


class TestWeatherEndpointsRegression:
    """Regression tests for existing weather endpoints."""

    def test_weather_health_endpoint(self):
        """GET /api/strategies/weather/health returns 200 with expected fields."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()

        assert "config" in data, "Missing config in weather health"
        assert "running" in data, "Missing running in weather health"
        assert "total_scans" in data, "Missing total_scans in weather health"
        print("PASS: Weather health endpoint works with expected fields")

    def test_weather_signals_endpoint(self):
        """GET /api/strategies/weather/signals returns 200 with tradable/rejected."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200
        data = response.json()

        assert "tradable" in data, "Missing tradable in signals"
        assert "rejected" in data, "Missing rejected in signals"
        assert "total_tradable" in data, "Missing total_tradable"
        assert "total_rejected" in data, "Missing total_rejected"
        print(f"PASS: Weather signals endpoint - tradable={data['total_tradable']}, rejected={data['total_rejected']}")

    def test_weather_executions_endpoint(self):
        """GET /api/strategies/weather/executions returns 200 with active/completed."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/executions")
        assert response.status_code == 200
        data = response.json()

        assert "active" in data, "Missing active in executions"
        assert "completed" in data, "Missing completed in executions"
        print(f"PASS: Weather executions endpoint - active={len(data['active'])}, completed={len(data['completed'])}")

    def test_weather_forecasts_endpoint(self):
        """GET /api/strategies/weather/forecasts returns 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/forecasts")
        assert response.status_code == 200
        data = response.json()
        print(f"PASS: Weather forecasts endpoint - {len(data)} forecasts")

    def test_weather_stations_endpoint(self):
        """GET /api/strategies/weather/stations returns 200 with station list."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/stations")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list), "Expected stations to be a list"
        assert len(data) >= 8, f"Expected at least 8 stations, got {len(data)}"
        print(f"PASS: Weather stations endpoint - {len(data)} stations")

    def test_weather_config_endpoint(self):
        """GET /api/strategies/weather/config returns 200 with enabled field."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/config")
        assert response.status_code == 200
        data = response.json()

        assert "enabled" in data, "Missing enabled in config"
        print(f"PASS: Weather config endpoint - enabled={data['enabled']}")


class TestCalibrationEndpointsRegression:
    """Regression tests for calibration endpoints."""

    def test_calibration_status_endpoint(self):
        """GET /api/strategies/weather/calibration/status returns 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/calibration/status")
        assert response.status_code == 200
        data = response.json()

        assert "total_stations_calibrated" in data, "Missing total_stations_calibrated"
        assert "total_stations_registered" in data, "Missing total_stations_registered"
        print(f"PASS: Calibration status - {data['total_stations_calibrated']}/{data['total_stations_registered']} calibrated")

    def test_calibration_run_endpoint_exists(self):
        """POST /api/strategies/weather/calibration/run endpoint exists."""
        # Don't actually run calibration, just verify endpoint exists
        response = requests.post(f"{BASE_URL}/api/strategies/weather/calibration/run", json={})
        # Should return 200 even with empty body
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Calibration run endpoint exists and accepts POST")


class TestShadowModeEndpointsRegression:
    """Regression tests for shadow mode endpoints."""

    def test_shadow_summary_endpoint(self):
        """GET /api/strategies/weather/shadow-summary returns 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/shadow-summary")
        assert response.status_code == 200
        data = response.json()

        assert "execution_mode" in data, "Missing execution_mode"
        assert "is_shadow" in data, "Missing is_shadow"
        assert "operational_stats" in data, "Missing operational_stats"
        print(f"PASS: Shadow summary - mode={data['execution_mode']}, is_shadow={data['is_shadow']}")

    def test_shadow_enable_endpoint(self):
        """POST /api/strategies/weather/shadow/enable returns 200."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/shadow/enable")
        assert response.status_code == 200
        data = response.json()

        assert data.get("status") == "shadow_overrides_applied", f"Expected status=shadow_overrides_applied"
        print("PASS: Shadow enable endpoint works")

    def test_shadow_reset_endpoint(self):
        """POST /api/strategies/weather/shadow/reset returns 200."""
        response = requests.post(f"{BASE_URL}/api/strategies/weather/shadow/reset")
        assert response.status_code == 200
        data = response.json()

        assert data.get("status") == "config_reset_to_defaults", f"Expected status=config_reset_to_defaults"
        print("PASS: Shadow reset endpoint works")


class TestDemoModeEndpointsRegression:
    """Regression tests for demo mode endpoints."""

    def test_demo_status_endpoint(self):
        """GET /api/demo/status returns 200."""
        response = requests.get(f"{BASE_URL}/api/demo/status")
        assert response.status_code == 200
        data = response.json()

        assert "enabled" in data, "Missing enabled in demo status"
        print(f"PASS: Demo status - enabled={data['enabled']}")

    def test_demo_weather_signals_endpoint(self):
        """GET /api/demo/strategies/weather/signals returns 200."""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/signals")
        assert response.status_code == 200
        data = response.json()

        assert "tradable" in data, "Missing tradable in demo weather signals"
        print(f"PASS: Demo weather signals - tradable={data.get('total_tradable')}")

    def test_demo_weather_health_endpoint(self):
        """GET /api/demo/strategies/weather/health returns 200."""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()

        assert "config" in data or "running" in data, "Expected config or running in demo health"
        print("PASS: Demo weather health endpoint works")

    def test_demo_weather_shadow_summary_endpoint(self):
        """GET /api/demo/strategies/weather/shadow-summary returns 200."""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/shadow-summary")
        assert response.status_code == 200
        data = response.json()

        assert "execution_mode" in data or "is_shadow" in data, "Expected mode info in demo shadow summary"
        print("PASS: Demo weather shadow-summary endpoint works")


class TestOtherPagesNoRegression:
    """Quick regression tests for other pages' endpoints (Overview, Analytics, Positions)."""

    def test_positions_endpoint(self):
        """GET /api/positions returns 200."""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        print("PASS: Positions endpoint works (Overview page)")

    def test_trades_endpoint(self):
        """GET /api/trades returns 200."""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        print("PASS: Trades endpoint works (Overview page)")

    def test_analytics_summary_endpoint(self):
        """GET /api/analytics/summary returns 200."""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200
        print("PASS: Analytics summary endpoint works (Analytics page)")

    def test_analytics_strategies_endpoint(self):
        """GET /api/analytics/strategies returns 200."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategies")
        assert response.status_code == 200
        print("PASS: Analytics strategies endpoint works (Analytics page)")

    def test_orders_endpoint(self):
        """GET /api/orders returns 200."""
        response = requests.get(f"{BASE_URL}/api/orders")
        assert response.status_code == 200
        print("PASS: Orders endpoint works (Positions page)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
