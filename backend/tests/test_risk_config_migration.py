"""
Test suite for Risk Config Migration and Crypto Sniper Signal Generation
Tests the max_concurrent_positions upgrade from 10 to 25+ and sniper activity
"""
import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestRiskConfigMigration:
    """Tests for risk config max_concurrent_positions >= 25"""
    
    def test_status_returns_200(self):
        """GET /api/status should return 200"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        print(f"PASS: GET /api/status returned 200")
    
    def test_max_concurrent_positions_not_old_default(self):
        """max_concurrent_positions should be >= 25 (not the old default of 10)"""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        max_positions = data.get("risk", {}).get("max_concurrent_positions", 0)
        assert max_positions >= 25, f"max_concurrent_positions={max_positions} is less than 25 (old default was 10)"
        print(f"PASS: max_concurrent_positions={max_positions} (>= 25, not old default of 10)")


class TestSniperHealth:
    """Tests for crypto sniper signal generation"""
    
    def test_sniper_health_returns_200(self):
        """GET /api/strategies/sniper/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        print(f"PASS: GET /api/strategies/sniper/health returned 200")
    
    def test_sniper_is_running(self):
        """Sniper strategy should be running"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        running = data.get("running", False)
        assert running, "Sniper is not running"
        print(f"PASS: Sniper is running")
    
    def test_sniper_has_signal_history_in_trades(self):
        """Historical trades should contain crypto_sniper entries (proves sniper has generated signals)"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        trades = response.json()
        sniper_trades = [t for t in trades if t.get("strategy_id") == "crypto_sniper"]
        assert len(sniper_trades) > 0, "No crypto_sniper trades in history - sniper has never generated signals"
        print(f"PASS: Found {len(sniper_trades)} crypto_sniper trades in history")


class TestCryptoPositions:
    """Tests for crypto positions (sniper trades)"""
    
    def test_positions_endpoint_returns_200(self):
        """GET /api/positions should return 200"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        print(f"PASS: GET /api/positions returned 200")
    
    def test_trades_contain_sniper_entries(self):
        """Trades should contain crypto_sniper entries"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        trades = response.json()
        sniper_trades = [t for t in trades if t.get("strategy_id") == "crypto_sniper"]
        assert len(sniper_trades) > 0, "No crypto_sniper trades found"
        print(f"PASS: Found {len(sniper_trades)} crypto_sniper trades")


class TestLiveResolution:
    """Tests for live market resolution (pnl-history freshness)"""
    
    def test_pnl_history_returns_200(self):
        """GET /api/analytics/pnl-history should return 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        print(f"PASS: GET /api/analytics/pnl-history returned 200")
    
    def test_close_trades_above_threshold(self):
        """close_trades > 370"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        data = response.json()
        close_trades = data.get("close_trades", 0)
        assert close_trades > 370, f"close_trades={close_trades} should be > 370"
        print(f"PASS: close_trades={close_trades} (> 370)")
    
    def test_latest_close_within_10_minutes(self):
        """latest_close_at should be within the last 10 minutes"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        data = response.json()
        latest_close_at = data.get("latest_close_at")
        assert latest_close_at is not None, "latest_close_at is None"
        
        # Parse ISO timestamp
        latest_close_dt = datetime.fromisoformat(latest_close_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - latest_close_dt
        
        # Should be within 10 minutes (600 seconds)
        assert delta.total_seconds() <= 600, f"latest_close_at is {delta.total_seconds():.0f}s ago (> 600s)"
        print(f"PASS: latest_close_at is {delta.total_seconds():.0f}s ago (within 10 minutes)")


class TestResolverActivity:
    """Tests for market resolver activity"""
    
    def test_market_resolver_returns_200(self):
        """GET /api/health/market-resolver should return 200"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver")
        assert response.status_code == 200
        print(f"PASS: GET /api/health/market-resolver returned 200")
    
    def test_resolver_is_running(self):
        """Resolver should be running"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver")
        data = response.json()
        running = data.get("running", False)
        assert running, "Resolver is not running"
        print(f"PASS: Resolver is running")
    
    def test_resolver_has_resolved_positions_or_has_trades(self):
        """positions_resolved > 0 OR historical close_trades > 370 (proves resolver has been active)"""
        resolver_resp = requests.get(f"{BASE_URL}/api/health/market-resolver")
        resolver_data = resolver_resp.json()
        positions_resolved = resolver_data.get("positions_resolved", 0)
        
        # Also check pnl-history for historical evidence of resolver activity
        pnl_resp = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        pnl_data = pnl_resp.json()
        close_trades = pnl_data.get("close_trades", 0)
        
        # Resolver activity is proven by either real-time resolutions or historical close trades
        has_activity = positions_resolved > 0 or close_trades > 370
        assert has_activity, f"No resolver activity: positions_resolved={positions_resolved}, close_trades={close_trades}"
        print(f"PASS: Resolver activity confirmed - positions_resolved={positions_resolved}, close_trades={close_trades}")


class TestDataConsistency:
    """Tests for data consistency across endpoints"""
    
    def test_close_count_matches_across_endpoints(self):
        """close_count should match across /api/status, /api/analytics/global, /api/analytics/pnl-history"""
        status_resp = requests.get(f"{BASE_URL}/api/status")
        global_resp = requests.get(f"{BASE_URL}/api/analytics/global")
        pnl_resp = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        
        assert status_resp.status_code == 200
        assert global_resp.status_code == 200
        assert pnl_resp.status_code == 200
        
        status_close = status_resp.json().get("stats", {}).get("close_count", -1)
        global_close = global_resp.json().get("strategy_performance", {}).get("close_trades", -2)
        pnl_close = pnl_resp.json().get("close_trades", -3)
        
        assert status_close == global_close, f"status.close_count={status_close} != global.close_trades={global_close}"
        assert status_close == pnl_close, f"status.close_count={status_close} != pnl.close_trades={pnl_close}"
        print(f"PASS: Data consistency - close_count matches across all endpoints: {status_close}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
