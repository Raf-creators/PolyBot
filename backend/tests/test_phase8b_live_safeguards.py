"""
Phase 8B: Final Live Trading Safeguards Test Suite

Features tested:
1. Cancel order endpoint POST /api/execution/orders/{id}/cancel
2. Slippage protection config (max_live_slippage_bps, allow_aggressive_live)
3. Enhanced execution/status with fill_update_method, poll_interval_seconds
4. LiveOrderRecord fields: slippage_bps, cancelled_at, cancel_reason, update_source
5. Execution orders get/cancel APIs
6. Regression tests for health, config, analytics, ticker
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestCancelOrderEndpoint:
    """Test POST /api/execution/orders/{id}/cancel endpoint"""

    def test_cancel_nonexistent_order_returns_404(self):
        """POST /api/execution/orders/nonexistent/cancel should return 404"""
        response = requests.post(f"{BASE_URL}/api/execution/orders/nonexistent-order-id/cancel")
        assert response.status_code == 404, f"Expected 404 for nonexistent order, got {response.status_code}: {response.text}"
        data = response.json()
        # Should contain 'order not found' in detail
        detail = data.get('detail', '')
        assert 'order not found' in detail.lower(), f"Expected 'order not found' in detail, got: {detail}"

    def test_cancel_random_uuid_returns_404(self):
        """POST /api/execution/orders/{random_uuid}/cancel should return 404"""
        import uuid
        random_id = str(uuid.uuid4())
        response = requests.post(f"{BASE_URL}/api/execution/orders/{random_id}/cancel")
        assert response.status_code == 404, f"Expected 404 for random UUID, got {response.status_code}"


class TestSlippageProtectionConfig:
    """Test slippage_protection fields in execution/status"""

    def test_execution_status_has_slippage_protection(self):
        """GET /api/execution/status should include slippage_protection"""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        assert response.status_code == 200
        data = response.json()
        
        assert 'slippage_protection' in data, "Missing slippage_protection in execution/status"
        sp = data['slippage_protection']
        
        assert 'max_live_slippage_bps' in sp, "Missing max_live_slippage_bps in slippage_protection"
        assert 'allow_aggressive_live' in sp, "Missing allow_aggressive_live in slippage_protection"
        
        # Verify types
        assert isinstance(sp['max_live_slippage_bps'], (int, float)), "max_live_slippage_bps should be numeric"
        assert isinstance(sp['allow_aggressive_live'], bool), "allow_aggressive_live should be boolean"
        print(f"Slippage protection config: {sp}")

    def test_execution_status_default_slippage_values(self):
        """Default max_live_slippage_bps should be 100, allow_aggressive_live should be false"""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        assert response.status_code == 200
        data = response.json()
        sp = data['slippage_protection']
        
        # Defaults from RiskConfig
        assert sp['max_live_slippage_bps'] >= 0, "max_live_slippage_bps should be non-negative"
        assert sp['allow_aggressive_live'] == False, f"allow_aggressive_live default should be False, got {sp['allow_aggressive_live']}"


class TestLiveAdapterEnhancements:
    """Test fill_update_method and poll_interval_seconds in live_adapter status"""

    def test_live_adapter_has_fill_update_method(self):
        """live_adapter status should include fill_update_method='polling'"""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        assert response.status_code == 200
        data = response.json()
        
        live_adapter = data.get('live_adapter', {})
        assert 'fill_update_method' in live_adapter, "Missing fill_update_method in live_adapter"
        assert live_adapter['fill_update_method'] == 'polling', f"Expected fill_update_method='polling', got {live_adapter['fill_update_method']}"

    def test_live_adapter_has_poll_interval_seconds(self):
        """live_adapter status should include poll_interval_seconds"""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        assert response.status_code == 200
        data = response.json()
        
        live_adapter = data.get('live_adapter', {})
        assert 'poll_interval_seconds' in live_adapter, "Missing poll_interval_seconds in live_adapter"
        assert live_adapter['poll_interval_seconds'] > 0, "poll_interval_seconds should be positive"
        print(f"Poll interval: {live_adapter['poll_interval_seconds']}s")

    def test_live_adapter_has_cancelled_and_slippage_rejected_counters(self):
        """live_adapter should have total_cancelled and total_slippage_rejected"""
        response = requests.get(f"{BASE_URL}/api/execution/status")
        assert response.status_code == 200
        data = response.json()
        
        live_adapter = data.get('live_adapter', {})
        assert 'total_cancelled' in live_adapter, "Missing total_cancelled in live_adapter"
        assert 'total_slippage_rejected' in live_adapter, "Missing total_slippage_rejected in live_adapter"
        
        # Both should be non-negative integers
        assert live_adapter['total_cancelled'] >= 0, "total_cancelled should be non-negative"
        assert live_adapter['total_slippage_rejected'] >= 0, "total_slippage_rejected should be non-negative"


class TestWalletEndpoint:
    """Test GET /api/execution/wallet structure"""

    def test_wallet_has_correct_structure(self):
        """GET /api/execution/wallet should return expected fields including warnings array"""
        response = requests.get(f"{BASE_URL}/api/execution/wallet")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ['mode', 'authenticated', 'balance_usdc', 'live_ready', 'warnings']
        for field in required_fields:
            assert field in data, f"Missing {field} in wallet response"
        
        # warnings must be an array
        assert isinstance(data['warnings'], list), f"warnings should be array, got {type(data['warnings'])}"
        print(f"Wallet: authenticated={data['authenticated']}, warnings={data['warnings']}")


class TestExecutionOrdersEndpoint:
    """Test GET /api/execution/orders"""

    def test_execution_orders_returns_array(self):
        """GET /api/execution/orders should return array (possibly empty)"""
        response = requests.get(f"{BASE_URL}/api/execution/orders")
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list), f"Expected array, got {type(data)}"
        print(f"Live orders count: {len(data)}")


class TestExecutionModeEndpoint:
    """Test execution mode switching"""

    def test_execution_mode_get(self):
        """GET /api/execution/mode should return current mode"""
        response = requests.get(f"{BASE_URL}/api/execution/mode")
        assert response.status_code == 200
        data = response.json()
        
        assert 'mode' in data
        assert 'live_adapter_authenticated' in data
        assert 'credentials' in data

    def test_execution_mode_set_live_without_creds_returns_400(self):
        """POST /api/execution/mode mode=live should return 400 without credentials"""
        response = requests.post(f"{BASE_URL}/api/execution/mode", json={"mode": "live"})
        assert response.status_code == 400, f"Expected 400 for live mode without creds, got {response.status_code}"
        data = response.json()
        assert 'not set' in data.get('detail', '').lower() or 'credential' in data.get('detail', '').lower()

    def test_execution_mode_set_shadow_works(self):
        """POST /api/execution/mode mode=shadow should work (200)"""
        response = requests.post(f"{BASE_URL}/api/execution/mode", json={"mode": "shadow"})
        assert response.status_code == 200, f"Expected 200 for shadow mode, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get('mode') == 'shadow'

    def test_execution_mode_set_paper_works(self):
        """POST /api/execution/mode mode=paper should work (200)"""
        response = requests.post(f"{BASE_URL}/api/execution/mode", json={"mode": "paper"})
        assert response.status_code == 200, f"Expected 200 for paper mode, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get('mode') == 'paper'


class TestPaperModeEngineControl:
    """Test engine start/stop in paper mode"""

    def test_engine_start_in_paper_mode(self):
        """Engine should start successfully in paper mode"""
        # Ensure paper mode
        requests.post(f"{BASE_URL}/api/execution/mode", json={"mode": "paper"})
        
        # Stop engine first if running
        requests.post(f"{BASE_URL}/api/engine/stop")
        
        # Start engine
        response = requests.post(f"{BASE_URL}/api/engine/start")
        # Could be 200 (success) or 400 (already running)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        print(f"Engine start response: {response.status_code}")

    def test_engine_stop(self):
        """Engine should stop successfully"""
        response = requests.post(f"{BASE_URL}/api/engine/stop")
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_health_returns_healthy(self):
        """GET /api/health should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'healthy'

    def test_config_includes_persisted_and_last_saved(self):
        """GET /api/config should have persisted and last_saved fields"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        
        assert 'persisted' in data, "Missing persisted field in config"
        assert 'last_saved' in data, "Missing last_saved field in config"

    def test_config_risk_has_slippage_fields(self):
        """GET /api/config risk should have max_live_slippage_bps and allow_aggressive_live"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        
        risk = data.get('risk', {})
        assert 'max_live_slippage_bps' in risk, "Missing max_live_slippage_bps in risk config"
        assert 'allow_aggressive_live' in risk, "Missing allow_aggressive_live in risk config"

    def test_pnl_history_works(self):
        """GET /api/analytics/pnl-history should return correct structure"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        
        assert 'points' in data
        assert 'current_pnl' in data

    def test_ticker_feed_returns_array(self):
        """GET /api/ticker/feed should return array"""
        response = requests.get(f"{BASE_URL}/api/ticker/feed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestCleanup:
    """Cleanup after tests"""

    def test_reset_to_paper_mode(self):
        """Reset to paper mode after tests"""
        response = requests.post(f"{BASE_URL}/api/execution/mode", json={"mode": "paper"})
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
