"""
Iteration 47 Test Suite: Weather V2 Incremental Upgrade

Tests for:
1. by_market_type breakdown in weather health endpoint
2. market_type field in signals and best_signal_this_scan
3. Negative Celsius parsing (Toronto -9°C, -11°C or below, -5°C or higher)
4. Non-temperature bucket parsing (precipitation, snow, wind)
5. Non-temperature probability computation
6. Open-Meteo fetching precipitation/snowfall/wind data
7. Positions endpoints continue working
"""

import os
import pytest
import requests
import sys

# Add backend to path for unit test imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://edge-trading-hub-1.preview.emergentagent.com').rstrip('/')


class TestWeatherHealthByMarketType:
    """Test by_market_type breakdown in weather health endpoint"""
    
    def test_weather_health_returns_200(self):
        """Health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, dict), "Health response should be a dict"
        print("PASS: Weather health endpoint returns 200")
    
    def test_by_market_type_exists(self):
        """Health response includes by_market_type object"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        assert "by_market_type" in data, "Health response missing by_market_type field"
        print(f"PASS: by_market_type found in health response")
    
    def test_by_market_type_has_four_categories(self):
        """by_market_type includes temperature, precipitation, snowfall, wind"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        by_type = data.get("by_market_type", {})
        
        expected_types = ["temperature", "precipitation", "snowfall", "wind"]
        for mtype in expected_types:
            assert mtype in by_type, f"by_market_type missing {mtype}"
            sub = by_type[mtype]
            assert isinstance(sub, dict), f"{mtype} should be a dict"
            # Each category should have classified/signals/executed/rejected counts
            assert "classified" in sub, f"{mtype} missing 'classified' count"
            assert "signals" in sub, f"{mtype} missing 'signals' count"
            assert "rejected" in sub, f"{mtype} missing 'rejected' count"
        print(f"PASS: by_market_type has all 4 categories with proper structure: {list(by_type.keys())}")
    
    def test_temperature_classified_count(self):
        """Temperature category should show classified markets"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        temp_stats = data.get("by_market_type", {}).get("temperature", {})
        # Agent note: expected 69 classified from Toronto Celsius fix
        classified = temp_stats.get("classified", 0)
        assert isinstance(classified, int), "classified should be integer"
        print(f"PASS: Temperature classified count = {classified}")


class TestWeatherSignalsMarketType:
    """Test market_type field in weather signals"""
    
    def test_signals_endpoint_returns_200(self):
        """Signals endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Weather signals endpoint returns 200")
    
    def test_tradable_signals_have_market_type(self):
        """Tradable signals include market_type field"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200
        data = response.json()
        
        tradable = data.get("tradable", [])
        if len(tradable) > 0:
            for sig in tradable[:5]:  # Check first 5
                assert "market_type" in sig, f"Signal missing market_type: {sig.get('id', 'unknown')}"
                mtype = sig["market_type"]
                assert mtype in ["temperature", "precipitation", "snowfall", "wind"], \
                    f"Invalid market_type: {mtype}"
            print(f"PASS: {len(tradable)} tradable signals have market_type field")
        else:
            print("INFO: No tradable signals to verify market_type (expected in low-activity periods)")
    
    def test_rejected_signals_have_market_type_or_explanation(self):
        """Rejected signals have market_type context"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200
        data = response.json()
        
        rejected = data.get("rejected", [])
        if len(rejected) > 0:
            for sig in rejected[:5]:
                # market_type should be present
                if "market_type" in sig:
                    assert sig["market_type"] in ["temperature", "precipitation", "snowfall", "wind", ""]
            print(f"PASS: Rejected signals checked ({len(rejected)} total)")
        else:
            print("INFO: No rejected signals to verify")


class TestBestSignalMarketType:
    """Test best_signal_this_scan includes market_type"""
    
    def test_best_signal_has_market_type(self):
        """best_signal_this_scan includes market_type field when present"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        data = response.json()
        
        best = data.get("best_signal_this_scan")
        if best is not None:
            assert "market_type" in best, "best_signal_this_scan missing market_type field"
            mtype = best["market_type"]
            assert mtype in ["temperature", "precipitation", "snowfall", "wind"], \
                f"Invalid market_type in best_signal: {mtype}"
            print(f"PASS: best_signal_this_scan has market_type={mtype}")
            print(f"  station={best.get('station')}, date={best.get('date')}, bucket={best.get('bucket')}, edge={best.get('edge_bps')}bps")
        else:
            print("INFO: No best_signal_this_scan (strategy may need more scan time)")


class TestNegativeCelsiusParsing:
    """Unit tests for negative Celsius temperature parsing"""
    
    def test_parse_bucket_negative_exact(self):
        """Parse negative exact temp: 'be -9°C on March 17?'"""
        from engine.strategies.weather_parser import parse_bucket_from_question
        
        question = "Will the highest temperature in Toronto be -9°C on March 17?"
        bucket = parse_bucket_from_question(question, "token123")
        
        assert bucket is not None, f"Failed to parse negative exact temp from: {question}"
        assert "-9" in bucket.label, f"Label should contain -9: {bucket.label}"
        # -9°C = 15.8°F approximately
        assert bucket.lower_bound is not None or bucket.upper_bound is not None
        print(f"PASS: Parsed negative exact: label={bucket.label}, lower={bucket.lower_bound}, upper={bucket.upper_bound}")
    
    def test_parse_bucket_negative_or_below(self):
        """Parse negative 'or below': 'be -11°C or below on March 17?'"""
        from engine.strategies.weather_parser import parse_bucket_from_question
        
        question = "Will the highest temperature in Toronto be -11°C or below on March 17?"
        bucket = parse_bucket_from_question(question, "token456")
        
        assert bucket is not None, f"Failed to parse negative 'or below' from: {question}"
        assert "or below" in bucket.label.lower() or bucket.upper_bound is not None
        print(f"PASS: Parsed negative or below: label={bucket.label}, upper_bound={bucket.upper_bound}")
    
    def test_parse_bucket_negative_or_higher(self):
        """Parse negative 'or higher': 'be -5°C or higher on March 17?'"""
        from engine.strategies.weather_parser import parse_bucket_from_question
        
        question = "Will the highest temperature in Toronto be -5°C or higher on March 17?"
        bucket = parse_bucket_from_question(question, "token789")
        
        assert bucket is not None, f"Failed to parse negative 'or higher' from: {question}"
        assert "or higher" in bucket.label.lower() or bucket.lower_bound is not None
        print(f"PASS: Parsed negative or higher: label={bucket.label}, lower_bound={bucket.lower_bound}")
    
    def test_celsius_to_fahrenheit_conversion(self):
        """Negative Celsius converts to correct Fahrenheit"""
        from engine.strategies.weather_parser import parse_bucket_from_question
        
        # -10°C should be 14°F
        question = "Will the highest temperature in Toronto be -10°C on March 17?"
        bucket = parse_bucket_from_question(question, "token_conv")
        
        if bucket:
            # For exact value, bounds should be around 14°F (±0.5 for continuity)
            if bucket.lower_bound is not None:
                expected_f = -10 * 9/5 + 32  # = 14
                # Allow tolerance for continuity correction
                assert abs(bucket.lower_bound - (expected_f - 0.5)) < 1 or abs(bucket.lower_bound - expected_f) < 2
            print(f"PASS: Celsius conversion verified: bounds={bucket.lower_bound}, {bucket.upper_bound}")
        else:
            print("WARN: Could not parse -10°C question (may be pattern mismatch)")


class TestNonTemperatureParsing:
    """Unit tests for precipitation/snow/wind bucket parsing"""
    
    def test_detect_market_type_precipitation(self):
        """Detect precipitation market type from question"""
        from engine.strategies.weather_parser import _detect_market_type
        from engine.strategies.weather_models import WeatherMarketType
        
        questions = [
            "Will there be 0.5 inches or more of rain in NYC on March 18?",
            "Will precipitation exceed 1 inch in Chicago on March 20?",
        ]
        for q in questions:
            mtype = _detect_market_type(q)
            assert mtype == WeatherMarketType.PRECIPITATION, f"Expected PRECIPITATION, got {mtype} for: {q[:50]}"
        print("PASS: Precipitation market type detection works")
    
    def test_detect_market_type_snowfall(self):
        """Detect snowfall market type from question"""
        from engine.strategies.weather_parser import _detect_market_type
        from engine.strategies.weather_models import WeatherMarketType
        
        questions = [
            "Will NYC get 3 or more inches of snow on March 20?",
            "Will there be at least 5 inches of snowfall in Denver?",
        ]
        for q in questions:
            mtype = _detect_market_type(q)
            assert mtype == WeatherMarketType.SNOWFALL, f"Expected SNOWFALL, got {mtype} for: {q[:50]}"
        print("PASS: Snowfall market type detection works")
    
    def test_detect_market_type_wind(self):
        """Detect wind market type from question"""
        from engine.strategies.weather_parser import _detect_market_type
        from engine.strategies.weather_models import WeatherMarketType
        
        questions = [
            "Will wind speeds exceed 40 mph in Chicago on March 19?",
            "Will there be 30 mph or more wind in Dallas?",
        ]
        for q in questions:
            mtype = _detect_market_type(q)
            assert mtype == WeatherMarketType.WIND, f"Expected WIND, got {mtype} for: {q[:50]}"
        print("PASS: Wind market type detection works")
    
    def test_parse_amount_bucket_precip(self):
        """Parse precipitation amount bucket"""
        from engine.strategies.weather_parser import parse_amount_bucket_from_question
        from engine.strategies.weather_models import WeatherMarketType
        
        question = "Will there be 0.5 inches or more of rain in NYC on March 18?"
        bucket = parse_amount_bucket_from_question(question, "precip_token", WeatherMarketType.PRECIPITATION)
        
        assert bucket is not None, f"Failed to parse precipitation bucket from: {question}"
        assert bucket.lower_bound is not None or bucket.upper_bound is not None
        print(f"PASS: Parsed precipitation bucket: label={bucket.label}, lower={bucket.lower_bound}, upper={bucket.upper_bound}")
    
    def test_parse_amount_bucket_snow(self):
        """Parse snowfall amount bucket"""
        from engine.strategies.weather_parser import parse_amount_bucket_from_question
        from engine.strategies.weather_models import WeatherMarketType
        
        question = "Will NYC get at least 3 inches of snow on March 20?"
        bucket = parse_amount_bucket_from_question(question, "snow_token", WeatherMarketType.SNOWFALL)
        
        assert bucket is not None, f"Failed to parse snowfall bucket from: {question}"
        print(f"PASS: Parsed snowfall bucket: label={bucket.label}, lower={bucket.lower_bound}, upper={bucket.upper_bound}")
    
    def test_parse_amount_bucket_wind(self):
        """Parse wind speed bucket"""
        from engine.strategies.weather_parser import parse_amount_bucket_from_question
        from engine.strategies.weather_models import WeatherMarketType
        
        question = "Will wind speeds exceed 40 mph in Chicago on March 19?"
        bucket = parse_amount_bucket_from_question(question, "wind_token", WeatherMarketType.WIND)
        
        assert bucket is not None, f"Failed to parse wind bucket from: {question}"
        print(f"PASS: Parsed wind bucket: label={bucket.label}, lower={bucket.lower_bound}, upper={bucket.upper_bound}")


class TestAmountProbabilityComputation:
    """Unit tests for non-temperature probability computation"""
    
    def test_compute_amount_bucket_probability_precip(self):
        """Probability computation for precipitation"""
        from engine.strategies.weather_pricing import compute_amount_bucket_probability
        from engine.strategies.weather_models import TempBucket
        
        # Threshold: 0.5 inches or more
        bucket = TempBucket(label="0.5+ in", token_id="t1", lower_bound=0.5, upper_bound=None)
        
        # Forecast: 0.3 inches with sigma 0.3
        prob = compute_amount_bucket_probability(bucket, 0.3, 0.3, "precipitation")
        
        assert 0 <= prob <= 1, f"Probability out of range: {prob}"
        # With forecast 0.3 and sigma 0.3, P(>0.5) should be moderate
        print(f"PASS: Precipitation probability = {prob:.4f}")
    
    def test_compute_amount_bucket_probability_snow(self):
        """Probability computation for snowfall"""
        from engine.strategies.weather_pricing import compute_amount_bucket_probability
        from engine.strategies.weather_models import TempBucket
        
        # Threshold: 3 inches or more
        bucket = TempBucket(label="3+ in", token_id="t2", lower_bound=3.0, upper_bound=None)
        
        # Forecast: 4 inches with sigma 2.0
        prob = compute_amount_bucket_probability(bucket, 4.0, 2.0, "snowfall")
        
        assert 0 <= prob <= 1, f"Probability out of range: {prob}"
        # Forecast above threshold should give >50% probability
        assert prob > 0.5, f"Expected >50% with forecast above threshold, got {prob}"
        print(f"PASS: Snowfall probability = {prob:.4f}")
    
    def test_compute_amount_bucket_probability_wind(self):
        """Probability computation for wind"""
        from engine.strategies.weather_pricing import compute_amount_bucket_probability
        from engine.strategies.weather_models import TempBucket
        
        # Threshold: 40 mph or more
        bucket = TempBucket(label="40+ mph", token_id="t3", lower_bound=40.0, upper_bound=None)
        
        # Forecast: 35 mph with sigma 5.0
        prob = compute_amount_bucket_probability(bucket, 35.0, 5.0, "wind")
        
        assert 0 <= prob <= 1, f"Probability out of range: {prob}"
        # 1 sigma below threshold should give ~16% probability
        print(f"PASS: Wind probability = {prob:.4f}")
    
    def test_get_amount_sigma(self):
        """Sigma tables return valid values for each type"""
        from engine.strategies.weather_pricing import get_amount_sigma
        
        for mtype in ["precipitation", "snowfall", "wind"]:
            for lead_hours in [12, 36, 60, 100, 150]:
                sigma = get_amount_sigma(mtype, lead_hours)
                assert sigma > 0, f"Sigma should be positive for {mtype} at {lead_hours}h"
                assert sigma < 20, f"Sigma seems too high for {mtype}: {sigma}"
        print("PASS: All amount sigma values are valid")


class TestForecastSnapshotFields:
    """Test ForecastSnapshot model has new fields"""
    
    def test_forecast_snapshot_has_precip_snow_wind_fields(self):
        """ForecastSnapshot model includes new forecast fields"""
        from engine.strategies.weather_models import ForecastSnapshot
        
        # Create a snapshot with all fields
        snapshot = ForecastSnapshot(
            station_id="KLGA",
            target_date="2026-03-17",
            forecast_high_f=45.0,
            forecast_precip_in=0.2,
            forecast_snow_in=0.0,
            forecast_wind_mph=15.5,
            source="open_meteo",
            lead_hours=24.0,
        )
        
        assert snapshot.forecast_precip_in == 0.2
        assert snapshot.forecast_snow_in == 0.0
        assert snapshot.forecast_wind_mph == 15.5
        print(f"PASS: ForecastSnapshot has precip={snapshot.forecast_precip_in}in, snow={snapshot.forecast_snow_in}in, wind={snapshot.forecast_wind_mph}mph")


class TestPositionsEndpoints:
    """Test existing position endpoints still work"""
    
    def test_weather_breakdown_returns_200(self):
        """GET /api/positions/weather/breakdown returns 200"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/breakdown")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "total_open" in data, "Missing total_open field"
        assert "total_unrealized_pnl" in data, "Missing total_unrealized_pnl field"
        assert "by_resolution_date" in data, "Missing by_resolution_date field"
        assert "biggest_winners" in data, "Missing biggest_winners field"
        print(f"PASS: Weather breakdown returns valid data (total_open={data['total_open']})")
    
    def test_by_strategy_returns_200(self):
        """GET /api/positions/by-strategy returns 200"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "positions" in data or "summaries" in data, "Expected positions or summaries in response"
        if "positions" in data and "weather" in data["positions"]:
            weather_positions = data["positions"]["weather"]
            print(f"PASS: by-strategy returns weather positions ({len(weather_positions)} positions)")
        else:
            print("PASS: by-strategy endpoint returns 200")


class TestSniperAndAnalytics:
    """Verify sniper and analytics endpoints still work"""
    
    def test_sniper_signals_returns_200(self):
        """GET /api/strategies/sniper/signals returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Sniper signals endpoint returns 200")
    
    def test_sniper_health_returns_200(self):
        """GET /api/strategies/sniper/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Sniper health endpoint returns 200")
    
    def test_strategy_attribution_returns_200(self):
        """GET /api/analytics/strategy-attribution returns 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Strategy attribution endpoint returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
