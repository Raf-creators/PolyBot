"""
Test iteration 44 features: Strategy Attribution Analytics, Controls endpoint,
and Strategy Comparison UI elements.

Tests cover:
1. /api/analytics/strategy-attribution - Deep per-strategy analytics
2. /api/controls - Live-readiness controls (kill switch, limits, mode)
3. /api/status - All strategies show status='active'
4. /api/analytics/strategy-tracker - position_slots with per-strategy headroom
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestStrategyAttributionEndpoint:
    """Test /api/analytics/strategy-attribution endpoint"""
    
    def test_endpoint_returns_200(self):
        """Endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        assert response.status_code == 200
        print(f"PASS: /api/analytics/strategy-attribution returns 200")
    
    def test_returns_four_buckets(self):
        """Should return crypto, weather, arb, resolver buckets"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        data = response.json()
        
        expected_buckets = ['crypto', 'weather', 'arb', 'resolver']
        for bucket in expected_buckets:
            assert bucket in data, f"Missing bucket: {bucket}"
        print(f"PASS: All 4 strategy buckets present (crypto, weather, arb, resolver)")
    
    def test_each_bucket_has_required_fields(self):
        """Each bucket should have all required analytics fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        data = response.json()
        
        required_fields = [
            'realized_pnl', 'unrealized_pnl', 'total_pnl', 
            'trade_count', 'wins', 'losses', 'win_rate',
            'avg_pnl_per_trade', 'avg_hold_hours', 'pnl_per_hour',
            'capital_allocated', 'open_positions', 'avg_trade_size',
            'best_trade', 'worst_trade'
        ]
        
        for bucket in ['crypto', 'weather', 'arb', 'resolver']:
            bucket_data = data.get(bucket, {})
            for field in required_fields:
                assert field in bucket_data, f"Bucket '{bucket}' missing field: {field}"
        
        print(f"PASS: All buckets have all required fields ({len(required_fields)} fields each)")
    
    def test_crypto_has_trades_and_pnl(self):
        """Crypto bucket should have trade_count > 0 and realized_pnl > 0"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        data = response.json()
        
        crypto = data.get('crypto', {})
        assert crypto.get('trade_count', 0) > 0, "Crypto should have trades"
        assert crypto.get('realized_pnl', 0) > 0, "Crypto should have positive realized PnL"
        
        print(f"PASS: Crypto has {crypto['trade_count']} trades, ${crypto['realized_pnl']:.2f} realized PnL")
    
    def test_arb_has_positive_win_rate(self):
        """Arb bucket should have win_rate > 0"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        data = response.json()
        
        arb = data.get('arb', {})
        assert arb.get('win_rate', 0) > 0, "Arb should have positive win rate"
        assert arb.get('wins', 0) > 0, "Arb should have winning trades"
        
        print(f"PASS: Arb has {arb['win_rate']}% win rate with {arb['wins']} wins")
    
    def test_arb_is_top_pnl_strategy(self):
        """Arb should have the highest total_pnl (should show TOP badge)"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        data = response.json()
        
        pnl_values = {bucket: data.get(bucket, {}).get('total_pnl', 0) 
                      for bucket in ['crypto', 'weather', 'arb', 'resolver']}
        
        max_bucket = max(pnl_values, key=pnl_values.get)
        assert max_bucket == 'arb', f"Expected 'arb' to be top PnL but got '{max_bucket}'"
        
        print(f"PASS: Arb is top PnL strategy with ${pnl_values['arb']:.2f}")
        for bucket, pnl in pnl_values.items():
            print(f"  {bucket}: ${pnl:.2f}")


class TestControlsEndpoint:
    """Test /api/controls endpoint"""
    
    def test_endpoint_returns_200(self):
        """Endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/controls")
        assert response.status_code == 200
        print(f"PASS: /api/controls returns 200")
    
    def test_returns_paper_mode(self):
        """Should return mode='paper'"""
        response = requests.get(f"{BASE_URL}/api/controls")
        data = response.json()
        
        assert data.get('mode') == 'paper', f"Expected mode='paper', got '{data.get('mode')}'"
        print(f"PASS: Mode is 'paper'")
    
    def test_kill_switch_inactive(self):
        """Kill switch should be inactive"""
        response = requests.get(f"{BASE_URL}/api/controls")
        data = response.json()
        
        assert data.get('kill_switch_active') == False, "Kill switch should be inactive"
        print(f"PASS: Kill switch is inactive")
    
    def test_has_limit_fields(self):
        """Should have max_daily_loss, max_market_exposure, max_order_size, max_position_size"""
        response = requests.get(f"{BASE_URL}/api/controls")
        data = response.json()
        
        required_fields = ['max_daily_loss', 'max_market_exposure', 'max_order_size', 'max_position_size']
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
            assert data[field] is not None, f"Field '{field}' is None"
        
        print(f"PASS: All limit fields present")
        print(f"  max_daily_loss: ${data['max_daily_loss']}")
        print(f"  max_market_exposure: ${data['max_market_exposure']}")
        print(f"  max_order_size: ${data['max_order_size']}")
        print(f"  max_position_size: ${data['max_position_size']}")
    
    def test_has_daily_pnl_and_exposure(self):
        """Should have daily_pnl and total_exposure"""
        response = requests.get(f"{BASE_URL}/api/controls")
        data = response.json()
        
        assert 'daily_pnl' in data, "Missing daily_pnl"
        assert 'total_exposure' in data, "Missing total_exposure"
        
        print(f"PASS: daily_pnl=${data['daily_pnl']:.2f}, total_exposure=${data['total_exposure']:.2f}")
    
    def test_limits_status_has_remaining_values(self):
        """limits_status should have daily_loss_remaining and exposure_remaining as positive numbers"""
        response = requests.get(f"{BASE_URL}/api/controls")
        data = response.json()
        
        limits_status = data.get('limits_status', {})
        
        assert 'daily_loss_remaining' in limits_status, "Missing daily_loss_remaining"
        assert 'exposure_remaining' in limits_status, "Missing exposure_remaining"
        
        # These should be positive (still have headroom)
        assert limits_status['daily_loss_remaining'] >= 0, "daily_loss_remaining should be >= 0"
        assert limits_status['exposure_remaining'] >= 0, "exposure_remaining should be >= 0"
        
        print(f"PASS: limits_status has positive remaining values")
        print(f"  daily_loss_remaining: ${limits_status['daily_loss_remaining']:.2f}")
        print(f"  exposure_remaining: ${limits_status['exposure_remaining']:.2f}")


class TestStatusEndpoint:
    """Test /api/status endpoint for strategy status"""
    
    def test_all_strategies_active(self):
        """All 3 strategies should show status='active' (NOT 'stopped')"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        
        data = response.json()
        strategies = data.get('strategies', [])
        
        strategy_ids = ['arb_scanner', 'crypto_sniper', 'weather_trader']
        
        for sid in strategy_ids:
            strategy = next((s for s in strategies if s.get('strategy_id') == sid), None)
            assert strategy is not None, f"Strategy '{sid}' not found"
            assert strategy.get('status') == 'active', f"Strategy '{sid}' should be 'active', got '{strategy.get('status')}'"
        
        print(f"PASS: All 3 strategies show status='active'")
        for strategy in strategies:
            print(f"  {strategy['strategy_id']}: status={strategy.get('status')}, enabled={strategy.get('enabled')}")


class TestStrategyTrackerEndpoint:
    """Test /api/analytics/strategy-tracker for position_slots"""
    
    def test_position_slots_has_per_strategy_headroom(self):
        """position_slots should return per-strategy headroom (weather, crypto, arb, global)"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        assert response.status_code == 200
        
        data = response.json()
        slots = data.get('position_slots', {})
        headroom = slots.get('headroom', {})
        
        expected_keys = ['weather', 'crypto', 'arb', 'global']
        for key in expected_keys:
            assert key in headroom, f"Headroom missing key: {key}"
        
        print(f"PASS: position_slots has per-strategy headroom")
        for key in expected_keys:
            print(f"  {key}_headroom: {headroom.get(key)}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
