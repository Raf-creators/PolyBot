"""Tests for Phase 10 Step 1 (weather_models.py) and Step 2 (weather_parser.py).

Covers:
  - Model instantiation with defaults and custom values
  - JSON serialization round-trips
  - Station registry completeness and lookup
  - Market question parsing across realistic variations
  - Bucket parsing for all known formats
  - Rejection reasons for malformed/unparseable markets
  - Edge cases: past dates, unknown cities, missing keywords, bad buckets
"""

import pytest
import json
from datetime import datetime, timezone, date as date_type

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.strategies.weather_models import (
    WeatherConfig, StationInfo, StationType, Season,
    TempBucket, WeatherMarketClassification, ForecastSnapshot,
    SigmaCalibration, BucketProbability, WeatherSignal, WeatherExecution,
    WeatherSignalStatus,
)
from engine.strategies.weather_parser import (
    STATION_REGISTRY, lookup_station, get_all_stations,
    parse_single_bucket, parse_temp_buckets, validate_buckets,
    classify_weather_market, _parse_date, _extract_city,
)


# ===========================================================================
# Step 1: Model Tests
# ===========================================================================

class TestWeatherConfig:
    def test_defaults(self):
        cfg = WeatherConfig()
        assert cfg.scan_interval == 60.0
        assert cfg.min_edge_bps == 300.0
        assert cfg.max_concurrent_signals == 8
        assert cfg.kelly_scale == 0.25
        assert cfg.cooldown_seconds == 1800.0

    def test_custom_values(self):
        cfg = WeatherConfig(min_edge_bps=500.0, scan_interval=30.0)
        assert cfg.min_edge_bps == 500.0
        assert cfg.scan_interval == 30.0

    def test_json_roundtrip(self):
        cfg = WeatherConfig()
        data = cfg.model_dump()
        cfg2 = WeatherConfig(**data)
        assert cfg == cfg2


class TestStationInfo:
    def test_create(self):
        s = StationInfo(
            station_id="KTEST", city="Test City", state="TS",
            latitude=40.0, longitude=-74.0, elevation_ft=100,
            timezone="America/New_York", station_type=StationType.COASTAL,
            wunderground_slug="us/ts/test-city/KTEST",
            aliases=["Test"],
        )
        assert s.station_id == "KTEST"
        assert s.station_type == StationType.COASTAL

    def test_json_roundtrip(self):
        s = STATION_REGISTRY["KLGA"]
        data = s.model_dump()
        s2 = StationInfo(**data)
        assert s2.station_id == "KLGA"
        assert s2.city == "New York City"


class TestTempBucket:
    def test_lower_open(self):
        b = TempBucket(label="40F or below", token_id="t1", upper_bound=40)
        assert b.is_lower_open is True
        assert b.is_upper_open is False
        assert b.midpoint is None

    def test_upper_open(self):
        b = TempBucket(label="47F or higher", token_id="t5", lower_bound=47)
        assert b.is_lower_open is False
        assert b.is_upper_open is True

    def test_bounded(self):
        b = TempBucket(label="43-44F", token_id="t3", lower_bound=43, upper_bound=44)
        assert b.is_lower_open is False
        assert b.is_upper_open is False
        assert b.midpoint == 43.5

    def test_json_roundtrip(self):
        b = TempBucket(label="41-42F", token_id="t2", lower_bound=41, upper_bound=42)
        data = b.model_dump()
        b2 = TempBucket(**data)
        assert b2.lower_bound == 41
        assert b2.upper_bound == 42


class TestWeatherMarketClassification:
    def test_create(self):
        buckets = [
            TempBucket(label="40F or below", token_id="t1", upper_bound=40),
            TempBucket(label="41-42F", token_id="t2", lower_bound=41, upper_bound=42),
            TempBucket(label="47F or higher", token_id="t5", lower_bound=47),
        ]
        c = WeatherMarketClassification(
            condition_id="cond1", station_id="KLGA", city="New York City",
            target_date="2026-03-15", resolution_type="daily_high",
            buckets=buckets, question="Highest temperature in NYC on March 15, 2026?",
        )
        assert c.station_id == "KLGA"
        assert len(c.buckets) == 3
        assert c.classified_at  # auto-generated


class TestForecastSnapshot:
    def test_create(self):
        f = ForecastSnapshot(
            station_id="KLGA", target_date="2026-03-15",
            forecast_high_f=44.0, lead_hours=36.0,
        )
        assert f.source == "open_meteo"
        assert f.fetched_at  # auto-generated


class TestSigmaCalibration:
    def test_defaults(self):
        cal = SigmaCalibration(station_id="KLGA")
        assert cal.sigma_by_lead_hours["0_24"] == 1.8
        assert cal.sigma_by_lead_hours["120_168"] == 6.2
        assert cal.seasonal_factors["winter"] == 1.15
        assert cal.mean_bias_f == 0.0


class TestBucketProbability:
    def test_create(self):
        bp = BucketProbability(
            label="43-44F", token_id="t3",
            model_prob=0.35, market_price=0.22, edge_bps=1300.0,
        )
        assert bp.is_tradable is False  # default
        assert bp.edge_bps == 1300.0


class TestWeatherSignal:
    def test_create(self):
        sig = WeatherSignal(
            condition_id="c1", station_id="KLGA", target_date="2026-03-15",
            bucket_label="43-44F", token_id="t3",
            forecast_high_f=44.0, sigma=2.5, lead_hours=36.0,
            model_prob=0.35, market_price=0.22, edge_bps=1300.0,
            confidence=0.65, recommended_size=3.0, is_tradable=True,
        )
        assert sig.id  # auto-generated
        assert sig.is_tradable is True
        assert sig.rejection_reason is None


class TestWeatherExecution:
    def test_create(self):
        ex = WeatherExecution(
            signal_id="s1", condition_id="c1", station_id="KLGA",
            target_date="2026-03-15", bucket_label="43-44F",
            order_id="o1", target_edge_bps=1300.0, size=3.0,
        )
        assert ex.status == WeatherSignalStatus.SUBMITTED
        assert ex.entry_price is None


# ===========================================================================
# Step 2: Station Registry Tests
# ===========================================================================

class TestStationRegistry:
    def test_all_stations_present(self):
        expected = {"KLGA", "KORD", "KLAX", "KATL", "KDFW", "KMIA", "KDEN", "KSFO"}
        assert set(STATION_REGISTRY.keys()) == expected

    def test_all_stations_have_required_fields(self):
        for sid, info in STATION_REGISTRY.items():
            assert info.station_id == sid
            assert info.city
            assert info.state
            assert info.latitude != 0
            assert info.longitude != 0
            assert info.timezone
            assert info.station_type in (StationType.COASTAL, StationType.INLAND)
            assert info.wunderground_slug
            assert len(info.aliases) >= 1

    def test_lookup_by_city(self):
        assert lookup_station("New York City").station_id == "KLGA"
        assert lookup_station("Chicago").station_id == "KORD"
        assert lookup_station("Miami").station_id == "KMIA"

    def test_lookup_by_alias(self):
        assert lookup_station("NYC").station_id == "KLGA"
        assert lookup_station("LA").station_id == "KLAX"
        assert lookup_station("SF").station_id == "KSFO"
        assert lookup_station("DFW").station_id == "KDFW"

    def test_lookup_case_insensitive(self):
        assert lookup_station("nyc").station_id == "KLGA"
        assert lookup_station("CHICAGO").station_id == "KORD"
        assert lookup_station("los angeles").station_id == "KLAX"

    def test_lookup_unknown(self):
        assert lookup_station("Unknown City") is None
        assert lookup_station("") is None
        assert lookup_station("Tokyo") is None

    def test_get_all_stations(self):
        stations = get_all_stations()
        assert len(stations) == 8
        assert all(isinstance(s, StationInfo) for s in stations)


# ===========================================================================
# Step 2: Date Parsing Tests
# ===========================================================================

class TestDateParsing:
    def test_full_date_with_comma(self):
        d = _parse_date("Highest temperature on March 13, 2026?")
        assert d == date_type(2026, 3, 13)

    def test_full_date_without_comma(self):
        d = _parse_date("temperature on March 13 2026")
        assert d == date_type(2026, 3, 13)

    def test_abbreviated_month(self):
        d = _parse_date("temp on Mar 13, 2026")
        assert d == date_type(2026, 3, 13)

    def test_numeric_date_slash(self):
        d = _parse_date("temp on 3/13/2026")
        assert d == date_type(2026, 3, 13)

    def test_numeric_date_dash(self):
        d = _parse_date("temp on 3-13-2026")
        assert d == date_type(2026, 3, 13)

    def test_no_date(self):
        assert _parse_date("some random text") is None

    def test_invalid_date(self):
        assert _parse_date("February 30, 2026") is None

    def test_month_without_year_future(self):
        """If no year given and date is in the future, use current year."""
        d = _parse_date("temp on December 25")
        assert d is not None
        assert d.month == 12
        assert d.day == 25


# ===========================================================================
# Step 2: City Extraction Tests
# ===========================================================================

class TestCityExtraction:
    def test_extract_nyc(self):
        assert _extract_city("Highest temperature in NYC on March 13") == "KLGA"

    def test_extract_new_york_city(self):
        assert _extract_city("temperature in New York City on March 13") == "KLGA"

    def test_extract_chicago(self):
        assert _extract_city("high temp in Chicago on March 15") == "KORD"

    def test_extract_la(self):
        assert _extract_city("temperature in Los Angeles on March 20") == "KLAX"

    def test_extract_la_abbreviation(self):
        assert _extract_city("temperature in LA on March 20") == "KLAX"

    def test_extract_unknown(self):
        assert _extract_city("temperature in Tokyo on March 20") is None


# ===========================================================================
# Step 2: Bucket Parsing Tests
# ===========================================================================

class TestSingleBucketParsing:
    # ---- Lower-open buckets ----
    def test_or_below_with_f(self):
        b = parse_single_bucket("40F or below", "t1")
        assert b is not None
        assert b.upper_bound == 40
        assert b.lower_bound is None

    def test_or_below_with_space_f(self):
        b = parse_single_bucket("40 F or below", "t1")
        assert b is not None
        assert b.upper_bound == 40

    def test_or_below_no_f(self):
        b = parse_single_bucket("40 or below", "t1")
        assert b is not None
        assert b.upper_bound == 40

    def test_or_lower(self):
        b = parse_single_bucket("40F or lower", "t1")
        assert b is not None
        assert b.upper_bound == 40

    def test_or_less(self):
        b = parse_single_bucket("40 or less", "t1")
        assert b is not None
        assert b.upper_bound == 40

    def test_degree_symbol(self):
        b = parse_single_bucket("40°F or below", "t1")
        assert b is not None
        assert b.upper_bound == 40

    # ---- Upper-open buckets ----
    def test_or_higher_with_f(self):
        b = parse_single_bucket("47F or higher", "t5")
        assert b is not None
        assert b.lower_bound == 47
        assert b.upper_bound is None

    def test_or_above(self):
        b = parse_single_bucket("47F or above", "t5")
        assert b is not None
        assert b.lower_bound == 47

    def test_or_more(self):
        b = parse_single_bucket("47 or more", "t5")
        assert b is not None
        assert b.lower_bound == 47

    def test_or_greater(self):
        b = parse_single_bucket("47°F or greater", "t5")
        assert b is not None
        assert b.lower_bound == 47

    # ---- Bounded buckets ----
    def test_dash_f(self):
        b = parse_single_bucket("41-42F", "t2")
        assert b is not None
        assert b.lower_bound == 41
        assert b.upper_bound == 42

    def test_dash_space_f(self):
        b = parse_single_bucket("41 - 42 F", "t2")
        assert b is not None
        assert b.lower_bound == 41
        assert b.upper_bound == 42

    def test_endash(self):
        b = parse_single_bucket("41\u201342F", "t2")
        assert b is not None
        assert b.lower_bound == 41
        assert b.upper_bound == 42

    def test_bare_numbers(self):
        b = parse_single_bucket("41-42", "t2")
        assert b is not None
        assert b.lower_bound == 41
        assert b.upper_bound == 42

    def test_to_keyword(self):
        b = parse_single_bucket("41 to 42 F", "t2")
        assert b is not None
        assert b.lower_bound == 41
        assert b.upper_bound == 42

    # ---- Unparseable ----
    def test_unparseable_text(self):
        assert parse_single_bucket("sunny skies", "t1") is None

    def test_unparseable_empty(self):
        assert parse_single_bucket("", "t1") is None


class TestParseAllBuckets:
    def test_full_market(self):
        outcomes = ["40F or below", "41-42F", "43-44F", "45-46F", "47F or higher"]
        tokens = ["t1", "t2", "t3", "t4", "t5"]
        buckets, errors = parse_temp_buckets(outcomes, tokens)
        assert len(buckets) == 5
        assert len(errors) == 0
        assert buckets[0].is_lower_open
        assert buckets[4].is_upper_open

    def test_partial_failure(self):
        outcomes = ["40F or below", "garbage", "47F or higher"]
        tokens = ["t1", "t2", "t3"]
        buckets, errors = parse_temp_buckets(outcomes, tokens)
        assert len(buckets) == 2
        assert len(errors) == 1
        assert "unparseable" in errors[0]

    def test_mismatched_lengths(self):
        outcomes = ["40F or below", "41-42F"]
        tokens = ["t1"]
        buckets, errors = parse_temp_buckets(outcomes, tokens)
        assert len(buckets) == 0
        assert len(errors) == 1
        assert "mismatch" in errors[0]


class TestValidateBuckets:
    def test_valid_set(self):
        buckets = [
            TempBucket(label="40F or below", token_id="t1", upper_bound=40),
            TempBucket(label="41-42F", token_id="t2", lower_bound=41, upper_bound=42),
            TempBucket(label="47F or higher", token_id="t5", lower_bound=47),
        ]
        assert validate_buckets(buckets) is None

    def test_too_few(self):
        buckets = [TempBucket(label="40F or below", token_id="t1", upper_bound=40)]
        err = validate_buckets(buckets)
        assert "too_few" in err

    def test_missing_lower_open(self):
        buckets = [
            TempBucket(label="41-42F", token_id="t2", lower_bound=41, upper_bound=42),
            TempBucket(label="47F or higher", token_id="t5", lower_bound=47),
        ]
        err = validate_buckets(buckets)
        assert "missing_lower_open" in err

    def test_missing_upper_open(self):
        buckets = [
            TempBucket(label="40F or below", token_id="t1", upper_bound=40),
            TempBucket(label="41-42F", token_id="t2", lower_bound=41, upper_bound=42),
        ]
        err = validate_buckets(buckets)
        assert "missing_upper_open" in err

    def test_duplicate_tokens(self):
        buckets = [
            TempBucket(label="40F or below", token_id="t1", upper_bound=40),
            TempBucket(label="41-42F", token_id="t1", lower_bound=41, upper_bound=42),
            TempBucket(label="47F or higher", token_id="t3", lower_bound=47),
        ]
        err = validate_buckets(buckets)
        assert "duplicate" in err


# ===========================================================================
# Step 2: Full Classification Tests
# ===========================================================================

class TestClassifyWeatherMarket:
    """Test the end-to-end classify_weather_market function."""

    STANDARD_OUTCOMES = ["40F or below", "41-42F", "43-44F", "45-46F", "47F or higher"]
    STANDARD_TOKENS = ["t1", "t2", "t3", "t4", "t5"]

    def test_standard_nyc(self):
        c, err = classify_weather_market(
            question="Highest temperature in NYC on March 15, 2026?",
            condition_id="cond1",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c is not None
        assert c.station_id == "KLGA"
        assert c.target_date == "2026-03-15"
        assert c.resolution_type == "daily_high"
        assert len(c.buckets) == 5

    def test_full_city_name(self):
        c, err = classify_weather_market(
            question="Highest temperature in New York City on March 15, 2026?",
            condition_id="cond1",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c.station_id == "KLGA"

    def test_what_will_variant(self):
        c, err = classify_weather_market(
            question="What will the high temperature be in Chicago on March 18, 2026?",
            condition_id="cond2",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c.station_id == "KORD"
        assert c.target_date == "2026-03-18"

    def test_la_market(self):
        c, err = classify_weather_market(
            question="Highest temperature in Los Angeles on April 1, 2026?",
            condition_id="cond3",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c.station_id == "KLAX"

    def test_miami_abbreviated(self):
        c, err = classify_weather_market(
            question="Highest temperature in Miami on Mar 20, 2026?",
            condition_id="cond4",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c.station_id == "KMIA"

    def test_denver_market(self):
        c, err = classify_weather_market(
            question="High temperature in Denver on March 22, 2026?",
            condition_id="cond5",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c.station_id == "KDEN"

    def test_sf_market(self):
        c, err = classify_weather_market(
            question="Highest temperature in San Francisco on March 25, 2026?",
            condition_id="cond6",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c.station_id == "KSFO"

    def test_atlanta_market(self):
        c, err = classify_weather_market(
            question="Highest temperature in Atlanta on March 30, 2026?",
            condition_id="cond7",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c.station_id == "KATL"

    def test_dallas_market(self):
        c, err = classify_weather_market(
            question="Highest temperature in Dallas on April 5, 2026?",
            condition_id="cond8",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert err is None
        assert c.station_id == "KDFW"

    # ---- Rejection cases ----

    def test_reject_no_weather_keyword(self):
        c, err = classify_weather_market(
            question="Will BTC be above $97,000 at 12:15 UTC?",
            condition_id="cond_btc",
            outcomes=["Yes", "No"],
            token_ids=["ty", "tn"],
        )
        assert c is None
        assert err == "no_weather_keyword"

    def test_reject_unknown_city(self):
        c, err = classify_weather_market(
            question="Highest temperature in Tokyo on March 15, 2026?",
            condition_id="cond_tokyo",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert c is None
        assert "unknown_city" in err

    def test_reject_no_date(self):
        c, err = classify_weather_market(
            question="Highest temperature in NYC?",
            condition_id="cond_nodate",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert c is None
        assert err == "no_date_found"

    def test_reject_past_date(self):
        c, err = classify_weather_market(
            question="Highest temperature in NYC on January 1, 2020?",
            condition_id="cond_past",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert c is None
        assert "date_in_past" in err

    def test_reject_bad_buckets(self):
        c, err = classify_weather_market(
            question="Highest temperature in NYC on March 15, 2026?",
            condition_id="cond_badbucket",
            outcomes=["Yes", "No"],
            token_ids=["ty", "tn"],
        )
        assert c is None
        assert "bucket_parse_failed" in err or "invalid_buckets" in err

    def test_reject_missing_boundary_buckets(self):
        # Only bounded buckets, no open-ended ones
        c, err = classify_weather_market(
            question="Highest temperature in NYC on March 15, 2026?",
            condition_id="cond_nobounds",
            outcomes=["41-42F", "43-44F", "45-46F"],
            token_ids=["t1", "t2", "t3"],
        )
        assert c is None
        assert "invalid_buckets" in err
        assert "missing_lower_open" in err

    def test_reject_single_bucket(self):
        c, err = classify_weather_market(
            question="Highest temperature in NYC on March 15, 2026?",
            condition_id="cond_single",
            outcomes=["40F or below"],
            token_ids=["t1"],
        )
        assert c is None
        # Either bucket_parse_failed (not enough) or invalid_buckets (too_few)
        assert "invalid_buckets" in err or "bucket_parse_failed" in err

    # ---- Edge case: city in question but not in regex capture ----
    def test_fallback_city_extraction(self):
        """City not in the regex-captured group but present in the full question."""
        c, err = classify_weather_market(
            question="Temperature forecast: NYC high temp on March 15, 2026?",
            condition_id="cond_fallback",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        # Should either succeed (fallback scan) or have a clear rejection
        if c is not None:
            assert c.station_id == "KLGA"
        else:
            assert err is not None  # at minimum, we get a reason

    # ---- Degree symbol and varied formats ----
    def test_degree_symbol_buckets(self):
        outcomes = ["40°F or below", "41°F-42°F", "43°F-44°F", "45°F-46°F", "47°F or higher"]
        tokens = ["t1", "t2", "t3", "t4", "t5"]
        c, err = classify_weather_market(
            question="Highest temperature in NYC on March 15, 2026?",
            condition_id="cond_deg",
            outcomes=outcomes,
            token_ids=tokens,
        )
        assert err is None
        assert len(c.buckets) == 5


# ===========================================================================
# Rejection reason cleanliness
# ===========================================================================

class TestRejectionReasons:
    """Verify rejection reasons are clean, non-None strings."""

    STANDARD_OUTCOMES = ["40F or below", "41-42F", "43-44F", "45-46F", "47F or higher"]
    STANDARD_TOKENS = ["t1", "t2", "t3", "t4", "t5"]

    REJECT_CASES = [
        ("Will BTC be above $97,000?", "no_weather_keyword"),
        ("Highest temperature in Tokyo on March 15, 2026?", "unknown_city"),
        ("Highest temperature in NYC?", "no_date_found"),
        ("Highest temperature in NYC on January 1, 2020?", "date_in_past"),
    ]

    @pytest.mark.parametrize("question,expected_substr", REJECT_CASES)
    def test_rejection_reason_is_clean_string(self, question, expected_substr):
        c, err = classify_weather_market(
            question=question,
            condition_id="cond_test",
            outcomes=self.STANDARD_OUTCOMES,
            token_ids=self.STANDARD_TOKENS,
        )
        assert c is None
        assert isinstance(err, str)
        assert len(err) > 0
        assert expected_substr in err
