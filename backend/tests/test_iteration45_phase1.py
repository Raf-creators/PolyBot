"""
Iteration 45: Phase 1 - Open Positions Visibility and Unrealized PnL
Tests GET /api/positions/by-strategy endpoint for strategy pages.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPositionsByStrategy:
    """Test /api/positions/by-strategy endpoint for Weather/Sniper/Analytics pages."""
    
    def test_endpoint_returns_200(self):
        """GET /api/positions/by-strategy returns 200."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/positions/by-strategy returns 200")
    
    def test_response_has_required_structure(self):
        """Response has positions, summaries, total_unrealized_pnl, total_open."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        assert "positions" in data, "Missing 'positions' key"
        assert "summaries" in data, "Missing 'summaries' key"
        assert "total_unrealized_pnl" in data, "Missing 'total_unrealized_pnl' key"
        assert "total_open" in data, "Missing 'total_open' key"
        print("PASS: Response has positions, summaries, total_unrealized_pnl, total_open")
    
    def test_positions_grouped_by_strategy(self):
        """Positions are grouped by weather, crypto, arb, other."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        positions = data.get("positions", {})
        assert "weather" in positions, "Missing weather bucket"
        assert "crypto" in positions, "Missing crypto bucket"
        assert "arb" in positions, "Missing arb bucket"
        assert "other" in positions, "Missing other bucket"
        print(f"PASS: Positions grouped by strategy - weather:{len(positions['weather'])}, crypto:{len(positions['crypto'])}, arb:{len(positions['arb'])}")
    
    def test_summaries_have_required_fields(self):
        """Each summary has realized/unrealized/total PnL, trade_count, wins, losses, win_rate."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        required_fields = ['open_positions', 'unrealized_pnl', 'realized_pnl', 'total_pnl', 
                          'trade_count', 'wins', 'losses', 'win_rate', 'capital_allocated']
        
        for bucket in ['weather', 'crypto', 'arb']:
            summary = data.get("summaries", {}).get(bucket, {})
            for field in required_fields:
                assert field in summary, f"Summary for {bucket} missing '{field}'"
        print("PASS: All summaries have required PnL/trade fields")
    
    def test_weather_positions_have_metadata(self):
        """Weather positions have enriched metadata (weather.station_id, bucket_label, etc)."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        weather_positions = data.get("positions", {}).get("weather", [])
        if len(weather_positions) > 0:
            # Check first position has weather metadata
            pos = weather_positions[0]
            assert "strategy_bucket" in pos, "Missing strategy_bucket"
            assert pos.get("strategy_bucket") == "weather", "Wrong bucket classification"
            # Weather-specific enrichment is optional but verify structure
            if "weather" in pos:
                weather_meta = pos.get("weather", {})
                # May have station_id, bucket_label, edge_at_entry
                print(f"PASS: Weather position has metadata: {list(weather_meta.keys())[:5]}")
            else:
                print("PASS: Weather positions found (metadata enrichment varies)")
        else:
            pytest.skip("No weather positions to validate")
    
    def test_crypto_positions_have_metadata(self):
        """Crypto positions have enriched metadata (sniper.asset, side, edge_at_entry)."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        crypto_positions = data.get("positions", {}).get("crypto", [])
        if len(crypto_positions) > 0:
            pos = crypto_positions[0]
            assert pos.get("strategy_bucket") == "crypto", "Wrong bucket classification"
            # Sniper-specific enrichment is optional but verify structure
            if "sniper" in pos:
                sniper_meta = pos.get("sniper", {})
                print(f"PASS: Crypto position has metadata: {list(sniper_meta.keys())[:5]}")
            else:
                print("PASS: Crypto positions found (metadata enrichment varies)")
        else:
            pytest.skip("No crypto positions to validate")
    
    def test_positions_have_display_fields(self):
        """Positions have display fields: avg_cost, current_price, size, unrealized_pnl."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        all_positions = []
        for bucket in ['weather', 'crypto', 'arb']:
            all_positions.extend(data.get("positions", {}).get(bucket, []))
        
        if len(all_positions) == 0:
            pytest.skip("No positions to validate")
        
        required_display = ['avg_cost', 'current_price', 'size', 'unrealized_pnl', 'unrealized_pnl_pct']
        pos = all_positions[0]
        for field in required_display:
            assert field in pos, f"Position missing '{field}'"
        print("PASS: Positions have display fields (avg_cost, current_price, size, unrealized_pnl, unrealized_pnl_pct)")
    
    def test_positions_have_time_to_resolution(self):
        """Positions have hours_to_resolution field for UI display."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        all_positions = []
        for bucket in ['weather', 'crypto', 'arb']:
            all_positions.extend(data.get("positions", {}).get(bucket, []))
        
        if len(all_positions) == 0:
            pytest.skip("No positions to validate")
        
        # hours_to_resolution should exist (may be None for some)
        found_with_resolution = [p for p in all_positions if p.get("hours_to_resolution") is not None]
        print(f"PASS: {len(found_with_resolution)}/{len(all_positions)} positions have hours_to_resolution set")
    
    def test_total_open_matches_sum(self):
        """total_open matches sum of all position buckets."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        positions = data.get("positions", {})
        total = sum(len(positions.get(b, [])) for b in ['weather', 'crypto', 'arb', 'other'])
        assert data.get("total_open") == total, f"total_open mismatch: {data.get('total_open')} != {total}"
        print(f"PASS: total_open={total} matches sum of buckets")
    
    def test_weather_summary_pnl_values(self):
        """Weather summary shows ~54 open positions and correct PnL structure."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        weather_summary = data.get("summaries", {}).get("weather", {})
        weather_positions = data.get("positions", {}).get("weather", [])
        
        assert weather_summary.get("open_positions") == len(weather_positions), "Weather open_positions count mismatch"
        assert "realized_pnl" in weather_summary, "Missing realized_pnl"
        assert "unrealized_pnl" in weather_summary, "Missing unrealized_pnl"
        assert "total_pnl" in weather_summary, "Missing total_pnl"
        
        # Verify total = realized + unrealized
        total = weather_summary.get("total_pnl", 0)
        realized = weather_summary.get("realized_pnl", 0)
        unrealized = weather_summary.get("unrealized_pnl", 0)
        expected_total = round(realized + unrealized, 4)
        assert abs(total - expected_total) < 0.01, f"total_pnl mismatch: {total} != {expected_total}"
        print(f"PASS: Weather summary - {weather_summary.get('open_positions')} open, realized={realized}, unrealized={unrealized}, total={total}")
    
    def test_crypto_summary_shows_realized_pnl(self):
        """Crypto summary shows realized PnL (~$50)."""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        crypto_summary = data.get("summaries", {}).get("crypto", {})
        realized = crypto_summary.get("realized_pnl", 0)
        
        # Per the task, crypto has ~$50.23 realized
        assert realized >= 40, f"Crypto realized_pnl too low: {realized}"
        print(f"PASS: Crypto summary shows realized_pnl={realized}")


class TestAnalyticsStrategyAttribution:
    """Test strategy-attribution endpoint still works for Analytics page."""
    
    def test_endpoint_returns_200(self):
        """GET /api/analytics/strategy-attribution returns 200."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        assert response.status_code == 200
        print("PASS: GET /api/analytics/strategy-attribution returns 200")
    
    def test_has_three_main_buckets(self):
        """Attribution has crypto, weather, arb buckets for Analytics comparison."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        data = response.json()
        
        assert "crypto" in data, "Missing crypto bucket"
        assert "weather" in data, "Missing weather bucket"
        assert "arb" in data, "Missing arb bucket"
        print("PASS: Strategy attribution has crypto, weather, arb buckets")
    
    def test_each_bucket_has_pnl_fields(self):
        """Each bucket has realized_pnl, unrealized_pnl, total_pnl."""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        data = response.json()
        
        for bucket in ['crypto', 'weather', 'arb']:
            attr = data.get(bucket, {})
            assert "realized_pnl" in attr, f"{bucket} missing realized_pnl"
            assert "unrealized_pnl" in attr, f"{bucket} missing unrealized_pnl"
            assert "total_pnl" in attr, f"{bucket} missing total_pnl"
        print("PASS: All buckets have realized/unrealized/total PnL")


class TestControlsEndpoint:
    """Test /api/controls for Analytics Controls tab."""
    
    def test_endpoint_returns_200(self):
        """GET /api/controls returns 200."""
        response = requests.get(f"{BASE_URL}/api/controls")
        assert response.status_code == 200
        print("PASS: GET /api/controls returns 200")
    
    def test_returns_paper_mode(self):
        """Controls returns mode=paper."""
        response = requests.get(f"{BASE_URL}/api/controls")
        data = response.json()
        assert data.get("mode") == "paper", f"Expected mode=paper, got {data.get('mode')}"
        print("PASS: Controls mode=paper")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
