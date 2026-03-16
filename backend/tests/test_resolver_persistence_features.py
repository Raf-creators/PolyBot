"""
Test suite for Market Resolver and Persistence Reload Features (Iteration 39)

Tests:
1. GET /api/diagnostics - verify 'resolver' field with skip_reasons
2. GET /api/analytics/pnl-history - verify latest_close_at and server_time
3. Backend restart resilience - verify data loaded from DB
4. Market snapshot loading - verify no_market skips reduced
5. GET /api/status - verify close_count, win_rate, daily_pnl
6. Data consistency across endpoints
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestDiagnosticsResolverFields:
    """Test /api/diagnostics returns resolver stats with skip_reasons"""
    
    def test_diagnostics_returns_resolver_field(self):
        """Verify /api/diagnostics has 'resolver' field"""
        response = requests.get(f"{BASE_URL}/api/diagnostics", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "resolver" in data, "Missing 'resolver' field in diagnostics"
        print(f"PASS: /api/diagnostics has 'resolver' field")
    
    def test_resolver_has_skip_reasons(self):
        """Verify resolver.skip_reasons has all 4 expected keys"""
        # Wait for resolver to run at least once (runs every 30s, delay 10s on startup)
        import time
        max_attempts = 5
        skip_reasons = {}
        
        for attempt in range(max_attempts):
            response = requests.get(f"{BASE_URL}/api/diagnostics", timeout=10)
            assert response.status_code == 200
            
            data = response.json()
            resolver = data.get("resolver", {})
            skip_reasons = resolver.get("skip_reasons", {})
            
            if skip_reasons:
                break
            print(f"  Waiting for resolver to run... attempt {attempt+1}/{max_attempts}")
            time.sleep(10)
        
        # Verify all 4 keys exist
        expected_keys = ["no_market", "no_end_date", "not_expired", "already_checked"]
        for key in expected_keys:
            assert key in skip_reasons, f"Missing skip_reasons.{key}"
            assert isinstance(skip_reasons[key], int), f"skip_reasons.{key} should be int"
        
        print(f"PASS: resolver.skip_reasons has all keys: {list(skip_reasons.keys())}")
        print(f"  no_market: {skip_reasons['no_market']}")
        print(f"  no_end_date: {skip_reasons['no_end_date']}")
        print(f"  not_expired: {skip_reasons['not_expired']}")
        print(f"  already_checked: {skip_reasons['already_checked']}")
    
    def test_diagnostics_has_persistence_reload_flag(self):
        """Verify has_persistence_reload=true"""
        response = requests.get(f"{BASE_URL}/api/diagnostics", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("has_persistence_reload") == True, \
            f"has_persistence_reload should be True, got {data.get('has_persistence_reload')}"
        print(f"PASS: has_persistence_reload=True")
    
    def test_diagnostics_trades_loaded_from_db(self):
        """Verify trades_loaded_from_db > 0"""
        response = requests.get(f"{BASE_URL}/api/diagnostics", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        state = data.get("state", {})
        trades_loaded = state.get("trades_loaded_from_db", 0)
        
        assert trades_loaded > 0, f"trades_loaded_from_db should be > 0, got {trades_loaded}"
        print(f"PASS: trades_loaded_from_db = {trades_loaded}")


class TestPnlHistoryNewFields:
    """Test /api/analytics/pnl-history returns latest_close_at and server_time"""
    
    def test_pnl_history_has_latest_close_at(self):
        """Verify pnl-history has latest_close_at field"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "latest_close_at" in data, "Missing 'latest_close_at' in pnl-history"
        
        latest = data["latest_close_at"]
        close_trades = data.get("close_trades", 0)
        
        # If close_trades > 0, latest_close_at should be non-null
        if close_trades > 0:
            assert latest is not None, "latest_close_at should be non-null when close_trades > 0"
            # Verify it's a valid ISO timestamp
            try:
                datetime.fromisoformat(latest.replace("Z", "+00:00"))
            except ValueError:
                pytest.fail(f"latest_close_at is not valid ISO format: {latest}")
        
        print(f"PASS: latest_close_at = {latest}")
    
    def test_pnl_history_has_server_time(self):
        """Verify pnl-history has server_time field"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "server_time" in data, "Missing 'server_time' in pnl-history"
        
        server_time = data["server_time"]
        assert server_time is not None, "server_time should not be null"
        
        # Verify it's a valid ISO timestamp
        try:
            datetime.fromisoformat(server_time.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"server_time is not valid ISO format: {server_time}")
        
        print(f"PASS: server_time = {server_time}")
    
    def test_pnl_history_close_trades_count(self):
        """Verify close_trades field exists and is >= 0"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert "close_trades" in data, "Missing 'close_trades' in pnl-history"
        
        close_trades = data["close_trades"]
        assert isinstance(close_trades, int), f"close_trades should be int, got {type(close_trades)}"
        assert close_trades >= 0, f"close_trades should be >= 0, got {close_trades}"
        
        print(f"PASS: close_trades = {close_trades}")


class TestStatusEndpoint:
    """Test /api/status returns expected stats"""
    
    def test_status_close_count_greater_than_300(self):
        """Verify close_count > 300"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get("stats", {})
        close_count = stats.get("close_count", 0)
        
        assert close_count > 300, f"close_count should be > 300, got {close_count}"
        print(f"PASS: close_count = {close_count} (> 300)")
    
    def test_status_win_rate_greater_than_zero(self):
        """Verify win_rate > 0"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get("stats", {})
        win_rate = stats.get("win_rate", 0)
        
        assert win_rate > 0, f"win_rate should be > 0, got {win_rate}"
        print(f"PASS: win_rate = {win_rate}% (> 0)")
    
    def test_status_daily_pnl_is_number(self):
        """Verify daily_pnl is a number"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get("stats", {})
        daily_pnl = stats.get("daily_pnl")
        
        assert daily_pnl is not None, "daily_pnl should not be None"
        assert isinstance(daily_pnl, (int, float)), f"daily_pnl should be number, got {type(daily_pnl)}"
        print(f"PASS: daily_pnl = ${daily_pnl}")


class TestDataConsistency:
    """Test data consistency across endpoints"""
    
    def test_close_count_consistency(self):
        """Verify close_count matches across /api/status, /api/analytics/global, /api/analytics/pnl-history"""
        # Get close_count from /api/status
        resp1 = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert resp1.status_code == 200
        status_close = resp1.json().get("stats", {}).get("close_count", 0)
        
        # Get close_trades from /api/analytics/global
        resp2 = requests.get(f"{BASE_URL}/api/analytics/global", timeout=10)
        assert resp2.status_code == 200
        global_close = resp2.json().get("strategy_performance", {}).get("close_trades", 0)
        
        # Get close_trades from /api/analytics/pnl-history
        resp3 = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert resp3.status_code == 200
        pnl_close = resp3.json().get("close_trades", 0)
        
        # All should match (allowing small variance due to live trading)
        tolerance = 5  # Allow 5 trade difference due to live updates
        
        assert abs(status_close - global_close) <= tolerance, \
            f"/api/status close_count ({status_close}) != /api/analytics/global close_trades ({global_close})"
        assert abs(status_close - pnl_close) <= tolerance, \
            f"/api/status close_count ({status_close}) != /api/analytics/pnl-history close_trades ({pnl_close})"
        
        print(f"PASS: close_count consistency verified")
        print(f"  /api/status: {status_close}")
        print(f"  /api/analytics/global: {global_close}")
        print(f"  /api/analytics/pnl-history: {pnl_close}")


class TestMarketSnapshotLoading:
    """Test market snapshot loading from DB reduces no_market skips"""
    
    def test_market_resolver_no_market_skips(self):
        """Verify no_market skips < 15 (market data loaded from DB)"""
        import time
        max_attempts = 5
        no_market = 999
        
        for attempt in range(max_attempts):
            response = requests.get(f"{BASE_URL}/api/diagnostics", timeout=10)
            assert response.status_code == 200
            
            data = response.json()
            resolver = data.get("resolver", {})
            skip_reasons = resolver.get("skip_reasons", {})
            
            if skip_reasons:
                no_market = skip_reasons.get("no_market", 999)
                break
            print(f"  Waiting for resolver to run... attempt {attempt+1}/{max_attempts}")
            time.sleep(10)
        
        # After loading market snapshots from DB, no_market should be < 15
        # (some positions may have markets that were never persisted)
        assert no_market < 15, f"no_market skips should be < 15, got {no_market}"
        print(f"PASS: no_market = {no_market} (< 15)")
        print(f"  This confirms market snapshots were loaded from MongoDB")


class TestMarketResolverHealth:
    """Test market resolver health endpoint"""
    
    def test_market_resolver_health(self):
        """Verify /api/health/market-resolver returns expected fields"""
        import time
        max_attempts = 5
        skip_reasons = {}
        
        for attempt in range(max_attempts):
            response = requests.get(f"{BASE_URL}/api/health/market-resolver", timeout=10)
            assert response.status_code == 200
            
            data = response.json()
            skip_reasons = data.get("skip_reasons", {})
            
            if skip_reasons:
                break
            print(f"  Waiting for resolver to run... attempt {attempt+1}/{max_attempts}")
            time.sleep(10)
        
        assert data.get("running") == True, "resolver should be running"
        assert "total_runs" in data, "Missing total_runs"
        assert skip_reasons, "Missing or empty skip_reasons (resolver may not have run yet)"
        
        print(f"PASS: Market resolver health check")
        print(f"  running: {data.get('running')}")
        print(f"  total_runs: {data.get('total_runs')}")
        print(f"  positions_checked: {data.get('positions_checked')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
