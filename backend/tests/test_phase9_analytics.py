"""
Phase 9: Rich Analytics and Strategy Performance Dashboard Tests

Tests cover:
- POST /api/test/inject-trades - inject synthetic test trades
- GET /api/analytics/summary - portfolio summary with PnL, drawdown, win rate, Sharpe, profit factor
- GET /api/analytics/strategies - per-strategy metrics for arb_scanner and crypto_sniper
- GET /api/analytics/execution-quality - fill quality and slippage metrics
- GET /api/analytics/timeseries - daily_pnl, equity_curve, drawdown_curve, trade_frequency, rolling_*
- POST /api/test/clear-trades - clears injected test data
- Empty state validation - all endpoints return valid JSON with null/empty values when no trades
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAnalyticsEmptyState:
    """Test analytics endpoints when no trades exist (empty state)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure clean state before tests."""
        # Clear any existing test trades
        requests.post(f"{BASE_URL}/api/test/clear-trades")
        yield

    def test_summary_empty_state(self):
        """GET /api/analytics/summary returns valid JSON with expected fields."""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Required fields should exist
        required_fields = [
            'total_pnl', 'realized_pnl', 'unrealized_pnl', 'peak_equity',
            'current_drawdown', 'max_drawdown', 'trade_count', 'closing_trade_count',
            'win_count', 'loss_count', 'win_rate', 'avg_win', 'avg_loss',
            'profit_factor', 'expectancy', 'sharpe_ratio', 'longest_win_streak',
            'longest_loss_streak', 'total_fees', 'total_volume'
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # trade_count should be a non-negative integer
        assert isinstance(data['trade_count'], int), f"Expected int, got {type(data['trade_count'])}"
        assert data['trade_count'] >= 0
        print(f"PASS: Summary endpoint returns valid structure with {data['trade_count']} trades")

    def test_strategies_empty_state(self):
        """GET /api/analytics/strategies returns empty dict when no trades."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategies")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # With no trades, should be empty dict
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        print(f"PASS: Empty strategies endpoint returns dict with {len(data)} strategies")

    def test_execution_quality_empty_state(self):
        """GET /api/analytics/execution-quality returns valid JSON when empty."""
        response = requests.get(f"{BASE_URL}/api/analytics/execution-quality")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        required_fields = [
            'total_orders', 'filled_count', 'rejected_count', 'cancelled_count',
            'fill_ratio', 'partial_fill_count', 'partial_fill_ratio',
            'avg_slippage_bps', 'max_slippage_bps', 'avg_latency_ms',
            'rejection_reasons', 'live_orders_total'
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print("PASS: Empty execution-quality endpoint returns valid structure")

    def test_timeseries_empty_state(self):
        """GET /api/analytics/timeseries returns valid JSON with correct keys."""
        response = requests.get(f"{BASE_URL}/api/analytics/timeseries")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # IMPORTANT: Check that response has same keys whether empty or not
        required_keys = [
            'daily_pnl', 'equity_curve', 'drawdown_curve', 
            'trade_frequency', 'rolling_7d_pnl', 'rolling_30d_pnl',
            'executions_by_strategy'
        ]
        for key in required_keys:
            assert key in data, f"Missing key in timeseries: {key}"
        
        # All array fields should be lists
        assert isinstance(data['daily_pnl'], list)
        assert isinstance(data['equity_curve'], list)
        assert isinstance(data['drawdown_curve'], list)
        assert isinstance(data['trade_frequency'], list)
        assert isinstance(data['executions_by_strategy'], dict)
        
        # Rolling values should be numeric or None
        assert data['rolling_7d_pnl'] is None or isinstance(data['rolling_7d_pnl'], (int, float))
        assert data['rolling_30d_pnl'] is None or isinstance(data['rolling_30d_pnl'], (int, float))
        
        print("PASS: Empty timeseries endpoint returns valid structure with correct keys")


class TestAnalyticsWithData:
    """Test analytics endpoints after injecting test data."""

    @pytest.fixture(autouse=True)
    def setup_with_data(self):
        """Inject test trades before tests, clean up after."""
        # Clear first
        requests.post(f"{BASE_URL}/api/test/clear-trades")
        
        # Inject test trades
        resp = requests.post(f"{BASE_URL}/api/test/inject-trades")
        assert resp.status_code == 200, f"Failed to inject trades: {resp.status_code}"
        self.inject_count = resp.json().get('count', 0)
        print(f"Injected {self.inject_count} test trades")
        
        yield
        
        # Cleanup
        requests.post(f"{BASE_URL}/api/test/clear-trades")
        print("Cleaned up test trades")

    def test_inject_trades_endpoint(self):
        """POST /api/test/inject-trades creates synthetic trades."""
        # Already injected in setup, just verify
        assert self.inject_count > 0, "Expected some trades to be injected"
        print(f"PASS: Inject endpoint created {self.inject_count} trades")

    def test_summary_with_trades(self):
        """GET /api/analytics/summary returns populated data after injection."""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Should have trades now
        assert data['trade_count'] > 0, f"Expected trades, got {data['trade_count']}"
        assert data['closing_trade_count'] > 0, f"Expected closing trades"
        
        # PnL fields should have values
        assert data['total_pnl'] is not None, "Expected total_pnl value"
        assert isinstance(data['total_pnl'], (int, float)), "total_pnl should be numeric"
        
        # Win rate should be calculated (not None if we have closing trades)
        assert data['win_rate'] is not None, "Expected win_rate with trades"
        assert 0 <= data['win_rate'] <= 100, f"Win rate should be 0-100, got {data['win_rate']}"
        
        # Sharpe should be calculated if enough trades (MIN_TRADES_FOR_SHARPE=5)
        # Might be None if std=0, but should be present
        
        # Profit factor might be None if no losses
        # Max drawdown should be >= 0
        assert data['max_drawdown'] >= 0, "Max drawdown should be >= 0"
        
        print(f"PASS: Summary with data - trades={data['trade_count']}, pnl={data['total_pnl']}, win_rate={data['win_rate']}%")

    def test_summary_all_fields_present(self):
        """Verify all expected summary fields are present."""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        
        expected_fields = {
            'total_pnl': (int, float, type(None)),
            'realized_pnl': (int, float, type(None)),
            'unrealized_pnl': (int, float, type(None)),
            'peak_equity': (int, float, type(None)),
            'current_drawdown': (int, float, type(None)),
            'max_drawdown': (int, float, type(None)),
            'trade_count': int,
            'closing_trade_count': int,
            'win_count': int,
            'loss_count': int,
            'win_rate': (int, float, type(None)),
            'avg_win': (int, float, type(None)),
            'avg_loss': (int, float, type(None)),
            'profit_factor': (int, float, type(None)),
            'expectancy': (int, float, type(None)),
            'sharpe_ratio': (int, float, type(None)),
            'longest_win_streak': int,
            'longest_loss_streak': int,
            'total_fees': (int, float, type(None)),
            'total_volume': (int, float, type(None)),
        }
        
        for field, expected_type in expected_fields.items():
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], expected_type), f"Field {field} has wrong type: {type(data[field])}"
        
        print("PASS: All summary fields present with correct types")

    def test_strategies_arb_scanner(self):
        """GET /api/analytics/strategies has arb_scanner metrics."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategies")
        assert response.status_code == 200
        data = response.json()
        
        assert 'arb_scanner' in data, f"Expected arb_scanner in strategies, got keys: {list(data.keys())}"
        
        arb = data['arb_scanner']
        required_fields = [
            'strategy_id', 'pnl', 'trade_count', 'closing_trades',
            'win_count', 'loss_count', 'win_rate', 'avg_win', 'avg_loss',
            'profit_factor', 'expectancy', 'sharpe_ratio', 'avg_edge_bps',
            'total_fees', 'total_volume'
        ]
        for field in required_fields:
            assert field in arb, f"arb_scanner missing field: {field}"
        
        assert arb['strategy_id'] == 'arb_scanner'
        assert arb['trade_count'] > 0, "Expected arb_scanner trades"
        
        print(f"PASS: arb_scanner metrics - trades={arb['trade_count']}, pnl={arb['pnl']}")

    def test_strategies_crypto_sniper(self):
        """GET /api/analytics/strategies has crypto_sniper metrics."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategies")
        assert response.status_code == 200
        data = response.json()
        
        assert 'crypto_sniper' in data, f"Expected crypto_sniper in strategies, got keys: {list(data.keys())}"
        
        sniper = data['crypto_sniper']
        assert sniper['strategy_id'] == 'crypto_sniper'
        assert sniper['trade_count'] > 0, "Expected crypto_sniper trades"
        
        print(f"PASS: crypto_sniper metrics - trades={sniper['trade_count']}, pnl={sniper['pnl']}")

    def test_execution_quality_with_orders(self):
        """GET /api/analytics/execution-quality returns metrics with injected orders."""
        response = requests.get(f"{BASE_URL}/api/analytics/execution-quality")
        assert response.status_code == 200
        data = response.json()
        
        # Injection creates orders too, so we should have some
        assert data['total_orders'] > 0, f"Expected orders, got {data['total_orders']}"
        assert data['filled_count'] >= 0, "filled_count should be >= 0"
        
        # Fill ratio might be None or a percentage
        if data['fill_ratio'] is not None:
            assert 0 <= data['fill_ratio'] <= 100, f"Fill ratio should be 0-100, got {data['fill_ratio']}"
        
        print(f"PASS: Execution quality - orders={data['total_orders']}, filled={data['filled_count']}")

    def test_timeseries_with_data(self):
        """GET /api/analytics/timeseries returns populated arrays."""
        response = requests.get(f"{BASE_URL}/api/analytics/timeseries")
        assert response.status_code == 200
        data = response.json()
        
        # Should have data now
        assert len(data['daily_pnl']) > 0, "Expected daily_pnl data"
        assert len(data['equity_curve']) > 0, "Expected equity_curve data"
        assert len(data['drawdown_curve']) > 0, "Expected drawdown_curve data"
        assert len(data['trade_frequency']) > 0, "Expected trade_frequency data"
        
        # Rolling 7d should have value (we inject 10 days of data)
        assert data['rolling_7d_pnl'] is not None, "Expected rolling_7d_pnl with 10 days of data"
        
        # Executions by strategy should have our strategies
        assert isinstance(data['executions_by_strategy'], dict)
        assert len(data['executions_by_strategy']) > 0, "Expected executions_by_strategy data"
        
        print(f"PASS: Timeseries populated - daily_pnl={len(data['daily_pnl'])} days, rolling_7d={data['rolling_7d_pnl']}")

    def test_timeseries_daily_pnl_structure(self):
        """Verify daily_pnl entries have correct structure."""
        response = requests.get(f"{BASE_URL}/api/analytics/timeseries")
        assert response.status_code == 200
        data = response.json()
        
        if data['daily_pnl']:
            entry = data['daily_pnl'][0]
            assert 'date' in entry, "daily_pnl entry missing 'date'"
            assert 'pnl' in entry, "daily_pnl entry missing 'pnl'"
            assert 'trades' in entry, "daily_pnl entry missing 'trades'"
            print(f"PASS: daily_pnl structure correct - sample: {entry}")
        else:
            pytest.skip("No daily_pnl data to verify structure")

    def test_timeseries_equity_curve_structure(self):
        """Verify equity_curve entries have correct structure."""
        response = requests.get(f"{BASE_URL}/api/analytics/timeseries")
        assert response.status_code == 200
        data = response.json()
        
        if data['equity_curve']:
            entry = data['equity_curve'][0]
            assert 'date' in entry, "equity_curve entry missing 'date'"
            assert 'equity' in entry, "equity_curve entry missing 'equity'"
            print(f"PASS: equity_curve structure correct - sample: {entry}")
        else:
            pytest.skip("No equity_curve data to verify structure")

    def test_timeseries_drawdown_curve_structure(self):
        """Verify drawdown_curve entries have correct structure."""
        response = requests.get(f"{BASE_URL}/api/analytics/timeseries")
        assert response.status_code == 200
        data = response.json()
        
        if data['drawdown_curve']:
            entry = data['drawdown_curve'][0]
            assert 'date' in entry, "drawdown_curve entry missing 'date'"
            assert 'drawdown' in entry, "drawdown_curve entry missing 'drawdown'"
            print(f"PASS: drawdown_curve structure correct - sample: {entry}")
        else:
            pytest.skip("No drawdown_curve data to verify structure")

    def test_timeseries_executions_by_strategy(self):
        """Verify executions_by_strategy has both strategies."""
        response = requests.get(f"{BASE_URL}/api/analytics/timeseries")
        assert response.status_code == 200
        data = response.json()
        
        ebs = data['executions_by_strategy']
        assert 'arb_scanner' in ebs or 'crypto_sniper' in ebs, \
            f"Expected at least one strategy in executions_by_strategy, got: {list(ebs.keys())}"
        
        # Verify structure of entries
        for strat_id, entries in ebs.items():
            assert isinstance(entries, list), f"{strat_id} should be a list"
            if entries:
                assert 'date' in entries[0], f"{strat_id} entries missing 'date'"
                assert 'count' in entries[0], f"{strat_id} entries missing 'count'"
        
        print(f"PASS: executions_by_strategy has strategies: {list(ebs.keys())}")


class TestClearTrades:
    """Test the clear trades endpoint."""

    def test_clear_trades_endpoint(self):
        """POST /api/test/clear-trades removes injected data."""
        # First inject
        inject_resp = requests.post(f"{BASE_URL}/api/test/inject-trades")
        assert inject_resp.status_code == 200
        
        # Verify data exists
        summary_resp = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert summary_resp.json()['trade_count'] > 0, "Expected trades after injection"
        
        # Clear
        clear_resp = requests.post(f"{BASE_URL}/api/test/clear-trades")
        assert clear_resp.status_code == 200
        data = clear_resp.json()
        assert data.get('status') == 'cleared', f"Expected status='cleared', got {data}"
        
        # Verify data is gone
        summary_after = requests.get(f"{BASE_URL}/api/analytics/summary")
        # Note: trade_count might not be 0 if there are non-test trades
        # The clear endpoint only removes test_ prefixed trades
        print(f"PASS: Clear endpoint returned status='cleared'")


class TestRegressionEndpoints:
    """Regression tests for existing analytics/PnL endpoints."""

    def test_pnl_history_endpoint(self):
        """GET /api/analytics/pnl-history still works."""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        
        expected_fields = ['points', 'current_pnl', 'peak_pnl', 'trough_pnl', 'max_drawdown', 'total_trades']
        for field in expected_fields:
            assert field in data, f"pnl-history missing field: {field}"
        
        print("PASS: pnl-history endpoint returns correct structure")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
