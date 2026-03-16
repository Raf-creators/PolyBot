"""
Test MongoDB persistence and restart resilience for Railway dashboard.

Tests:
1. Backend restart resilience - verify stats are loaded from MongoDB
2. Data consistency across endpoints after restart
3. Positions loaded from MongoDB snapshot
4. PnL history from closed trades
5. Global analytics timeseries with close_count
6. No trade duplication after restart
7. Trades endpoint returns historical data
"""

import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://edge-trading-hub-1.preview.emergentagent.com"


class TestPersistenceRestartResilience:
    """Test that after restart, MongoDB data is loaded correctly into state."""

    def test_health_endpoint(self):
        """Test /api/health returns status=ok"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["engine"] in ("running", "starting")
        print(f"PASS: Health check - engine={data['engine']}, mode={data['mode']}")

    def test_status_has_loaded_trades(self):
        """Test /api/status shows non-zero stats from MongoDB trades."""
        resp = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        
        stats = data.get("stats", {})
        
        # Verify counts are loaded from MongoDB
        assert stats.get("total_trades", 0) > 0, f"Expected total_trades > 0, got {stats.get('total_trades')}"
        assert stats.get("close_count", 0) > 0, f"Expected close_count > 0, got {stats.get('close_count')}"
        assert stats.get("win_count", 0) > 0, f"Expected win_count > 0, got {stats.get('win_count')}"
        assert stats.get("loss_count", 0) > 0, f"Expected loss_count > 0, got {stats.get('loss_count')}"
        assert stats.get("win_rate", 0) > 0, f"Expected win_rate > 0, got {stats.get('win_rate')}"
        
        # Verify daily_pnl shows value (from today's trades)
        daily_pnl = stats.get("daily_pnl", 0)
        print(f"PASS: Status stats - total_trades={stats.get('total_trades')}, "
              f"close_count={stats.get('close_count')}, win_count={stats.get('win_count')}, "
              f"loss_count={stats.get('loss_count')}, win_rate={stats.get('win_rate')}, "
              f"daily_pnl={daily_pnl}")

    def test_positions_loaded_from_snapshot(self):
        """Test /api/positions returns non-empty array from MongoDB snapshot."""
        resp = requests.get(f"{BASE_URL}/api/positions", timeout=10)
        assert resp.status_code == 200
        positions = resp.json()
        
        assert isinstance(positions, list), "Expected positions to be a list"
        assert len(positions) > 0, f"Expected positions > 0, got {len(positions)}"
        
        # Verify position structure
        first_pos = positions[0]
        assert "token_id" in first_pos
        assert "size" in first_pos
        assert "avg_cost" in first_pos
        
        print(f"PASS: Positions loaded - count={len(positions)}, "
              f"sample_token={first_pos.get('token_id')[:20]}...")

    def test_pnl_history_non_empty(self):
        """Test /api/analytics/pnl-history has non-empty points array with closed trades."""
        resp = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        
        points = data.get("points", [])
        close_trades = data.get("close_trades", 0)
        current_pnl = data.get("current_pnl", 0)
        
        assert len(points) > 0, f"Expected points > 0, got {len(points)}"
        assert close_trades > 0, f"Expected close_trades > 0, got {close_trades}"
        
        # Verify points structure
        first_point = points[0]
        assert "timestamp" in first_point
        assert "cumulative_pnl" in first_point
        assert "trade_pnl" in first_point
        assert "strategy" in first_point
        
        print(f"PASS: PnL history - points={len(points)}, close_trades={close_trades}, "
              f"current_pnl={current_pnl}")

    def test_global_analytics_strategy_performance(self):
        """Test /api/analytics/global has non-zero strategy_performance metrics."""
        resp = requests.get(f"{BASE_URL}/api/analytics/global", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        
        perf = data.get("strategy_performance", {})
        
        assert perf.get("close_trades", 0) > 0, f"Expected close_trades > 0, got {perf.get('close_trades')}"
        assert perf.get("win_count", 0) > 0, f"Expected win_count > 0, got {perf.get('win_count')}"
        assert perf.get("loss_count", 0) > 0, f"Expected loss_count > 0, got {perf.get('loss_count')}"
        assert perf.get("win_rate", 0) > 0, f"Expected win_rate > 0, got {perf.get('win_rate')}"
        
        # Verify realized_pnl is computed
        realized_pnl = perf.get("realized_pnl", 0)
        
        print(f"PASS: Global analytics strategy_performance - close_trades={perf.get('close_trades')}, "
              f"realized_pnl={realized_pnl}, win_rate={perf.get('win_rate')}")

    def test_global_analytics_timeseries(self):
        """Test /api/analytics/global timeseries.cumulative_pnl has non-zero last point with close_count."""
        resp = requests.get(f"{BASE_URL}/api/analytics/global", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        
        timeseries = data.get("timeseries", {})
        cum_pnl = timeseries.get("cumulative_pnl", [])
        
        assert len(cum_pnl) > 0, f"Expected cumulative_pnl > 0, got {len(cum_pnl)}"
        
        last_point = cum_pnl[-1]
        assert "date" in last_point
        assert "cumulative_pnl" in last_point
        assert "close_count" in last_point
        
        # Verify last point has non-zero values
        assert last_point.get("cumulative_pnl", 0) != 0 or last_point.get("close_count", 0) > 0, \
            f"Expected non-zero cumulative_pnl or close_count in last point"
        
        print(f"PASS: Global analytics timeseries - points={len(cum_pnl)}, "
              f"last_point_date={last_point.get('date')}, "
              f"last_cumulative_pnl={last_point.get('cumulative_pnl')}, "
              f"last_close_count={last_point.get('close_count')}")

    def test_data_consistency_close_count(self):
        """Test close_count matches across /api/status, /api/analytics/global, /api/analytics/pnl-history."""
        # Get status
        status_resp = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        status_close_count = status_data.get("stats", {}).get("close_count", 0)
        
        # Get global analytics
        global_resp = requests.get(f"{BASE_URL}/api/analytics/global", timeout=10)
        assert global_resp.status_code == 200
        global_data = global_resp.json()
        global_close_count = global_data.get("strategy_performance", {}).get("close_trades", 0)
        
        # Get pnl history
        pnl_resp = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert pnl_resp.status_code == 200
        pnl_data = pnl_resp.json()
        pnl_close_count = pnl_data.get("close_trades", 0)
        
        # All should match
        assert status_close_count == global_close_count, \
            f"status.close_count ({status_close_count}) != global.close_trades ({global_close_count})"
        assert status_close_count == pnl_close_count, \
            f"status.close_count ({status_close_count}) != pnl.close_trades ({pnl_close_count})"
        
        print(f"PASS: Data consistency - all endpoints show close_count={status_close_count}")

    def test_trades_endpoint_returns_data(self):
        """Test /api/trades returns trade history."""
        resp = requests.get(f"{BASE_URL}/api/trades", timeout=10)
        assert resp.status_code == 200
        trades = resp.json()
        
        assert isinstance(trades, list), "Expected trades to be a list"
        # API returns last 100 trades
        assert len(trades) > 0, f"Expected trades > 0, got {len(trades)}"
        
        # Verify trade structure
        first_trade = trades[0]
        assert "id" in first_trade
        assert "token_id" in first_trade
        assert "side" in first_trade
        assert "price" in first_trade
        assert "size" in first_trade
        assert "strategy_id" in first_trade
        
        # Check for resolver trades (pnl != 0)
        trades_with_pnl = [t for t in trades if t.get("pnl", 0) != 0]
        
        print(f"PASS: Trades endpoint - returned={len(trades)}, "
              f"with_pnl={len(trades_with_pnl)}, "
              f"strategies={set(t.get('strategy_id') for t in trades)}")


class TestNoTradeDuplication:
    """Test that trade count doesn't increase spuriously after restart."""

    def test_trade_count_stable(self):
        """Get trade count, wait, get again - should be stable (or only increase from live trading)."""
        import time
        
        # First count
        resp1 = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert resp1.status_code == 200
        count1 = resp1.json().get("stats", {}).get("total_trades", 0)
        
        # Wait a bit
        time.sleep(2)
        
        # Second count
        resp2 = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert resp2.status_code == 200
        count2 = resp2.json().get("stats", {}).get("total_trades", 0)
        
        # Count should be stable or only increase by a small amount (live trading)
        diff = count2 - count1
        assert diff >= 0, f"Trade count decreased: {count1} -> {count2}"
        assert diff < 50, f"Trade count increased too much: {count1} -> {count2} (diff={diff})"
        
        print(f"PASS: Trade count stable - count1={count1}, count2={count2}, diff={diff}")


class TestWinRateConsistency:
    """Test win_rate calculation is consistent."""

    def test_win_rate_calculation(self):
        """Verify win_rate = win_count / close_count * 100."""
        resp = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert resp.status_code == 200
        stats = resp.json().get("stats", {})
        
        win_count = stats.get("win_count", 0)
        loss_count = stats.get("loss_count", 0)
        close_count = stats.get("close_count", 0)
        win_rate = stats.get("win_rate", 0)
        
        # Verify close_count = win_count + loss_count
        expected_close_count = win_count + loss_count
        assert close_count == expected_close_count, \
            f"close_count ({close_count}) != win_count + loss_count ({expected_close_count})"
        
        # Verify win_rate calculation
        if close_count > 0:
            expected_win_rate = round(win_count / close_count * 100, 2)
            assert abs(win_rate - expected_win_rate) < 0.1, \
                f"win_rate ({win_rate}) != expected ({expected_win_rate})"
        
        print(f"PASS: Win rate calculation - win_count={win_count}, loss_count={loss_count}, "
              f"close_count={close_count}, win_rate={win_rate}")


class TestEngineStatusAfterLoad:
    """Test engine status after loading from MongoDB."""

    def test_engine_running(self):
        """Verify engine status is 'running' after loading state."""
        resp = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        
        status = data.get("status")
        assert status == "running", f"Expected status='running', got '{status}'"
        
        print(f"PASS: Engine running - status={status}, mode={data.get('mode')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
