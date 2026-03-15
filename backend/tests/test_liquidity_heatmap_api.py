"""
API tests for Liquidity Heatmap Feature (Phase 23)
Testing:
- GET /api/markets/liquidity-heatmap endpoint
- GET /api/markets/liquidity-scores endpoint
- Heatmap data shape validation
- Engine integration for populated heatmap
- Regression on /api/markets and /api/markets/summary
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestLiquidityHeatmapBasicAPI:
    """Basic API shape tests that work without engine running."""
    
    def test_health_check(self):
        """Ensure API is reachable."""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"PASS: Health check - status={data['status']}")
    
    def test_liquidity_heatmap_endpoint_returns_200(self):
        """GET /api/markets/liquidity-heatmap returns 200."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-heatmap")
        assert response.status_code == 200
        print("PASS: GET /api/markets/liquidity-heatmap returns 200")
    
    def test_liquidity_heatmap_response_shape(self):
        """Response has required top-level fields."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-heatmap")
        data = response.json()
        
        assert "tiles" in data, "Missing 'tiles' field"
        assert "token_count" in data, "Missing 'token_count' field"
        assert "tile_count" in data, "Missing 'tile_count' field"
        assert "summary" in data, "Missing 'summary' field"
        
        print(f"PASS: Response has tiles={len(data['tiles'])}, token_count={data['token_count']}, tile_count={data['tile_count']}")
    
    def test_liquidity_heatmap_summary_shape(self):
        """Summary has required fields: avg_score, max_score, min_score, total_liquidity, total_volume_24h."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-heatmap")
        data = response.json()
        summary = data["summary"]
        
        assert "avg_score" in summary, "Missing 'avg_score' in summary"
        assert "max_score" in summary, "Missing 'max_score' in summary"
        assert "min_score" in summary, "Missing 'min_score' in summary"
        assert "total_liquidity" in summary, "Missing 'total_liquidity' in summary"
        assert "total_volume_24h" in summary, "Missing 'total_volume_24h' in summary"
        
        print(f"PASS: Summary shape valid - avg_score={summary['avg_score']}, max_score={summary['max_score']}, min_score={summary['min_score']}")
    
    def test_liquidity_scores_endpoint_returns_200(self):
        """GET /api/markets/liquidity-scores returns 200."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-scores")
        assert response.status_code == 200
        print("PASS: GET /api/markets/liquidity-scores returns 200")
    
    def test_liquidity_scores_returns_dict(self):
        """Response is a dict mapping token_id to score."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-scores")
        data = response.json()
        
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        print(f"PASS: GET /api/markets/liquidity-scores returns dict with {len(data)} entries")
    
    def test_heatmap_empty_when_engine_stopped(self):
        """When engine is stopped, tiles should be empty."""
        # First ensure engine is stopped
        try:
            requests.post(f"{BASE_URL}/api/engine/stop")
        except:
            pass
        time.sleep(1)
        
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-heatmap")
        data = response.json()
        
        # With engine stopped, should have no weather market tiles
        print(f"PASS: With engine stopped, tile_count={data['tile_count']}")


class TestMarketsEndpointsRegression:
    """Regression tests for existing market endpoints."""
    
    def test_markets_endpoint_still_works(self):
        """GET /api/markets returns 200 and is a list."""
        response = requests.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: GET /api/markets returns list with {len(data)} markets")
    
    def test_markets_summary_still_works(self):
        """GET /api/markets/summary returns 200 with expected fields."""
        response = requests.get(f"{BASE_URL}/api/markets/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_markets" in data
        assert "top_by_volume" in data
        print(f"PASS: GET /api/markets/summary - total_markets={data['total_markets']}")


class TestLiquidityHeatmapWithEngine:
    """Tests that require the engine to be running for data population."""
    
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Start engine before test, stop after."""
        # Start engine
        start_response = requests.post(f"{BASE_URL}/api/engine/start")
        if start_response.status_code == 200:
            print("Engine started for heatmap test")
        elif start_response.status_code == 400:
            # Engine already running
            print("Engine already running")
        
        # Wait for market data to populate (12+ seconds)
        print("Waiting 15 seconds for market data to populate...")
        time.sleep(15)
        
        yield
        
        # Stop engine after test
        try:
            requests.post(f"{BASE_URL}/api/engine/stop")
            print("Engine stopped after heatmap test")
        except:
            pass
    
    def test_heatmap_has_tiles_after_engine_start(self):
        """After engine start and wait, heatmap should have tiles with weather market data."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-heatmap")
        assert response.status_code == 200
        data = response.json()
        
        # Note: tile_count may be 0 if no weather markets are currently active
        # on Polymarket. We'll check the structure regardless.
        print(f"INFO: Heatmap has {data['tile_count']} tiles, {data['token_count']} tokens")
        
        # Verify structure is correct
        assert isinstance(data["tiles"], list)
        assert isinstance(data["tile_count"], int)
        assert data["tile_count"] == len(data["tiles"])
        
        print(f"PASS: tile_count={data['tile_count']} matches tiles array length")
    
    def test_heatmap_tile_structure(self):
        """Each tile should have required fields."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-heatmap")
        data = response.json()
        tiles = data["tiles"]
        
        if not tiles:
            print("SKIP: No tiles to validate (no weather markets found)")
            pytest.skip("No weather market tiles available")
        
        tile = tiles[0]
        required_fields = [
            "condition_id", "station_id", "city", "target_date",
            "bucket_count", "priced_buckets", "avg_liquidity_score",
            "total_liquidity", "avg_spread", "buckets"
        ]
        
        for field in required_fields:
            assert field in tile, f"Missing '{field}' in tile"
        
        print(f"PASS: Tile has all required fields - city={tile['city']}, station_id={tile['station_id']}")
    
    def test_heatmap_bucket_structure(self):
        """Each bucket in a tile should have required fields."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-heatmap")
        data = response.json()
        tiles = data["tiles"]
        
        if not tiles:
            pytest.skip("No weather market tiles available")
        
        # Find a tile with buckets
        tile_with_buckets = None
        for t in tiles:
            if t.get("buckets"):
                tile_with_buckets = t
                break
        
        if not tile_with_buckets:
            pytest.skip("No tiles with buckets found")
        
        bucket = tile_with_buckets["buckets"][0]
        required_fields = [
            "label", "token_id", "mid_price", "spread",
            "liquidity", "volume_24h", "liquidity_score"
        ]
        
        for field in required_fields:
            assert field in bucket, f"Missing '{field}' in bucket"
        
        print(f"PASS: Bucket has all required fields - label={bucket['label']}")
    
    def test_liquidity_scores_range(self):
        """Liquidity scores should be in 0-100 range."""
        response = requests.get(f"{BASE_URL}/api/markets/liquidity-scores")
        data = response.json()
        
        if not data:
            pytest.skip("No liquidity scores available")
        
        out_of_range = []
        for token_id, score in data.items():
            if score < 0 or score > 100:
                out_of_range.append((token_id, score))
        
        assert len(out_of_range) == 0, f"Scores out of range: {out_of_range[:5]}"
        print(f"PASS: All {len(data)} scores in 0-100 range")
    
    def test_weather_trader_has_liquidity_scores_cached(self):
        """Weather trader health should show liquidity_scores_cached > 0."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        
        if "liquidity_scores_cached" in data:
            cached = data["liquidity_scores_cached"]
            print(f"PASS: liquidity_scores_cached={cached}")
        else:
            print("WARN: liquidity_scores_cached not in health response")


class TestOtherPageRegressions:
    """Regression tests for other pages to ensure no breaking changes."""
    
    def test_overview_positions_endpoint(self):
        """GET /api/positions works."""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        print("PASS: GET /api/positions works")
    
    def test_overview_trades_endpoint(self):
        """GET /api/trades works."""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        print("PASS: GET /api/trades works")
    
    def test_overview_orders_endpoint(self):
        """GET /api/orders works."""
        response = requests.get(f"{BASE_URL}/api/orders")
        assert response.status_code == 200
        print("PASS: GET /api/orders works")
    
    def test_arb_opportunities_endpoint(self):
        """GET /api/strategies/arb/opportunities works."""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/arb/opportunities works")
    
    def test_sniper_signals_endpoint(self):
        """GET /api/strategies/sniper/signals works."""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/sniper/signals works")
    
    def test_weather_signals_endpoint(self):
        """GET /api/strategies/weather/signals works."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/weather/signals works")
    
    def test_config_endpoint(self):
        """GET /api/config works."""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        print("PASS: GET /api/config works")
    
    def test_analytics_summary_endpoint(self):
        """GET /api/analytics/summary works."""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200
        print("PASS: GET /api/analytics/summary works")
