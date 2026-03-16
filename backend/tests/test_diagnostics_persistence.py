"""
Test diagnostics endpoint and persistence reload verification.
Tests the fix for Railway production dashboard showing 0 closed trades/PnL after restart.
Validates load_state_from_db() functionality and /api/diagnostics endpoint.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDiagnosticsEndpoint:
    """Test the /api/diagnostics endpoint returns correct build/environment info."""
    
    def test_diagnostics_returns_json(self):
        """GET /api/diagnostics returns valid JSON with all expected fields."""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "environment" in data, "Missing 'environment' field"
        assert "git_commit" in data, "Missing 'git_commit' field"
        assert "server_start_time" in data, "Missing 'server_start_time' field"
        assert "database" in data, "Missing 'database' field"
        assert "state" in data, "Missing 'state' field"
        assert "has_persistence_reload" in data, "Missing 'has_persistence_reload' field"
        print(f"PASS: /api/diagnostics returned valid JSON with all fields")
    
    def test_diagnostics_environment(self):
        """Verify environment is emergent_preview."""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        data = response.json()
        
        assert data["environment"] == "emergent_preview", f"Expected emergent_preview, got {data['environment']}"
        print(f"PASS: environment = {data['environment']}")
    
    def test_diagnostics_git_commit(self):
        """Verify git commit hash is present."""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        data = response.json()
        
        assert data["git_commit"] is not None, "git_commit is None"
        assert data["git_commit"] != "unknown", "git_commit is 'unknown'"
        assert len(data["git_commit"]) > 6, f"git_commit too short: {data['git_commit']}"
        print(f"PASS: git_commit = {data['git_commit']}")
    
    def test_diagnostics_server_start_time(self):
        """Verify server_start_time is a valid ISO timestamp."""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        data = response.json()
        
        assert data["server_start_time"] is not None, "server_start_time is None"
        assert "T" in data["server_start_time"], "server_start_time not in ISO format"
        print(f"PASS: server_start_time = {data['server_start_time']}")
    
    def test_diagnostics_database(self):
        """Verify database name and host are present."""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        data = response.json()
        
        db = data["database"]
        assert "name" in db, "Missing database.name"
        assert "host" in db, "Missing database.host"
        assert db["name"] == "test_database", f"Expected test_database, got {db['name']}"
        print(f"PASS: database.name = {db['name']}, database.host = {db['host']}")
    
    def test_diagnostics_trades_loaded_from_db(self):
        """Verify trades_loaded_from_db > 0 (persistence reload working)."""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        data = response.json()
        
        state = data["state"]
        trades_loaded = state.get("trades_loaded_from_db", 0)
        assert trades_loaded > 0, f"trades_loaded_from_db = {trades_loaded} (expected > 0)"
        print(f"PASS: trades_loaded_from_db = {trades_loaded}")
    
    def test_diagnostics_has_persistence_reload(self):
        """Verify has_persistence_reload = True (this code version has the fix)."""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        data = response.json()
        
        assert data.get("has_persistence_reload") is True, "has_persistence_reload is not True"
        print(f"PASS: has_persistence_reload = True")


class TestRestartResilience:
    """Test that restart resilience works - stats are non-zero after boot."""
    
    def test_status_close_count_nonzero(self):
        """GET /api/status close_count > 0."""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get("stats", {})
        close_count = stats.get("close_count", 0)
        assert close_count > 0, f"close_count = {close_count} (expected > 0)"
        print(f"PASS: close_count = {close_count}")
    
    def test_status_win_rate_nonzero(self):
        """GET /api/status win_rate > 0."""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        
        stats = data.get("stats", {})
        win_rate = stats.get("win_rate", 0)
        assert win_rate > 0, f"win_rate = {win_rate} (expected > 0)"
        print(f"PASS: win_rate = {win_rate}%")
    
    def test_status_daily_pnl_is_number(self):
        """GET /api/status daily_pnl is a number."""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        
        stats = data.get("stats", {})
        daily_pnl = stats.get("daily_pnl")
        assert daily_pnl is not None, "daily_pnl is None"
        assert isinstance(daily_pnl, (int, float)), f"daily_pnl is not a number: {type(daily_pnl)}"
        print(f"PASS: daily_pnl = {daily_pnl}")


class TestDataConsistency:
    """Test that close_count is consistent across all analytics endpoints."""
    
    def test_close_count_consistency(self):
        """close_count matches across /api/status, /api/analytics/global, /api/analytics/pnl-history."""
        # Get close_count from /api/status
        status_resp = requests.get(f"{BASE_URL}/api/status")
        assert status_resp.status_code == 200
        status_close_count = status_resp.json().get("stats", {}).get("close_count", 0)
        
        # Get close_trades from /api/analytics/global
        global_resp = requests.get(f"{BASE_URL}/api/analytics/global")
        assert global_resp.status_code == 200
        global_close_trades = global_resp.json().get("strategy_performance", {}).get("close_trades", 0)
        
        # Get close_trades from /api/analytics/pnl-history
        pnl_resp = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert pnl_resp.status_code == 200
        pnl_close_trades = pnl_resp.json().get("close_trades", 0)
        
        # All should match (allow small delta for live updates during test)
        assert status_close_count > 0, f"status close_count = {status_close_count}"
        assert global_close_trades > 0, f"global close_trades = {global_close_trades}"
        assert pnl_close_trades > 0, f"pnl close_trades = {pnl_close_trades}"
        
        # Within tolerance of 5 trades (live system may have updates)
        assert abs(status_close_count - global_close_trades) <= 5, \
            f"status vs global mismatch: {status_close_count} vs {global_close_trades}"
        assert abs(status_close_count - pnl_close_trades) <= 5, \
            f"status vs pnl mismatch: {status_close_count} vs {pnl_close_trades}"
        
        print(f"PASS: Data consistency - status={status_close_count}, global={global_close_trades}, pnl={pnl_close_trades}")


class TestGlobalAnalyticsTimeseries:
    """Test /api/analytics/global timeseries.cumulative_pnl."""
    
    def test_timeseries_cumulative_pnl_nonzero(self):
        """timeseries.cumulative_pnl last point has non-zero cumulative_pnl."""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        assert response.status_code == 200
        
        data = response.json()
        timeseries = data.get("timeseries", {})
        cumulative_pnl = timeseries.get("cumulative_pnl", [])
        
        assert len(cumulative_pnl) > 0, "cumulative_pnl array is empty"
        
        last_point = cumulative_pnl[-1]
        assert "cumulative_pnl" in last_point, "Last point missing cumulative_pnl field"
        assert last_point["cumulative_pnl"] != 0, f"cumulative_pnl = 0 in last point"
        print(f"PASS: Last timeseries point cumulative_pnl = {last_point['cumulative_pnl']}")


class TestPnlHistory:
    """Test /api/analytics/pnl-history endpoint."""
    
    def test_pnl_history_close_trades_count(self):
        """close_trades > 300 and points array length matches."""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        
        data = response.json()
        close_trades = data.get("close_trades", 0)
        points = data.get("points", [])
        
        assert close_trades > 300, f"close_trades = {close_trades} (expected > 300)"
        assert len(points) == close_trades, f"points length {len(points)} != close_trades {close_trades}"
        print(f"PASS: close_trades = {close_trades}, points length matches")


class TestPositions:
    """Test /api/positions endpoint."""
    
    def test_positions_non_empty(self):
        """GET /api/positions returns non-empty array."""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        
        positions = response.json()
        assert isinstance(positions, list), "positions is not a list"
        assert len(positions) > 0, "positions array is empty"
        print(f"PASS: Loaded {len(positions)} positions")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
