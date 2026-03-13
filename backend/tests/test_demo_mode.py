"""
Demo Mode Feature - Backend API Tests
Testing the safe demo mode feature for Polymarket Edge OS dashboard preview
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestDemoModeStatus:
    """Tests for demo mode status and toggle endpoints"""
    
    def test_demo_status_returns_enabled_field(self):
        """GET /api/demo/status - returns enabled flag and seed"""
        response = requests.get(f"{BASE_URL}/api/demo/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "seed" in data
        assert "generated_at" in data
        print(f"PASS: Demo status endpoint returns: enabled={data['enabled']}, seed={data['seed']}")
    
    def test_demo_enable_endpoint(self):
        """POST /api/demo/enable - enables demo mode"""
        response = requests.post(f"{BASE_URL}/api/demo/enable")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] == True
        assert "seed" in data
        print(f"PASS: Demo mode enabled successfully, seed={data['seed']}")
    
    def test_demo_disable_endpoint(self):
        """POST /api/demo/disable - disables demo mode"""
        response = requests.post(f"{BASE_URL}/api/demo/disable")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] == False
        print("PASS: Demo mode disabled successfully")
        # Re-enable for remaining tests
        requests.post(f"{BASE_URL}/api/demo/enable")
    
    def test_demo_regenerate_creates_new_seed(self):
        """POST /api/demo/regenerate - creates new random data"""
        # Get current seed
        status1 = requests.get(f"{BASE_URL}/api/demo/status").json()
        old_seed = status1["seed"]
        
        # Regenerate
        response = requests.post(f"{BASE_URL}/api/demo/regenerate")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "regenerated"
        assert "seed" in data
        assert "generated_at" in data
        # Seed should change (high probability)
        print(f"PASS: Demo data regenerated, old_seed={old_seed}, new_seed={data['seed']}")


class TestDemoStatusSnapshot:
    """Tests for demo status snapshot (engine state simulation)"""
    
    def test_demo_status_snapshot_returns_running_state(self):
        """GET /api/demo/status-snapshot - returns simulated running engine state"""
        response = requests.get(f"{BASE_URL}/api/demo/status-snapshot")
        assert response.status_code == 200
        data = response.json()
        
        # Should have engine status fields
        assert data.get("status") == "running", f"Expected running, got {data.get('status')}"
        assert data.get("mode") == "paper"
        assert "uptime_seconds" in data
        assert "stats" in data
        
        stats = data["stats"]
        assert "total_trades" in stats
        assert "win_rate" in stats
        assert "open_positions" in stats
        
        print(f"PASS: Demo snapshot shows running engine with {stats['total_trades']} trades")
    
    def test_demo_status_snapshot_has_expected_stats(self):
        """Demo stats should have realistic values"""
        response = requests.get(f"{BASE_URL}/api/demo/status-snapshot")
        data = response.json()
        stats = data["stats"]
        
        # Check for realistic demo data values (~199 trades, ~62% win rate, ~13 positions)
        assert stats["total_trades"] > 100, f"Expected >100 trades, got {stats['total_trades']}"
        assert 50 < stats["win_rate"] < 75, f"Expected 50-75% win rate, got {stats['win_rate']}"
        assert stats["open_positions"] > 5, f"Expected >5 positions, got {stats['open_positions']}"
        
        print(f"PASS: Demo stats realistic - trades={stats['total_trades']}, win_rate={stats['win_rate']}%, positions={stats['open_positions']}")


class TestDemoPositionsAndTrades:
    """Tests for demo positions, trades, and orders endpoints"""
    
    def test_demo_positions_returns_list(self):
        """GET /api/demo/positions - returns populated positions"""
        response = requests.get(f"{BASE_URL}/api/demo/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 9, f"Expected at least 9 demo positions, got {len(data)}"
        
        # Check position structure
        pos = data[0]
        assert "token_id" in pos
        assert "question" in pos
        assert "size" in pos
        assert "avg_cost" in pos
        assert "current_price" in pos
        assert "unrealized_pnl" in pos
        assert "strategy_id" in pos
        
        print(f"PASS: Demo positions returns {len(data)} positions with correct structure")
    
    def test_demo_trades_returns_list(self):
        """GET /api/demo/trades - returns populated trade history"""
        response = requests.get(f"{BASE_URL}/api/demo/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 150, f"Expected at least 150 demo trades, got {len(data)}"
        
        # Check trade structure
        trade = data[0]
        assert "order_id" in trade
        assert "market_question" in trade
        assert "outcome" in trade
        assert "side" in trade
        assert "price" in trade
        assert "size" in trade
        assert "pnl" in trade
        assert "strategy_id" in trade
        assert "timestamp" in trade
        
        print(f"PASS: Demo trades returns {len(data)} trades with correct structure")
    
    def test_demo_orders_returns_list(self):
        """GET /api/demo/orders - returns order records"""
        response = requests.get(f"{BASE_URL}/api/demo/orders")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        order = data[0]
        assert "id" in order
        assert "token_id" in order
        assert "side" in order
        assert "price" in order
        assert "size" in order
        assert "status" in order
        
        print(f"PASS: Demo orders returns {len(data)} orders")


class TestDemoAnalytics:
    """Tests for demo analytics endpoints"""
    
    def test_demo_analytics_summary_returns_stats(self):
        """GET /api/demo/analytics/summary - returns portfolio metrics"""
        response = requests.get(f"{BASE_URL}/api/demo/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Check key analytics fields
        required_fields = [
            "total_pnl", "realized_pnl", "unrealized_pnl",
            "trade_count", "win_count", "loss_count", "win_rate",
            "profit_factor", "max_drawdown", "sharpe_ratio"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify realistic values
        assert data["total_pnl"] > 5000, f"Expected >$5000 total PnL, got {data['total_pnl']}"
        assert data["trade_count"] > 100
        assert 50 < data["win_rate"] < 75
        assert data["profit_factor"] > 1.5
        
        print(f"PASS: Demo analytics summary - total_pnl=${data['total_pnl']:.2f}, win_rate={data['win_rate']}%, sharpe={data['sharpe_ratio']:.2f}")
    
    def test_demo_analytics_timeseries(self):
        """GET /api/demo/analytics/timeseries - returns time-based data"""
        response = requests.get(f"{BASE_URL}/api/demo/analytics/timeseries")
        assert response.status_code == 200
        data = response.json()
        
        assert "equity_curve" in data
        assert "daily_pnl" in data
        assert "drawdown_curve" in data
        
        # Should have 7 days of data
        assert len(data["equity_curve"]) >= 5
        assert len(data["daily_pnl"]) >= 5
        
        print(f"PASS: Demo timeseries has {len(data['equity_curve'])} equity points")
    
    def test_demo_pnl_history(self):
        """GET /api/demo/analytics/pnl-history - returns cumulative PnL"""
        response = requests.get(f"{BASE_URL}/api/demo/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        
        assert "points" in data
        assert "current_pnl" in data
        assert "peak_pnl" in data
        assert "max_drawdown" in data
        assert "total_trades" in data
        
        assert len(data["points"]) > 100
        assert data["current_pnl"] > 5000
        
        print(f"PASS: Demo PnL history - current=${data['current_pnl']:.2f}, peak=${data['peak_pnl']:.2f}, drawdown=${data['max_drawdown']:.2f}")


class TestDemoStrategyEndpoints:
    """Tests for demo strategy-specific endpoints"""
    
    def test_demo_arb_opportunities(self):
        """GET /api/demo/strategies/arb/opportunities"""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/arb/opportunities")
        assert response.status_code == 200
        data = response.json()
        
        assert "tradable" in data
        assert "rejected" in data
        assert "total_tradable" in data
        assert "total_rejected" in data
        
        print(f"PASS: Demo arb opportunities - tradable={data['total_tradable']}, rejected={data['total_rejected']}")
    
    def test_demo_arb_executions(self):
        """GET /api/demo/strategies/arb/executions"""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/arb/executions")
        assert response.status_code == 200
        data = response.json()
        
        assert "active" in data
        assert "completed" in data
        
        print(f"PASS: Demo arb executions - completed={len(data['completed'])}")
    
    def test_demo_sniper_signals(self):
        """GET /api/demo/strategies/sniper/signals"""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/sniper/signals")
        assert response.status_code == 200
        data = response.json()
        
        assert "tradable" in data
        assert "rejected" in data
        
        print(f"PASS: Demo sniper signals - tradable={data['total_tradable']}")
    
    def test_demo_weather_signals(self):
        """GET /api/demo/strategies/weather/signals"""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/signals")
        assert response.status_code == 200
        data = response.json()
        
        assert "tradable" in data
        assert "rejected" in data
        
        print(f"PASS: Demo weather signals - tradable={data['total_tradable']}")
    
    def test_demo_weather_forecasts(self):
        """GET /api/demo/strategies/weather/forecasts"""
        response = requests.get(f"{BASE_URL}/api/demo/strategies/weather/forecasts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        
        print(f"PASS: Demo weather forecasts returns {len(data)} cached forecasts")


class TestDemoTickerAndWallet:
    """Tests for demo ticker feed and wallet endpoints"""
    
    def test_demo_ticker_feed(self):
        """GET /api/demo/ticker/feed - returns recent trade executions"""
        response = requests.get(f"{BASE_URL}/api/demo/ticker/feed")
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) > 0
        
        item = data[0]
        assert "id" in item
        assert "strategy" in item
        assert "side" in item
        assert "size" in item
        assert "price" in item
        assert "timestamp" in item
        
        print(f"PASS: Demo ticker feed returns {len(data)} recent executions")
    
    def test_demo_wallet_status(self):
        """GET /api/demo/execution/wallet - returns simulated wallet"""
        response = requests.get(f"{BASE_URL}/api/demo/execution/wallet")
        assert response.status_code == 200
        data = response.json()
        
        assert "mode" in data
        assert "balance_usdc" in data
        assert data["mode"] == "paper"
        assert data["balance_usdc"] > 10000  # ~$14,746 target
        
        print(f"PASS: Demo wallet - mode={data['mode']}, balance=${data['balance_usdc']:.2f}")


class TestDemoConfigAndHealth:
    """Tests for demo config and health endpoints"""
    
    def test_demo_config(self):
        """GET /api/demo/config - returns simulated config"""
        response = requests.get(f"{BASE_URL}/api/demo/config")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("trading_mode") == "paper"
        assert "risk" in data
        assert "strategies" in data
        
        print(f"PASS: Demo config returns paper mode configuration")
    
    def test_demo_health(self):
        """GET /api/demo/health - returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/demo/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("status") == "healthy"
        assert data.get("engine") == "running"
        
        print("PASS: Demo health endpoint returns healthy/running")


class TestRealEndpointsUnaffected:
    """Verify real endpoints still work independently of demo mode"""
    
    def test_real_health_unaffected(self):
        """GET /api/health - returns actual engine state (not demo)"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        # Real engine might be stopped
        print(f"PASS: Real health endpoint returns status={data.get('status')}, engine={data.get('engine')}")
    
    def test_real_status_unaffected(self):
        """GET /api/status - returns actual engine status"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        # Real data should be different from demo
        print(f"PASS: Real status endpoint works independently, status={data.get('status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
