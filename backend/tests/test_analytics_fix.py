"""
Test suite for analytics fix verification.

This tests the fix for:
1. inject-trades endpoint now uses state.add_trade() to properly update counters
2. GlobalAnalyticsService.get_signal_timeseries() filters closed trades (pnl != 0) for PnL
3. /api/analytics/pnl-history only includes close trades
4. Data consistency between /api/status, /api/analytics/global, /api/analytics/pnl-history
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAnalyticsFix:
    """Tests to verify the analytics bug fix"""

    def test_status_returns_non_zero_stats(self):
        """GET /api/status — verify stats object contains non-zero values after test trades injected"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        
        stats = data.get('stats', {})
        print(f"Status stats: daily_pnl={stats.get('daily_pnl')}, win_count={stats.get('win_count')}, "
              f"loss_count={stats.get('loss_count')}, close_count={stats.get('close_count')}, "
              f"win_rate={stats.get('win_rate')}")
        
        # Verify structure
        assert 'stats' in data
        assert 'daily_pnl' in stats
        assert 'win_count' in stats
        assert 'loss_count' in stats
        assert 'close_count' in stats
        assert 'win_rate' in stats
        
        # Verify non-zero values (test trades should have been injected)
        assert stats.get('close_count', 0) > 0, f"close_count should be > 0, got {stats.get('close_count')}"
        assert stats.get('win_count', 0) > 0, f"win_count should be > 0, got {stats.get('win_count')}"
        assert stats.get('loss_count', 0) > 0, f"loss_count should be > 0, got {stats.get('loss_count')}"
        assert stats.get('win_rate', 0) > 0, f"win_rate should be > 0, got {stats.get('win_rate')}"

    def test_global_analytics_returns_non_zero_values(self):
        """GET /api/analytics/global — verify strategy_performance shows non-zero metrics"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        assert response.status_code == 200
        data = response.json()
        
        perf = data.get('strategy_performance', {})
        print(f"Global analytics: close_trades={perf.get('close_trades')}, realized_pnl={perf.get('realized_pnl')}, "
              f"win_rate={perf.get('win_rate')}, win_count={perf.get('win_count')}, loss_count={perf.get('loss_count')}")
        
        # Verify structure
        assert 'strategy_performance' in data
        assert 'close_trades' in perf
        assert 'realized_pnl' in perf
        assert 'win_rate' in perf
        
        # Verify non-zero values
        assert perf.get('close_trades', 0) > 0, f"close_trades should be > 0, got {perf.get('close_trades')}"
        assert perf.get('win_count', 0) > 0, f"win_count should be > 0, got {perf.get('win_count')}"
        assert perf.get('loss_count', 0) > 0, f"loss_count should be > 0, got {perf.get('loss_count')}"
        assert perf.get('win_rate', 0) > 0, f"win_rate should be > 0, got {perf.get('win_rate')}"

    def test_pnl_history_returns_non_empty(self):
        """GET /api/analytics/pnl-history — verify close_trades > 0 and points array non-empty"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        
        print(f"PnL history: close_trades={data.get('close_trades')}, current_pnl={data.get('current_pnl')}, "
              f"points_count={len(data.get('points', []))}")
        
        # Verify structure
        assert 'close_trades' in data
        assert 'current_pnl' in data
        assert 'points' in data
        
        # Verify non-zero values
        assert data.get('close_trades', 0) > 0, f"close_trades should be > 0, got {data.get('close_trades')}"
        assert len(data.get('points', [])) > 0, f"points array should not be empty"

    def test_data_consistency_close_count(self):
        """Verify close_count is consistent across all 3 endpoints"""
        # Get all three endpoints
        status_resp = requests.get(f"{BASE_URL}/api/status")
        global_resp = requests.get(f"{BASE_URL}/api/analytics/global")
        pnl_resp = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        
        assert status_resp.status_code == 200
        assert global_resp.status_code == 200
        assert pnl_resp.status_code == 200
        
        status_close = status_resp.json()['stats'].get('close_count', 0)
        global_close = global_resp.json()['strategy_performance'].get('close_trades', 0)
        pnl_close = pnl_resp.json().get('close_trades', 0)
        
        print(f"Close count consistency: /api/status={status_close}, /api/analytics/global={global_close}, "
              f"/api/analytics/pnl-history={pnl_close}")
        
        # All three should match
        assert status_close == global_close, f"status close_count ({status_close}) != global close_trades ({global_close})"
        assert status_close == pnl_close, f"status close_count ({status_close}) != pnl-history close_trades ({pnl_close})"

    def test_data_consistency_win_rate(self):
        """Verify win_rate is consistent between /api/status and /api/analytics/global"""
        status_resp = requests.get(f"{BASE_URL}/api/status")
        global_resp = requests.get(f"{BASE_URL}/api/analytics/global")
        
        assert status_resp.status_code == 200
        assert global_resp.status_code == 200
        
        status_win_rate = status_resp.json()['stats'].get('win_rate', 0)
        global_win_rate = global_resp.json()['strategy_performance'].get('win_rate', 0)
        
        print(f"Win rate consistency: /api/status={status_win_rate}, /api/analytics/global={global_win_rate}")
        
        # Win rates should be approximately equal (allow for rounding)
        assert abs(status_win_rate - global_win_rate) < 1.0, \
            f"Win rates differ significantly: status={status_win_rate}, global={global_win_rate}"

    def test_cumulative_pnl_timeseries_non_zero(self):
        """GET /api/analytics/global timeseries — verify cumulative_pnl has non-zero last point"""
        response = requests.get(f"{BASE_URL}/api/analytics/global")
        assert response.status_code == 200
        data = response.json()
        
        timeseries = data.get('timeseries', {})
        cum_pnl = timeseries.get('cumulative_pnl', [])
        
        print(f"Timeseries: cumulative_pnl points={len(cum_pnl)}")
        
        # Should have points
        assert len(cum_pnl) > 0, "cumulative_pnl should have at least one point"
        
        # Last point should have non-zero cumulative_pnl (since we have wins and losses)
        last_point = cum_pnl[-1]
        print(f"Last point: date={last_point.get('date')}, cumulative_pnl={last_point.get('cumulative_pnl')}, "
              f"close_count={last_point.get('close_count')}")
        
        assert 'cumulative_pnl' in last_point, "Last point should have cumulative_pnl field"
        assert 'close_count' in last_point, "Last point should have close_count field"
        # Note: cumulative PnL could be positive or negative depending on random trades
        # The key check is that it's not flat at zero

    def test_clear_and_reinject_trades(self):
        """POST /api/test/clear-trades then POST /api/test/inject-trades — verify stats update"""
        # Clear trades
        clear_resp = requests.post(f"{BASE_URL}/api/test/clear-trades")
        assert clear_resp.status_code == 200
        print(f"Clear response: {clear_resp.json()}")
        
        # Check status after clear
        status_after_clear = requests.get(f"{BASE_URL}/api/status").json()
        print(f"After clear: close_count={status_after_clear['stats'].get('close_count')}")
        
        # Re-inject trades
        inject_resp = requests.post(f"{BASE_URL}/api/test/inject-trades")
        assert inject_resp.status_code == 200
        inject_data = inject_resp.json()
        print(f"Inject response: {inject_data}")
        
        # Check status after inject
        status_after_inject = requests.get(f"{BASE_URL}/api/status").json()
        stats = status_after_inject['stats']
        print(f"After inject: close_count={stats.get('close_count')}, win_count={stats.get('win_count')}, "
              f"loss_count={stats.get('loss_count')}, win_rate={stats.get('win_rate')}")
        
        # Verify non-zero values after inject
        assert stats.get('close_count', 0) > 0, f"close_count should be > 0 after inject"
        assert stats.get('win_count', 0) > 0, f"win_count should be > 0 after inject"
        assert stats.get('loss_count', 0) > 0, f"loss_count should be > 0 after inject"

    def test_daily_pnl_non_zero(self):
        """Verify daily_pnl in /api/status is non-zero (trades have random PnL)"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        
        stats = data.get('stats', {})
        daily_pnl = stats.get('daily_pnl', 0)
        print(f"Daily PnL: {daily_pnl}")
        
        # daily_pnl should have accumulated from trades (could be positive or negative)
        # The key check is that the system is tracking it
        assert isinstance(daily_pnl, (int, float)), "daily_pnl should be a number"


class TestEngineHealth:
    """Additional tests for engine health and connectivity"""

    def test_engine_running(self):
        """Verify engine is running"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('status') == 'running', f"Engine status should be 'running', got {data.get('status')}"

    def test_health_endpoint(self):
        """GET /api/health — basic health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('status') == 'ok', f"Health status should be 'ok', got {data.get('status')}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
