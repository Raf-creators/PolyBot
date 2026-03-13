"""Tests for Phase 10 Step 3: weather_pricing.py

Covers:
  - Normal CDF correctness
  - Season determination
  - Sigma calibration (defaults, partial, full, clamping)
  - Individual bucket probability (lower-open, upper-open, bounded)
  - Continuity correction
  - All-bucket probability normalization (sums to ~1.0)
  - EV and edge calculation
  - Kelly sizing (positive edge, zero/negative edge, clamping)
  - Weather confidence scoring
  - Forecast blending (single, multiple, disagreement inflation)
  - Contiguous bucket validation (gap detection in parser)
  - Edge cases: zero sigma, extreme mu, extreme lead times
"""

import math
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.strategies.weather_models import (
    TempBucket, SigmaCalibration, StationType, Season,
)
from engine.strategies.weather_pricing import (
    normal_cdf, get_season, calibrate_sigma,
    compute_bucket_probability, compute_all_bucket_probabilities,
    compute_edge_bps, compute_bucket_ev, evaluate_all_buckets,
    kelly_size, compute_weather_confidence, blend_forecasts,
    _SIGMA_FLOOR, _SIGMA_CEILING,
)
from engine.strategies.weather_parser import validate_buckets


# ---- Helpers ----

def _make_standard_buckets(token_prefix="t"):
    """Standard 5-bucket set: <=40, 41-42, 43-44, 45-46, >=47"""
    return [
        TempBucket(label="40F or below", token_id=f"{token_prefix}1", upper_bound=40),
        TempBucket(label="41-42F", token_id=f"{token_prefix}2", lower_bound=41, upper_bound=42),
        TempBucket(label="43-44F", token_id=f"{token_prefix}3", lower_bound=43, upper_bound=44),
        TempBucket(label="45-46F", token_id=f"{token_prefix}4", lower_bound=45, upper_bound=46),
        TempBucket(label="47F or higher", token_id=f"{token_prefix}5", lower_bound=47),
    ]


# ===========================================================================
# Normal CDF
# ===========================================================================

class TestNormalCDF:
    def test_cdf_at_zero(self):
        assert abs(normal_cdf(0) - 0.5) < 1e-7

    def test_cdf_at_large_positive(self):
        assert abs(normal_cdf(6.0) - 1.0) < 1e-6

    def test_cdf_at_large_negative(self):
        assert abs(normal_cdf(-6.0) - 0.0) < 1e-6

    def test_cdf_at_one(self):
        # P(Z <= 1) ≈ 0.8413
        assert abs(normal_cdf(1.0) - 0.8413) < 0.001

    def test_cdf_at_neg_one(self):
        # P(Z <= -1) ≈ 0.1587
        assert abs(normal_cdf(-1.0) - 0.1587) < 0.001

    def test_cdf_symmetry(self):
        for x in [0.5, 1.0, 2.0, 3.0]:
            assert abs(normal_cdf(x) + normal_cdf(-x) - 1.0) < 1e-7


# ===========================================================================
# Season Determination
# ===========================================================================

class TestSeason:
    def test_winter(self):
        assert get_season(12) == Season.WINTER
        assert get_season(1) == Season.WINTER
        assert get_season(2) == Season.WINTER

    def test_spring(self):
        assert get_season(3) == Season.SPRING
        assert get_season(4) == Season.SPRING
        assert get_season(5) == Season.SPRING

    def test_summer(self):
        assert get_season(6) == Season.SUMMER
        assert get_season(7) == Season.SUMMER
        assert get_season(8) == Season.SUMMER

    def test_fall(self):
        assert get_season(9) == Season.FALL
        assert get_season(10) == Season.FALL
        assert get_season(11) == Season.FALL


# ===========================================================================
# Sigma Calibration
# ===========================================================================

class TestSigmaCalibration:
    def test_defaults_short_lead(self):
        sigma = calibrate_sigma(12.0, 3, StationType.COASTAL)
        # 0_24 bracket (1.8) * spring (1.0) * coastal (0.90) = 1.62
        assert abs(sigma - 1.62) < 0.01

    def test_defaults_long_lead(self):
        sigma = calibrate_sigma(150.0, 1, StationType.INLAND)
        # 120_168 bracket (6.2) * winter (1.15) * inland (1.10) = 7.843
        assert abs(sigma - 7.843) < 0.01

    def test_summer_reduces_sigma(self):
        sigma_summer = calibrate_sigma(36.0, 7, StationType.COASTAL)
        sigma_winter = calibrate_sigma(36.0, 1, StationType.COASTAL)
        assert sigma_summer < sigma_winter

    def test_inland_increases_sigma(self):
        sigma_inland = calibrate_sigma(36.0, 3, StationType.INLAND)
        sigma_coastal = calibrate_sigma(36.0, 3, StationType.COASTAL)
        assert sigma_inland > sigma_coastal

    def test_sigma_floor(self):
        # Even with very short lead and summer coastal, should not go below floor
        sigma = calibrate_sigma(1.0, 7, StationType.COASTAL)
        assert sigma >= _SIGMA_FLOOR

    def test_sigma_ceiling(self):
        # Even with extreme values, should not exceed ceiling
        sigma = calibrate_sigma(200.0, 1, StationType.INLAND)
        assert sigma <= _SIGMA_CEILING

    def test_full_calibration(self):
        cal = SigmaCalibration(
            station_id="KLGA",
            sample_count=100,
            sigma_by_lead_hours={"0_24": 1.5, "24_48": 2.2, "48_72": 3.0, "72_120": 4.0, "120_168": 5.5},
            seasonal_factors={"winter": 1.2, "spring": 1.0, "summer": 0.85, "fall": 1.05},
            station_type_factor=0.92,
        )
        sigma = calibrate_sigma(36.0, 3, StationType.COASTAL, cal)
        # 24_48 bracket (2.2) * spring (1.0) * 0.92 = 2.024
        assert abs(sigma - 2.024) < 0.01

    def test_partial_calibration_blends(self):
        cal = SigmaCalibration(station_id="KLGA", sample_count=15)
        # weight = 15/30 = 0.5
        sigma = calibrate_sigma(12.0, 3, StationType.COASTAL, cal)
        # Blended base = 0.5 * 1.8 + 0.5 * 1.8 = 1.8 (same defaults)
        # Then * spring(1.0) * coastal(0.90) = 1.62
        assert abs(sigma - 1.62) < 0.05


# ===========================================================================
# Individual Bucket Probability
# ===========================================================================

class TestBucketProbability:
    def test_lower_open_mu_well_below(self):
        """Forecast well below bucket → high probability."""
        b = TempBucket(label="40F or below", token_id="t1", upper_bound=40)
        p = compute_bucket_probability(b, mu=35.0, sigma=2.0)
        assert p > 0.9

    def test_lower_open_mu_well_above(self):
        """Forecast well above bucket → low probability."""
        b = TempBucket(label="40F or below", token_id="t1", upper_bound=40)
        p = compute_bucket_probability(b, mu=50.0, sigma=2.0)
        assert p < 0.01

    def test_upper_open_mu_well_above(self):
        """Forecast well above lower bound → high probability."""
        b = TempBucket(label="47F or higher", token_id="t5", lower_bound=47)
        p = compute_bucket_probability(b, mu=52.0, sigma=2.0)
        assert p > 0.9

    def test_upper_open_mu_well_below(self):
        b = TempBucket(label="47F or higher", token_id="t5", lower_bound=47)
        p = compute_bucket_probability(b, mu=35.0, sigma=2.0)
        assert p < 0.01

    def test_bounded_mu_centered(self):
        """Forecast centered on bucket → moderate probability."""
        b = TempBucket(label="43-44F", token_id="t3", lower_bound=43, upper_bound=44)
        p = compute_bucket_probability(b, mu=43.5, sigma=2.0)
        # With sigma=2, 2-degree bucket centered on mu ≈ 38% (±0.75 sigma)
        assert 0.15 < p < 0.55

    def test_bounded_mu_far_away(self):
        b = TempBucket(label="43-44F", token_id="t3", lower_bound=43, upper_bound=44)
        p = compute_bucket_probability(b, mu=60.0, sigma=2.0)
        assert p < 0.001

    def test_continuity_correction(self):
        """Verify continuity correction: bucket "43-44F" uses [42.5, 44.5)."""
        b = TempBucket(label="43-44F", token_id="t3", lower_bound=43, upper_bound=44)
        # With mu=42.5, sigma very small → prob should be ~0.5 (right at lower boundary)
        p = compute_bucket_probability(b, mu=42.5, sigma=0.01)
        assert abs(p - 0.5) < 0.1

    def test_zero_sigma_point_mass(self):
        """Zero sigma → point mass at mu."""
        b = TempBucket(label="43-44F", token_id="t3", lower_bound=43, upper_bound=44)
        p_in = compute_bucket_probability(b, mu=43.5, sigma=0.0)
        assert p_in == 1.0
        p_out = compute_bucket_probability(b, mu=50.0, sigma=0.0)
        assert p_out == 0.0


# ===========================================================================
# All-Bucket Probability Normalization
# ===========================================================================

class TestAllBucketProbabilities:
    def test_sum_to_one(self):
        buckets = _make_standard_buckets()
        probs = compute_all_bucket_probabilities(buckets, mu=43.5, sigma=2.5)
        assert abs(sum(probs) - 1.0) < 1e-9

    def test_sum_to_one_extreme_mu(self):
        buckets = _make_standard_buckets()
        # mu far above all buckets
        probs = compute_all_bucket_probabilities(buckets, mu=80.0, sigma=2.0)
        assert abs(sum(probs) - 1.0) < 1e-9
        # Last bucket (47+) should dominate
        assert probs[-1] > 0.99

    def test_sum_to_one_extreme_low(self):
        buckets = _make_standard_buckets()
        probs = compute_all_bucket_probabilities(buckets, mu=10.0, sigma=2.0)
        assert abs(sum(probs) - 1.0) < 1e-9
        # First bucket (<=40) should dominate
        assert probs[0] > 0.99

    def test_peaked_on_center(self):
        """Forecast at 43.5 should peak on the 43-44F bucket."""
        buckets = _make_standard_buckets()
        probs = compute_all_bucket_probabilities(buckets, mu=43.5, sigma=2.0)
        center_idx = 2  # "43-44F"
        assert probs[center_idx] == max(probs)

    def test_large_sigma_flattens(self):
        """Large sigma → more uniform distribution."""
        buckets = _make_standard_buckets()
        tight = compute_all_bucket_probabilities(buckets, mu=43.5, sigma=1.0)
        wide = compute_all_bucket_probabilities(buckets, mu=43.5, sigma=6.0)
        # Center bucket should be more concentrated with tight sigma
        assert tight[2] > wide[2]
        # Tails should be larger with wide sigma
        assert wide[0] > tight[0]
        assert wide[-1] > tight[-1]

    def test_correct_bucket_count(self):
        buckets = _make_standard_buckets()
        probs = compute_all_bucket_probabilities(buckets, mu=43.5, sigma=2.5)
        assert len(probs) == 5

    def test_all_non_negative(self):
        buckets = _make_standard_buckets()
        for mu in [30, 40, 43.5, 50, 70]:
            for sigma in [1.0, 2.5, 5.0, 10.0]:
                probs = compute_all_bucket_probabilities(buckets, mu, sigma)
                assert all(p >= 0 for p in probs)


# ===========================================================================
# EV and Edge Calculation
# ===========================================================================

class TestEVCalculation:
    def test_positive_edge(self):
        edge = compute_edge_bps(0.35, 0.22)
        assert edge == 1300.0

    def test_negative_edge(self):
        edge = compute_edge_bps(0.20, 0.35)
        assert edge == -1500.0

    def test_zero_edge(self):
        edge = compute_edge_bps(0.50, 0.50)
        assert edge == 0.0

    def test_ev_positive(self):
        ev = compute_bucket_ev(0.35, 0.22)
        assert abs(ev - 0.13) < 1e-9

    def test_ev_negative(self):
        ev = compute_bucket_ev(0.20, 0.35)
        assert abs(ev - (-0.15)) < 1e-9


class TestEvaluateAllBuckets:
    def test_one_tradable(self):
        buckets = _make_standard_buckets()
        probs = [0.03, 0.12, 0.35, 0.30, 0.20]
        prices = [0.05, 0.10, 0.22, 0.35, 0.28]
        results = evaluate_all_buckets(buckets, probs, prices, min_edge_bps=300.0)

        assert len(results) == 5
        # Bucket 2 (43-44F): edge = (0.35 - 0.22) * 10000 = 1300 bps → tradable
        idx, edge, ev, tradable, reason = results[2]
        assert idx == 2
        assert edge == 1300.0
        assert tradable is True
        assert reason is None

    def test_below_threshold(self):
        buckets = _make_standard_buckets()
        probs = [0.03, 0.12, 0.24, 0.35, 0.26]
        prices = [0.05, 0.10, 0.22, 0.35, 0.28]
        results = evaluate_all_buckets(buckets, probs, prices, min_edge_bps=300.0)

        # Bucket 2: edge = (0.24 - 0.22) * 10000 = 200 bps → below threshold
        _, edge, _, tradable, reason = results[2]
        assert edge == 200.0
        assert tradable is False
        assert "edge" in reason

    def test_invalid_price(self):
        buckets = _make_standard_buckets()
        probs = [0.1] * 5
        prices = [0.0, 0.2, 0.3, 0.3, 0.2]  # first price is 0
        results = evaluate_all_buckets(buckets, probs, prices)
        _, _, _, tradable, reason = results[0]
        assert tradable is False
        assert "invalid_price" in reason


# ===========================================================================
# Kelly Sizing
# ===========================================================================

class TestKellySizing:
    def test_positive_edge(self):
        size = kelly_size(model_prob=0.40, market_price=0.25, base_size=3.0)
        assert size > 0
        assert size <= 8.0  # max_size default

    def test_zero_edge(self):
        size = kelly_size(model_prob=0.25, market_price=0.25, base_size=3.0)
        assert size == 0.0

    def test_negative_edge(self):
        size = kelly_size(model_prob=0.10, market_price=0.30, base_size=3.0)
        assert size == 0.0

    def test_max_size_cap(self):
        size = kelly_size(model_prob=0.90, market_price=0.10, base_size=100.0, max_size=5.0)
        assert size <= 5.0

    def test_invalid_price(self):
        assert kelly_size(0.5, 0.0, 3.0) == 0.0
        assert kelly_size(0.5, 1.0, 3.0) == 0.0
        assert kelly_size(0.0, 0.5, 3.0) == 0.0

    def test_scales_with_edge(self):
        """Higher edge → larger position."""
        small_edge = kelly_size(0.30, 0.25, 3.0)
        big_edge = kelly_size(0.50, 0.25, 3.0)
        assert big_edge > small_edge

    def test_kelly_scale_effect(self):
        """Smaller kelly_scale → smaller position."""
        full = kelly_size(0.40, 0.25, 3.0, kelly_scale=0.50)
        half = kelly_size(0.40, 0.25, 3.0, kelly_scale=0.25)
        assert full > half


# ===========================================================================
# Weather Confidence
# ===========================================================================

class TestWeatherConfidence:
    def test_perfect_conditions(self):
        c = compute_weather_confidence(
            liquidity=3000, market_data_age_seconds=10,
            forecast_age_minutes=15, lead_hours=36.0, sigma=1.5,
        )
        assert c >= 0.9

    def test_poor_conditions(self):
        c = compute_weather_confidence(
            liquidity=50, market_data_age_seconds=200,
            forecast_age_minutes=200, lead_hours=200.0, sigma=8.0,
        )
        assert c < 0.15

    def test_bounded(self):
        for liq in [0, 100, 1000, 5000]:
            for age in [5, 30, 120, 300]:
                c = compute_weather_confidence(
                    liquidity=liq, market_data_age_seconds=age,
                    forecast_age_minutes=age, lead_hours=48.0, sigma=2.5,
                )
                assert 0.0 <= c <= 1.0


# ===========================================================================
# Forecast Blending
# ===========================================================================

class TestForecastBlending:
    def test_single_source(self):
        mu, sigma = blend_forecasts([(44.0, 2.5)])
        assert mu == 44.0
        assert sigma == 2.5

    def test_two_agreeing_sources(self):
        mu, sigma = blend_forecasts([(44.0, 2.5), (44.0, 2.5)])
        assert abs(mu - 44.0) < 0.01
        # No inter-model disagreement → sigma stays ~2.5
        assert abs(sigma - 2.5) < 0.2

    def test_disagreement_inflates_sigma(self):
        """When sources disagree, sigma should increase."""
        mu_agree, sigma_agree = blend_forecasts([(44.0, 2.5), (44.0, 2.5)])
        mu_disagree, sigma_disagree = blend_forecasts([(44.0, 2.5), (50.0, 2.5)])
        assert sigma_disagree > sigma_agree

    def test_weighted_blending(self):
        mu, sigma = blend_forecasts(
            [(40.0, 2.0), (50.0, 3.0)],
            weights=[0.7, 0.3],
        )
        expected_mu = 0.7 * 40.0 + 0.3 * 50.0  # 43.0
        assert abs(mu - expected_mu) < 0.01

    def test_empty_forecasts(self):
        mu, sigma = blend_forecasts([])
        assert mu == 0.0
        assert sigma == _SIGMA_CEILING

    def test_sigma_floor_enforced(self):
        mu, sigma = blend_forecasts([(44.0, 0.0)])
        assert sigma >= _SIGMA_FLOOR


# ===========================================================================
# Contiguous Bucket Validation (parser enhancement)
# ===========================================================================

class TestContiguousBucketValidation:
    def test_valid_contiguous(self):
        buckets = _make_standard_buckets()
        assert validate_buckets(buckets) is None

    def test_gap_detected(self):
        """Missing 43-44F bucket creates a gap from 42 to 45."""
        buckets = [
            TempBucket(label="40F or below", token_id="t1", upper_bound=40),
            TempBucket(label="41-42F", token_id="t2", lower_bound=41, upper_bound=42),
            # 43-44F missing!
            TempBucket(label="45-46F", token_id="t4", lower_bound=45, upper_bound=46),
            TempBucket(label="47F or higher", token_id="t5", lower_bound=47),
        ]
        err = validate_buckets(buckets)
        assert err is not None
        assert "bucket_gap" in err

    def test_overlap_detected(self):
        """Overlapping bounds: 40-43 and 42-44 overlap at 42-43."""
        buckets = [
            TempBucket(label="39 or below", token_id="t1", upper_bound=39),
            TempBucket(label="40-43F", token_id="t2", lower_bound=40, upper_bound=43),
            TempBucket(label="42-44F", token_id="t3", lower_bound=42, upper_bound=44),
            TempBucket(label="45 or higher", token_id="t4", lower_bound=45),
        ]
        err = validate_buckets(buckets)
        assert err is not None
        assert "bucket_overlap" in err

    def test_valid_wide_buckets(self):
        """Wider buckets (e.g. 5-degree spans) can still be contiguous."""
        buckets = [
            TempBucket(label="30 or below", token_id="t1", upper_bound=30),
            TempBucket(label="31-35F", token_id="t2", lower_bound=31, upper_bound=35),
            TempBucket(label="36-40F", token_id="t3", lower_bound=36, upper_bound=40),
            TempBucket(label="41 or higher", token_id="t4", lower_bound=41),
        ]
        assert validate_buckets(buckets) is None


# ===========================================================================
# Integration: Full Pipeline (mu → probs → EV → size)
# ===========================================================================

class TestFullPricingPipeline:
    """End-to-end: forecast → probabilities → EV → sizing."""

    def test_pipeline(self):
        buckets = _make_standard_buckets()
        mu = 43.5  # forecast high
        sigma = calibrate_sigma(36.0, 3, StationType.COASTAL)  # ~2.43

        # Probabilities
        probs = compute_all_bucket_probabilities(buckets, mu, sigma)
        assert abs(sum(probs) - 1.0) < 1e-9
        assert len(probs) == 5

        # Market prices (simulated: center bucket underpriced)
        prices = [0.05, 0.10, 0.22, 0.35, 0.28]

        # EV evaluation
        results = evaluate_all_buckets(buckets, probs, prices, min_edge_bps=300.0)

        # Find tradable buckets
        tradable = [(i, edge, ev) for i, edge, ev, is_t, _ in results if is_t]

        # The center bucket (43-44F, idx=2) should have positive edge
        # since mu=43.5 with tight sigma means high probability there
        center_prob = probs[2]
        center_edge = compute_edge_bps(center_prob, 0.22)

        if center_edge >= 300.0:
            # Size it
            size = kelly_size(center_prob, 0.22, base_size=3.0)
            assert size > 0
            assert size <= 8.0

    def test_pipeline_no_tradable(self):
        """Fair prices → no tradable buckets."""
        buckets = _make_standard_buckets()
        mu, sigma = 43.5, 2.5
        probs = compute_all_bucket_probabilities(buckets, mu, sigma)
        # Set market prices = model probs (fair market)
        results = evaluate_all_buckets(buckets, probs, probs, min_edge_bps=300.0)
        tradable = [r for r in results if r[3]]
        assert len(tradable) == 0
