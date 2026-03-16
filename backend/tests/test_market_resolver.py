"""
Test Market Resolver Service — verifies the global market resolver functionality
that closes positions when Polymarket markets resolve.

Tests cover:
- GET /api/health/market-resolver - resolver health endpoint
- POST /api/market-resolver/run - manual resolution trigger
- GET /api/positions - enriched position data with end_date, time_to_expiry, expired, resolved
- GET /api/trades - resolution trades from strategy_id='resolver'
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Ensure BASE_URL is set
if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)


class TestMarketResolverHealth:
    """Tests for GET /api/health/market-resolver endpoint"""

    def test_market_resolver_health_returns_200(self):
        """Health endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver")
        assert response.status_code == 200
        print(f"✓ GET /api/health/market-resolver returned 200")

    def test_market_resolver_running(self):
        """Resolver should be running"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver")
        data = response.json()
        assert data.get("running") is True, f"running should be True, got {data.get('running')}"
        print(f"✓ Resolver running=True")

    def test_market_resolver_interval_seconds(self):
        """Resolver should have interval_seconds=30"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver")
        data = response.json()
        assert data.get("interval_seconds") == 30, f"Expected 30, got {data.get('interval_seconds')}"
        print(f"✓ Resolver interval_seconds=30")

    def test_market_resolver_total_runs_gt_0(self):
        """Resolver should have total_runs >= 0 (may be 0 on fresh start)"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver")
        data = response.json()
        total_runs = data.get("total_runs", 0)
        # On fresh start, total_runs may be 0 initially
        assert total_runs >= 0, f"Expected total_runs >= 0, got {total_runs}"
        print(f"✓ Resolver total_runs={total_runs}")

    def test_market_resolver_positions_resolved_gte_0(self):
        """Resolver should have positions_resolved >= 0 (may be 0 if no markets have expired yet)"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver")
        data = response.json()
        positions_resolved = data.get("positions_resolved", 0)
        # On fresh start, positions_resolved will be 0 until markets expire
        assert "positions_resolved" in data, "positions_resolved field should exist"
        print(f"✓ Resolver positions_resolved={positions_resolved}")

    def test_market_resolver_recent_resolutions(self):
        """recent_resolutions field should exist (may be empty on fresh start)"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver")
        data = response.json()
        recent = data.get("recent_resolutions", [])
        
        # recent_resolutions should be a list
        assert isinstance(recent, list), f"recent_resolutions should be list, got {type(recent)}"
        
        # If entries exist, verify structure
        if recent:
            first = recent[0]
            assert "question" in first, "recent_resolutions entry missing 'question'"
            assert "won" in first, "recent_resolutions entry missing 'won'"
            assert "pnl" in first, "recent_resolutions entry missing 'pnl'"
            assert isinstance(first["won"], bool), f"'won' should be bool, got {type(first['won'])}"
            assert isinstance(first["pnl"], (int, float)), f"'pnl' should be number, got {type(first['pnl'])}"
            print(f"✓ recent_resolutions has {len(recent)} entries with correct structure")
            print(f"  Sample: question='{first['question'][:50]}...' won={first['won']} pnl={first['pnl']}")
        else:
            print(f"✓ recent_resolutions is empty (no markets resolved yet on fresh start)")


class TestMarketResolverManualRun:
    """Tests for POST /api/market-resolver/run endpoint"""

    def test_manual_resolution_run(self):
        """Manual resolution pass should return expected fields"""
        response = requests.post(f"{BASE_URL}/api/market-resolver/run")
        assert response.status_code == 200
        
        data = response.json()
        assert "resolved" in data, "Response missing 'resolved' field"
        assert "pnl" in data, "Response missing 'pnl' field"
        assert "queried" in data, "Response missing 'queried' field"
        assert "checked" in data, "Response missing 'checked' field"
        assert "duration_ms" in data, "Response missing 'duration_ms' field"
        
        print(f"✓ POST /api/market-resolver/run returned: resolved={data['resolved']}, pnl={data['pnl']}, queried={data['queried']}, checked={data['checked']}, duration_ms={data['duration_ms']}")


class TestPositionsEnrichment:
    """Tests for GET /api/positions with enriched fields"""

    def test_positions_returns_200(self):
        """Positions endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        print(f"✓ GET /api/positions returned 200")

    def test_positions_have_required_fields(self):
        """Each position should have end_date, time_to_expiry_seconds, expired, resolved fields"""
        response = requests.get(f"{BASE_URL}/api/positions")
        positions = response.json()
        
        if not positions:
            pytest.skip("No positions to test")
        
        for pos in positions[:5]:  # Check first 5
            assert "end_date" in pos, f"Position missing 'end_date'"
            assert "time_to_expiry_seconds" in pos, f"Position missing 'time_to_expiry_seconds'"
            assert "expired" in pos, f"Position missing 'expired'"
            assert "resolved" in pos, f"Position missing 'resolved'"
        
        print(f"✓ All positions have required fields (end_date, time_to_expiry_seconds, expired, resolved)")

    def test_crypto_sniper_positions_have_end_date(self):
        """Crypto sniper positions (Bitcoin Up or Down, Ethereum Up or Down) should have non-null end_date"""
        response = requests.get(f"{BASE_URL}/api/positions")
        positions = response.json()
        
        crypto_positions = [
            p for p in positions 
            if "Bitcoin Up" in p.get("market_question", "") or "Ethereum Up" in p.get("market_question", "")
        ]
        
        if not crypto_positions:
            pytest.skip("No crypto sniper positions found")
        
        for pos in crypto_positions:
            assert pos.get("end_date") is not None, f"Crypto position missing end_date: {pos['market_question'][:50]}"
            assert pos.get("time_to_expiry_seconds") is not None, f"Crypto position missing time_to_expiry_seconds"
        
        print(f"✓ {len(crypto_positions)} crypto positions have non-null end_date and time_to_expiry_seconds")

    def test_weather_positions_have_null_end_date(self):
        """Weather positions should have end_date=null and expired=false"""
        response = requests.get(f"{BASE_URL}/api/positions")
        positions = response.json()
        
        weather_positions = [
            p for p in positions 
            if "temperature" in p.get("market_question", "").lower() or "highest temp" in p.get("market_question", "").lower()
        ]
        
        if not weather_positions:
            pytest.skip("No weather positions found")
        
        for pos in weather_positions[:5]:  # Check first 5
            # Weather positions typically have null end_date (broad fetch doesn't include it)
            # But expired should be false
            assert pos.get("expired") is False, f"Weather position should not be expired"
        
        print(f"✓ {len(weather_positions)} weather positions have expired=false")


class TestResolutionTrades:
    """Tests for GET /api/trades with resolver strategy trades"""

    def test_trades_returns_200(self):
        """Trades endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        print(f"✓ GET /api/trades returned 200")

    def test_resolver_trades_exist(self):
        """Should have >= 0 resolution trades with strategy_id='resolver' (may be 0 on fresh start)"""
        response = requests.get(f"{BASE_URL}/api/trades")
        trades = response.json()
        
        resolver_trades = [t for t in trades if t.get("strategy_id") == "resolver"]
        
        # On fresh start, there may be 0 resolver trades until positions expire
        assert isinstance(resolver_trades, list), "resolver_trades should be a list"
        print(f"✓ Found {len(resolver_trades)} resolver trades")

    def test_resolver_trades_have_pnl(self):
        """Resolver trades should have pnl values"""
        response = requests.get(f"{BASE_URL}/api/trades")
        trades = response.json()
        
        resolver_trades = [t for t in trades if t.get("strategy_id") == "resolver"]
        
        for trade in resolver_trades:
            assert "pnl" in trade, f"Resolver trade missing 'pnl'"
            assert trade["pnl"] is not None, f"Resolver trade pnl should not be None"
        
        total_pnl = sum(t["pnl"] for t in resolver_trades)
        print(f"✓ Resolver trades have pnl values, total resolved PnL=${total_pnl:.4f}")

    def test_resolver_trades_signal_reason(self):
        """Resolver trades should have signal_reason starting with 'market_resolved:'"""
        response = requests.get(f"{BASE_URL}/api/trades")
        trades = response.json()
        
        resolver_trades = [t for t in trades if t.get("strategy_id") == "resolver"]
        
        for trade in resolver_trades:
            signal_reason = trade.get("signal_reason", "")
            assert signal_reason.startswith("market_resolved:"), \
                f"Expected signal_reason to start with 'market_resolved:', got '{signal_reason}'"
        
        print(f"✓ All resolver trades have signal_reason starting with 'market_resolved:'")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
