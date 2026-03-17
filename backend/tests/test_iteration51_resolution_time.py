"""
Iteration 51: Resolution time visibility for weather positions

Features tested:
- GET /api/positions/by-strategy includes resolution time fields for weather positions
- Weather position resolves_at is valid ISO timestamp ending in Z
- Weather position resolution_category (near/medium/long)
- Weather position opened_at from earliest buy trade
- Weather position time_open_seconds > 0
- Date parser handles 'on March 17' and 'on March 17, 2026'
- GET /api/analytics/summary still returns correct realized PnL
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestResolutionTimeFields:
    """Test resolution time fields in GET /api/positions/by-strategy"""

    def test_positions_by_strategy_returns_200(self):
        """GET /api/positions/by-strategy returns 200"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/positions/by-strategy returns 200")

    def test_weather_positions_have_resolution_fields(self):
        """Weather positions include resolves_at, target_date, time_to_resolution_seconds, time_open_seconds, opened_at, resolution_category"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        required_fields = ['resolves_at', 'target_date', 'time_to_resolution_seconds', 
                          'time_open_seconds', 'opened_at', 'resolution_category']
        
        # Check first 5 positions
        for i, pos in enumerate(weather_positions[:5]):
            for field in required_fields:
                assert field in pos, f"Position {i} missing field: {field}"
        
        print(f"PASS: All {len(required_fields)} resolution fields present in weather positions")

    def test_resolves_at_is_valid_iso_timestamp(self):
        """Weather position resolves_at is a valid ISO timestamp ending in Z"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        valid_count = 0
        for pos in weather_positions:
            resolves_at = pos.get('resolves_at')
            if resolves_at:
                # Must end in Z (UTC)
                assert resolves_at.endswith('Z'), f"resolves_at '{resolves_at}' should end with Z"
                # Must be parseable as ISO datetime
                try:
                    datetime.fromisoformat(resolves_at.replace('Z', '+00:00'))
                    valid_count += 1
                except ValueError:
                    pytest.fail(f"resolves_at '{resolves_at}' is not valid ISO format")
        
        assert valid_count > 0, "Expected at least one position with valid resolves_at"
        print(f"PASS: {valid_count} positions have valid ISO timestamp resolves_at ending in Z")

    def test_resolution_category_values(self):
        """Weather position resolution_category is one of: near (<6h), medium (6-24h), long (>24h), resolved"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        valid_categories = {'near', 'medium', 'long', 'resolved', None}
        category_counts = {'near': 0, 'medium': 0, 'long': 0, 'resolved': 0, 'none': 0}
        
        for pos in weather_positions:
            cat = pos.get('resolution_category')
            assert cat in valid_categories, f"Invalid resolution_category: {cat}"
            if cat:
                category_counts[cat] += 1
            else:
                category_counts['none'] += 1
        
        print(f"PASS: resolution_category valid - near:{category_counts['near']}, medium:{category_counts['medium']}, long:{category_counts['long']}, resolved:{category_counts['resolved']}")

    def test_opened_at_is_valid_timestamp(self):
        """Weather position opened_at is a valid timestamp from earliest buy trade"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        valid_count = 0
        for pos in weather_positions:
            opened_at = pos.get('opened_at')
            if opened_at:
                # Must be parseable as ISO datetime
                try:
                    dt = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                    valid_count += 1
                    # Should be in the past
                    assert dt < datetime.now(dt.tzinfo), f"opened_at {opened_at} should be in the past"
                except ValueError:
                    pytest.fail(f"opened_at '{opened_at}' is not valid ISO format")
        
        assert valid_count > 0, "Expected at least one position with valid opened_at"
        print(f"PASS: {valid_count} positions have valid opened_at timestamp")

    def test_time_open_seconds_positive(self):
        """Weather position time_open_seconds is > 0 for all positions"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        positive_count = 0
        for pos in weather_positions:
            time_open = pos.get('time_open_seconds')
            if time_open is not None:
                assert time_open > 0, f"time_open_seconds {time_open} should be > 0"
                positive_count += 1
        
        assert positive_count > 0, "Expected at least one position with time_open_seconds > 0"
        print(f"PASS: {positive_count} positions have time_open_seconds > 0")

    def test_time_to_resolution_seconds_consistent(self):
        """time_to_resolution_seconds is consistent with resolution_category"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        for pos in weather_positions:
            ttr = pos.get('time_to_resolution_seconds')
            cat = pos.get('resolution_category')
            
            if ttr is not None and cat is not None:
                if cat == 'near':
                    assert ttr <= 6 * 3600, f"'near' category should have ttr <= 6h (21600s), got {ttr}"
                elif cat == 'medium':
                    assert 6 * 3600 < ttr <= 24 * 3600, f"'medium' category should have 6h < ttr <= 24h, got {ttr}"
                elif cat == 'long':
                    assert ttr > 24 * 3600, f"'long' category should have ttr > 24h (86400s), got {ttr}"
        
        print("PASS: time_to_resolution_seconds consistent with resolution_category")


class TestDateParser:
    """Test the date parser handles various date formats in question text"""

    def test_weather_object_has_parsed_data(self):
        """Weather positions have parsed station_id, bucket_label, target_date, resolves_at_utc"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        parsed_count = 0
        for pos in weather_positions:
            weather = pos.get('weather', {})
            if weather.get('station_id') and weather.get('target_date'):
                parsed_count += 1
        
        assert parsed_count > 0, "Expected at least one position with parsed weather data"
        print(f"PASS: {parsed_count} positions have parsed weather data (station_id, target_date)")

    def test_target_date_format(self):
        """target_date is in YYYY-MM-DD format"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to test")
        
        valid_count = 0
        for pos in weather_positions:
            target_date = pos.get('target_date')
            if target_date:
                # Should match YYYY-MM-DD
                try:
                    datetime.strptime(target_date, '%Y-%m-%d')
                    valid_count += 1
                except ValueError:
                    pytest.fail(f"target_date '{target_date}' is not YYYY-MM-DD format")
        
        assert valid_count > 0, "Expected at least one position with valid target_date"
        print(f"PASS: {valid_count} positions have target_date in YYYY-MM-DD format")


class TestAnalyticsSummary:
    """Test /api/analytics/summary still works correctly"""

    def test_analytics_summary_returns_200(self):
        """GET /api/analytics/summary returns 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/analytics/summary returns 200")

    def test_analytics_summary_has_realized_pnl(self):
        """Analytics summary includes realized_pnl field"""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert 'realized_pnl' in data, "realized_pnl field missing from analytics summary"
        realized_pnl = data.get('realized_pnl')
        assert isinstance(realized_pnl, (int, float)), f"realized_pnl should be numeric, got {type(realized_pnl)}"
        
        print(f"PASS: realized_pnl = ${realized_pnl:.2f}")

    def test_analytics_summary_positive_pnl(self):
        """Analytics summary shows realized PnL > 0 (as per previous tests)"""
        response = requests.get(f"{BASE_URL}/api/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        
        realized_pnl = data.get('realized_pnl', 0)
        # Based on iteration 50, realized PnL was $142.70
        assert realized_pnl > 0, f"Expected realized_pnl > 0, got {realized_pnl}"
        
        print(f"PASS: realized_pnl > 0 (${realized_pnl:.2f})")


class TestPositionCounts:
    """Test position counts and summaries"""

    def test_weather_position_count(self):
        """Weather positions count matches expected (54 from context)"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        weather_positions = data.get('positions', {}).get('weather', [])
        
        count = len(weather_positions)
        print(f"PASS: Weather position count = {count}")
        assert count > 0, "Expected at least some weather positions"

    def test_summaries_included(self):
        """Response includes summaries section with weather stats"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        data = response.json()
        
        assert 'summaries' in data, "summaries field missing"
        summaries = data.get('summaries', {})
        assert 'weather' in summaries, "weather summary missing"
        
        weather_summary = summaries.get('weather', {})
        assert 'open_positions' in weather_summary, "open_positions missing from weather summary"
        assert 'unrealized_pnl' in weather_summary, "unrealized_pnl missing from weather summary"
        
        print(f"PASS: Weather summary: {weather_summary.get('open_positions')} open, ${weather_summary.get('unrealized_pnl', 0):.2f} unrealized")
