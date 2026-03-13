"""Phase 8A: Live Execution Hardening Tests

Tests for new/enhanced endpoints:
- GET /api/execution/wallet - returns mode, authenticated, balance_usdc, live_ready, warnings
- GET /api/execution/orders - returns live order records (empty array initially)
- GET /api/execution/status - live_adapter now has open_orders, partial_orders, last_api_call, last_status_refresh, recent_errors
- POST /api/execution/mode - mode switching (live blocked without creds, shadow/paper work)

Regression tests preserved from Phase 8.
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestWalletEndpoint:
    """Tests for GET /api/execution/wallet endpoint."""

    def test_wallet_returns_200(self):
        """GET /api/execution/wallet returns 200."""
        response = requests.get(f"{BASE_URL}/api/execution/wallet")
        assert response.status_code == 200
        print(f"✓ GET /api/execution/wallet returns 200")

    def test_wallet_has_expected_fields(self):
        """GET /api/execution/wallet returns mode, authenticated, balance_usdc, live_ready, warnings."""
        response = requests.get(f"{BASE_URL}/api/execution/wallet")
        data = response.json()
        
        assert "mode" in data, "Missing 'mode' field"
        assert "authenticated" in data, "Missing 'authenticated' field"
        assert "balance_usdc" in data, "Missing 'balance_usdc' field"
        assert "live_ready" in data, "Missing 'live_ready' field"
        assert "warnings" in data, "Missing 'warnings' field"
        print(f"✓ GET /api/execution/wallet has all expected fields: {list(data.keys())}")

    def test_wallet_authenticated_false_without_credentials(self):
        """GET /api/execution/wallet shows authenticated=false without credentials."""
        response = requests.get(f"{BASE_URL}/api/execution/wallet")
        data = response.json()
        
        assert data["authenticated"] == False, "authenticated should be false without credentials"
        print(f"✓ authenticated=false without credentials")

    def test_wallet_balance_null_without_authentication(self):
        """GET /api/execution/wallet shows balance_usdc=null without authentication."""
        response = requests.get(f"{BASE_URL}/api/execution/wallet")
        data = response.json()
        
        assert data["balance_usdc"] is None, "balance_usdc should be null without authentication"
        print(f"✓ balance_usdc=null without authentication")

    def test_wallet_warnings_is_array(self):
        """GET /api/execution/wallet warnings is an array (empty in paper mode without issues)."""
        response = requests.get(f"{BASE_URL}/api/execution/wallet")
        data = response.json()
        
        assert isinstance(data["warnings"], list), "warnings should be a list"
        # In paper mode without kill switch, warnings should be empty
        if data["mode"] == "paper":
            assert len(data["warnings"]) == 0, "In paper mode with no issues, warnings should be empty"
        print(f"✓ warnings is array with {len(data['warnings'])} items")

    def test_wallet_live_ready_false_without_credentials(self):
        """GET /api/execution/wallet shows live_ready=false without credentials."""
        response = requests.get(f"{BASE_URL}/api/execution/wallet")
        data = response.json()
        
        assert data["live_ready"] == False, "live_ready should be false without credentials"
        print(f"✓ live_ready=false without credentials")


class TestLiveOrdersEndpoint:
    """Tests for GET /api/execution/orders endpoint."""

    def test_orders_returns_200(self):
        """GET /api/execution/orders returns 200."""
        response = requests.get(f"{BASE_URL}/api/execution/orders")
        assert response.status_code == 200
        print(f"✓ GET /api/execution/orders returns 200")

    def test_orders_returns_array(self):
        """GET /api/execution/orders returns array (empty initially)."""
        response = requests.get(f"{BASE_URL}/api/execution/orders")
        data = response.json()
        
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ GET /api/execution/orders returns array with {len(data)} items")


class TestExecutionStatusEnhanced:
    """Tests for enhanced GET /api/execution/status endpoint (Phase 8A fields)."""

    def test_execution_status_returns_200(self):
        """GET /api/execution/status returns 200."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        assert response.status_code == 200
        print(f"✓ GET /api/execution/status returns 200")

    def test_live_adapter_has_open_orders_field(self):
        """GET /api/execution/status live_adapter has open_orders field."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data.get("live_adapter", {})
        assert "open_orders" in live_adapter, "Missing 'open_orders' field in live_adapter"
        assert live_adapter["open_orders"] == 0, "open_orders should be 0 initially"
        print(f"✓ live_adapter.open_orders = {live_adapter['open_orders']}")

    def test_live_adapter_has_partial_orders_field(self):
        """GET /api/execution/status live_adapter has partial_orders field."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data.get("live_adapter", {})
        assert "partial_orders" in live_adapter, "Missing 'partial_orders' field in live_adapter"
        assert live_adapter["partial_orders"] == 0, "partial_orders should be 0 initially"
        print(f"✓ live_adapter.partial_orders = {live_adapter['partial_orders']}")

    def test_live_adapter_has_last_api_call_field(self):
        """GET /api/execution/status live_adapter has last_api_call field."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data.get("live_adapter", {})
        assert "last_api_call" in live_adapter, "Missing 'last_api_call' field in live_adapter"
        # Without credentials, last_api_call should be None
        print(f"✓ live_adapter.last_api_call = {live_adapter['last_api_call']}")

    def test_live_adapter_has_last_status_refresh_field(self):
        """GET /api/execution/status live_adapter has last_status_refresh field."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data.get("live_adapter", {})
        assert "last_status_refresh" in live_adapter, "Missing 'last_status_refresh' field in live_adapter"
        print(f"✓ live_adapter.last_status_refresh = {live_adapter['last_status_refresh']}")

    def test_live_adapter_has_recent_errors_field(self):
        """GET /api/execution/status live_adapter has recent_errors field."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data.get("live_adapter", {})
        assert "recent_errors" in live_adapter, "Missing 'recent_errors' field in live_adapter"
        assert isinstance(live_adapter["recent_errors"], list), "recent_errors should be a list"
        print(f"✓ live_adapter.recent_errors = {live_adapter['recent_errors']}")

    def test_live_adapter_has_total_partial_fills_field(self):
        """GET /api/execution/status live_adapter has total_partial_fills field (Phase 8A)."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data.get("live_adapter", {})
        assert "total_partial_fills" in live_adapter, "Missing 'total_partial_fills' field in live_adapter"
        print(f"✓ live_adapter.total_partial_fills = {live_adapter['total_partial_fills']}")


class TestExecutionModeAPI:
    """Tests for GET/POST /api/execution/mode endpoint."""

    def test_execution_mode_returns_200(self):
        """GET /api/execution/mode returns 200."""
        response = requests.get(f"{BASE_URL}/api/execution/mode")
        assert response.status_code == 200
        print(f"✓ GET /api/execution/mode returns 200")

    def test_execution_mode_has_expected_fields(self):
        """GET /api/execution/mode returns mode, live_adapter_authenticated, credentials, live_enabled, safe_to_switch_live."""
        response = requests.get(f"{BASE_URL}/api/execution/mode")
        data = response.json()
        
        assert "mode" in data, "Missing 'mode' field"
        assert "live_adapter_authenticated" in data, "Missing 'live_adapter_authenticated' field"
        assert "credentials" in data, "Missing 'credentials' field"
        assert "live_enabled" in data, "Missing 'live_enabled' field"
        assert "safe_to_switch_live" in data, "Missing 'safe_to_switch_live' field"
        print(f"✓ GET /api/execution/mode has all expected fields")

    def test_post_mode_live_returns_400_without_credentials(self):
        """POST /api/execution/mode with mode=live returns 400 error when no credentials."""
        response = requests.post(
            f"{BASE_URL}/api/execution/mode",
            json={"mode": "live"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "POLYMARKET_PRIVATE_KEY" in data["detail"] or "Cannot switch to live" in data["detail"]
        print(f"✓ POST /api/execution/mode mode=live returns 400 without credentials")

    def test_post_mode_shadow_returns_200(self):
        """POST /api/execution/mode with mode=shadow returns 200."""
        response = requests.post(
            f"{BASE_URL}/api/execution/mode",
            json={"mode": "shadow"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "shadow"
        print(f"✓ POST /api/execution/mode mode=shadow returns 200")

    def test_post_mode_paper_returns_200(self):
        """POST /api/execution/mode with mode=paper returns 200."""
        response = requests.post(
            f"{BASE_URL}/api/execution/mode",
            json={"mode": "paper"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "paper"
        print(f"✓ POST /api/execution/mode mode=paper returns 200")

    def test_post_mode_invalid_returns_400(self):
        """POST /api/execution/mode with mode=invalid returns 400."""
        response = requests.post(
            f"{BASE_URL}/api/execution/mode",
            json={"mode": "invalid"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Invalid mode" in data["detail"]
        print(f"✓ POST /api/execution/mode mode=invalid returns 400")


class TestPaperModeStillWorks:
    """Tests for paper mode execution pipeline (regression)."""

    def test_engine_start_in_paper_mode(self):
        """Start engine in paper mode."""
        # Ensure paper mode
        requests.post(f"{BASE_URL}/api/execution/mode", json={"mode": "paper"})
        
        # Start engine
        response = requests.post(f"{BASE_URL}/api/engine/start")
        assert response.status_code in [200, 400]  # 400 if already running
        print(f"✓ Engine start in paper mode: {response.status_code}")

    def test_health_endpoint_running(self):
        """GET /api/health shows engine running."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ Health endpoint healthy, engine={data['engine']}")

    def test_engine_stop(self):
        """Stop engine."""
        response = requests.post(f"{BASE_URL}/api/engine/stop")
        assert response.status_code in [200, 400]  # 400 if not running
        print(f"✓ Engine stop: {response.status_code}")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints."""

    def test_health_returns_healthy(self):
        """GET /api/health returns healthy."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ GET /api/health returns healthy")

    def test_config_includes_persisted_and_last_saved(self):
        """GET /api/config includes persisted and last_saved."""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "persisted" in data
        assert "last_saved" in data
        print(f"✓ GET /api/config includes persisted and last_saved")

    def test_pnl_history_returns_expected_structure(self):
        """GET /api/analytics/pnl-history returns expected structure."""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        assert "points" in data
        assert "current_pnl" in data
        assert "peak_pnl" in data
        assert "trough_pnl" in data
        assert "max_drawdown" in data
        assert "total_trades" in data
        print(f"✓ GET /api/analytics/pnl-history returns correct structure")

    def test_ticker_feed_returns_array(self):
        """GET /api/ticker/feed returns array."""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/ticker/feed returns array")

    def test_alerts_test_endpoint(self):
        """GET /api/alerts/test works (even if telegram not configured)."""
        response = requests.get(f"{BASE_URL}/api/alerts/test")
        assert response.status_code == 200
        data = response.json()
        # Should return 'skipped' if telegram not configured
        assert "status" in data
        print(f"✓ GET /api/alerts/test works, status={data['status']}")


class TestCleanup:
    """Cleanup after tests."""

    def test_reset_to_paper_mode(self):
        """Reset to paper mode after tests."""
        response = requests.post(
            f"{BASE_URL}/api/execution/mode",
            json={"mode": "paper"}
        )
        assert response.status_code == 200
        print(f"✓ Reset to paper mode")

    def test_stop_engine_cleanup(self):
        """Stop engine after tests."""
        response = requests.post(f"{BASE_URL}/api/engine/stop")
        assert response.status_code in [200, 400]
        print(f"✓ Engine stopped or was not running")
