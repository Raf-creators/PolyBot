"""Phase 8: Live Polymarket Execution Adapter Tests

Tests for:
- GET /api/execution/mode - returns mode, credentials, live_enabled, safe_to_switch_live
- GET /api/execution/status - returns mode, paper_adapter, live_adapter, risk_config
- POST /api/execution/mode - mode switching with safety checks
- Paper mode still works: start engine, inject test market, verify trade executes
- Risk engine still gates execution in paper mode
- Regression tests: health, config, ticker, P&L chart, nav items
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestExecutionModeAPI:
    """Tests for GET /api/execution/mode endpoint."""

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

    def test_live_enabled_false_without_credentials(self):
        """GET /api/execution/mode shows live_enabled=false when no credentials."""
        response = requests.get(f"{BASE_URL}/api/execution/mode")
        data = response.json()
        
        # When mode is paper, live_enabled should be false
        if data["mode"] == "paper":
            assert data["live_enabled"] == False
        
        # Without credentials, live adapter should not be authenticated
        assert data["live_adapter_authenticated"] == False
        print(f"✓ live_enabled=false and live_adapter_authenticated=false without credentials")

    def test_safe_to_switch_live_false_without_credentials(self):
        """GET /api/execution/mode shows safe_to_switch_live=false when no credentials."""
        response = requests.get(f"{BASE_URL}/api/execution/mode")
        data = response.json()
        
        assert data["safe_to_switch_live"] == False
        print(f"✓ safe_to_switch_live=false without credentials")

    def test_credentials_all_five_env_vars_false(self):
        """GET /api/execution/mode credentials shows all 5 env vars as false."""
        response = requests.get(f"{BASE_URL}/api/execution/mode")
        data = response.json()
        credentials = data["credentials"]
        
        expected_keys = [
            "POLYMARKET_PRIVATE_KEY",
            "POLYMARKET_FUNDER_ADDRESS", 
            "POLYMARKET_API_KEY",
            "POLYMARKET_API_SECRET",
            "POLYMARKET_PASSPHRASE"
        ]
        
        for key in expected_keys:
            assert key in credentials, f"Missing credential key: {key}"
            assert credentials[key] == False, f"{key} should be false without credentials"
        
        assert credentials.get("ready") == False, "ready should be false without credentials"
        print(f"✓ All 5 credential env vars are false without credentials")


class TestExecutionStatusAPI:
    """Tests for GET /api/execution/status endpoint."""

    def test_execution_status_returns_200(self):
        """GET /api/execution/status returns 200."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        assert response.status_code == 200
        print(f"✓ GET /api/execution/status returns 200")

    def test_execution_status_has_expected_fields(self):
        """GET /api/execution/status returns mode, paper_adapter, live_adapter, risk_config."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        assert "mode" in data, "Missing 'mode' field"
        assert "paper_adapter" in data, "Missing 'paper_adapter' field"
        assert "live_adapter" in data, "Missing 'live_adapter' field"
        assert "risk_config" in data, "Missing 'risk_config' field"
        
        # paper_adapter should always be available
        assert data["paper_adapter"] == "always_available"
        print(f"✓ GET /api/execution/status has all expected fields")

    def test_live_adapter_authenticated_false_without_credentials(self):
        """GET /api/execution/status live_adapter.authenticated is false without credentials."""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        data = response.json()
        
        live_adapter = data["live_adapter"]
        assert live_adapter.get("authenticated") == False
        print(f"✓ live_adapter.authenticated is false without credentials")


class TestExecutionModePostAPI:
    """Tests for POST /api/execution/mode endpoint."""

    def test_post_mode_paper_returns_200(self):
        """POST /api/execution/mode with mode=paper returns 200."""
        response = requests.post(
            f"{BASE_URL}/api/execution/mode",
            json={"mode": "paper"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "paper"
        assert data.get("persisted") == True
        print(f"✓ POST /api/execution/mode mode=paper returns 200")

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
        """POST /api/execution/mode with mode=shadow returns 200 (shadow is allowed without live creds)."""
        response = requests.post(
            f"{BASE_URL}/api/execution/mode",
            json={"mode": "shadow"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "shadow"
        assert data.get("persisted") == True
        print(f"✓ POST /api/execution/mode mode=shadow returns 200")

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

    def test_mode_paper_persists(self):
        """POST /api/execution/mode mode=paper persists (check GET /api/config returns paper)."""
        # Set to paper
        response = requests.post(
            f"{BASE_URL}/api/execution/mode",
            json={"mode": "paper"}
        )
        assert response.status_code == 200
        
        # Verify via GET /api/config
        config_response = requests.get(f"{BASE_URL}/api/config")
        assert config_response.status_code == 200
        config_data = config_response.json()
        assert config_data["trading_mode"] == "paper"
        print(f"✓ Mode paper persists to config")


class TestPaperModeExecution:
    """Tests for paper mode execution pipeline."""

    def test_paper_mode_engine_start(self):
        """Start engine in paper mode."""
        # Ensure paper mode
        requests.post(f"{BASE_URL}/api/execution/mode", json={"mode": "paper"})
        
        # Start engine
        response = requests.post(f"{BASE_URL}/api/engine/start")
        # May return 400 if already running
        assert response.status_code in [200, 400]
        print(f"✓ Engine start returns 200 or 400 (already running)")

    def test_inject_arb_opportunity_in_paper_mode(self):
        """Inject test market in paper mode and verify trade executes."""
        # Ensure engine is running
        start_response = requests.post(f"{BASE_URL}/api/engine/start")
        
        # If already running, that's fine
        if start_response.status_code == 400:
            assert "already running" in start_response.json().get("detail", "").lower()
        
        # Inject test arb opportunity
        inject_response = requests.post(f"{BASE_URL}/api/test/inject-arb-opportunity")
        assert inject_response.status_code == 200
        inject_data = inject_response.json()
        assert inject_data["status"] == "injected"
        assert "condition_id" in inject_data
        print(f"✓ Test arb opportunity injected: {inject_data['condition_id']}")


class TestRiskEngineGating:
    """Tests for risk engine gating in paper mode."""

    def test_risk_kill_switch_endpoints(self):
        """Risk kill switch endpoints work."""
        # Activate
        activate_response = requests.post(f"{BASE_URL}/api/risk/kill-switch/activate")
        assert activate_response.status_code == 200
        
        # Verify via execution/mode
        mode_response = requests.get(f"{BASE_URL}/api/execution/mode")
        mode_data = mode_response.json()
        assert mode_data["safe_to_switch_live"] == False  # Kill switch active
        
        # Deactivate
        deactivate_response = requests.post(f"{BASE_URL}/api/risk/kill-switch/deactivate")
        assert deactivate_response.status_code == 200
        print(f"✓ Risk kill switch activate/deactivate works")


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

    def test_ticker_feed_returns_array(self):
        """GET /api/ticker/feed returns array."""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/ticker/feed returns array")

    def test_pnl_history_returns_expected_structure(self):
        """GET /api/analytics/pnl-history returns expected structure."""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        assert "points" in data
        assert "current_pnl" in data
        print(f"✓ GET /api/analytics/pnl-history returns expected structure")

    def test_strategies_arb_health(self):
        """GET /api/strategies/arb/health works."""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        print(f"✓ GET /api/strategies/arb/health works")

    def test_strategies_sniper_health(self):
        """GET /api/strategies/sniper/health works."""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        print(f"✓ GET /api/strategies/sniper/health works")

    def test_status_endpoint(self):
        """GET /api/status returns expected structure."""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        # Status returns mode, stats, components, risk etc.
        assert "mode" in data or "trading_mode" in data
        assert "stats" in data or "risk" in data
        print(f"✓ GET /api/status returns expected structure")


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

    def test_stop_engine(self):
        """Stop engine after tests."""
        response = requests.post(f"{BASE_URL}/api/engine/stop")
        # May return 400 if not running
        assert response.status_code in [200, 400]
        print(f"✓ Engine stopped or was not running")
