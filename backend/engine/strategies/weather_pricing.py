"""Weather strategy pricing engine.

Pure functions for:
  1. Normal CDF (math.erf, no scipy)
  2. Bucket probability calculation from forecast distribution
  3. Sigma calibration by lead time, season, station type
  4. EV calculation per bucket
  5. Quarter-Kelly sizing
  6. Weather-specific confidence scoring

All functions are deterministic, side-effect-free, and allocation-minimal.
No execution logic lives here.
"""

import math
from typing import List, Optional, Tuple

from engine.strategies.weather_models import (
    TempBucket, SigmaCalibration, StationType, Season,
)


# ---- Normal CDF ----

def normal_cdf(x: float) -> float:
    """Standard normal CDF via math.erf. Accurate to ~1e-7.

    Replicates sniper_pricing.normal_cdf for self-containment.
    """
    return 0.5 * (1.0 + math.erf(x / 1.4142135623730951))


# ---- Season Determination ----

def get_season(month: int) -> Season:
    """Map calendar month (1-12) to meteorological season."""
    if month in (12, 1, 2):
        return Season.WINTER
    if month in (3, 4, 5):
        return Season.SPRING
    if month in (6, 7, 8):
        return Season.SUMMER
    return Season.FALL


# ---- Sigma Calibration ----

# Default sigma table (degrees F) by lead-time bracket.
# Based on NWS MOS published accuracy: ~2F at 1 day, ~3.5F at 3 days, ~5F at 5 days.
_DEFAULT_SIGMA_TABLE = {
    "0_24": 1.8,
    "24_48": 2.7,
    "48_72": 3.4,
    "72_120": 4.8,
    "120_168": 6.2,
}

_DEFAULT_SEASONAL_FACTORS = {
    "winter": 1.15,
    "spring": 1.0,
    "summer": 0.88,
    "fall": 1.02,
}

_STATION_TYPE_FACTORS = {
    StationType.COASTAL: 0.90,
    StationType.INLAND: 1.10,
}

# Absolute floor / ceiling for sigma to prevent nonsensical values
_SIGMA_FLOOR = 0.5    # degrees F
_SIGMA_CEILING = 15.0  # degrees F


def _lead_hours_to_bracket(lead_hours: float) -> str:
    """Map lead time in hours to the calibration bracket key."""
    if lead_hours <= 24:
        return "0_24"
    if lead_hours <= 48:
        return "24_48"
    if lead_hours <= 72:
        return "48_72"
    if lead_hours <= 120:
        return "72_120"
    return "120_168"


def calibrate_sigma(
    lead_hours: float,
    month: int,
    station_type: StationType,
    calibration: Optional[SigmaCalibration] = None,
    overconfidence_multiplier: float = 1.0,
    max_adjustment_pct: float = 0.25,
    min_samples_for_cal: int = 30,
) -> tuple:
    """Compute calibrated forecast sigma in degrees F.

    Returns ``(sigma, trace)`` where *trace* is a dict describing every
    step of the pipeline so callers can log / display it.
    """
    bracket = _lead_hours_to_bracket(lead_hours)
    default_sigma = _DEFAULT_SIGMA_TABLE[bracket]

    source = "default"
    cal_sample_count = 0
    cal_raw_sigma = None
    capped = False

    if calibration and calibration.sample_count >= min_samples_for_cal:
        raw_cal = calibration.sigma_by_lead_hours.get(bracket, default_sigma)
        cal_raw_sigma = raw_cal
        cal_sample_count = calibration.sample_count
        lower = default_sigma * (1.0 - max_adjustment_pct)
        upper = default_sigma * (1.0 + max_adjustment_pct)
        base_sigma = max(lower, min(raw_cal, upper))
        capped = (raw_cal < lower or raw_cal > upper)
        source = "calibrated_capped" if capped else "calibrated"
        seasonal_table = calibration.seasonal_factors
        type_factor = calibration.station_type_factor
    elif calibration and calibration.sample_count > 0:
        cal_raw_sigma = calibration.sigma_by_lead_hours.get(bracket, default_sigma)
        cal_sample_count = calibration.sample_count
        weight = calibration.sample_count / float(min_samples_for_cal)
        base_sigma = weight * cal_raw_sigma + (1 - weight) * default_sigma
        source = "blended"
        seasonal_table = _DEFAULT_SEASONAL_FACTORS
        type_factor = _STATION_TYPE_FACTORS.get(station_type, 1.0)
    else:
        base_sigma = default_sigma
        seasonal_table = _DEFAULT_SEASONAL_FACTORS
        type_factor = _STATION_TYPE_FACTORS.get(station_type, 1.0)

    season = get_season(month)
    seasonal_factor = seasonal_table.get(season.value, 1.0)
    sigma_before_oc = base_sigma * seasonal_factor * type_factor

    # Apply overconfidence multiplier (temporary global widening)
    sigma_after_oc = sigma_before_oc * overconfidence_multiplier

    final = max(_SIGMA_FLOOR, min(sigma_after_oc, _SIGMA_CEILING))

    trace = {
        "bracket": bracket,
        "default_sigma": round(default_sigma, 3),
        "base_sigma": round(base_sigma, 3),
        "seasonal_factor": round(seasonal_factor, 3),
        "type_factor": round(type_factor, 3),
        "sigma_before_oc": round(sigma_before_oc, 3),
        "overconfidence_multiplier": overconfidence_multiplier,
        "sigma_after_oc": round(sigma_after_oc, 3),
        "final_sigma": round(final, 3),
        "source": source,
        "capped": capped,
        "calibration_raw_sigma": round(cal_raw_sigma, 3) if cal_raw_sigma is not None else None,
        "sample_count": cal_sample_count,
    }
    return final, trace


# ---- Bucket Probability ----

def compute_bucket_probability(
    bucket: TempBucket,
    mu: float,
    sigma: float,
) -> float:
    """Probability that the daily high falls in this bucket.

    Uses continuity correction: resolution is to nearest whole degree F,
    so a bucket "43-44F" captures anything in [42.5, 44.5).

    For boundary buckets:
      "40F or below"  → P(T <= 40.5)
      "47F or higher" → P(T >= 46.5)
    """
    if sigma <= 0:
        # Degenerate: point mass at mu
        if bucket.lower_bound is None and bucket.upper_bound is not None:
            return 1.0 if mu <= bucket.upper_bound else 0.0
        if bucket.upper_bound is None and bucket.lower_bound is not None:
            return 1.0 if mu >= bucket.lower_bound else 0.0
        if bucket.lower_bound is not None and bucket.upper_bound is not None:
            return 1.0 if bucket.lower_bound <= mu <= bucket.upper_bound else 0.0
        return 1.0  # both bounds None = catch-all

    # Continuity correction: +-0.5 around whole-degree boundaries
    if bucket.lower_bound is None:
        # "X or below": P(T <= upper + 0.5)
        z_upper = (bucket.upper_bound + 0.5 - mu) / sigma
        return normal_cdf(z_upper)

    if bucket.upper_bound is None:
        # "X or higher": P(T >= lower - 0.5)
        z_lower = (bucket.lower_bound - 0.5 - mu) / sigma
        return 1.0 - normal_cdf(z_lower)

    # Bounded: P(lower - 0.5 <= T <= upper + 0.5)
    z_lower = (bucket.lower_bound - 0.5 - mu) / sigma
    z_upper = (bucket.upper_bound + 0.5 - mu) / sigma
    prob = normal_cdf(z_upper) - normal_cdf(z_lower)
    return max(prob, 0.0)


# ---- Non-Temperature Probability Models ----

# Precipitation uses a gamma distribution approximation.
# Most daily precip is 0 or near 0, with a long right tail.
# We model P(precip > threshold) using a simplified exceedance curve:
#   P(X > t) ~ exp(-t / scale) for t > 0, scaled by P(rain).

_PRECIP_SIGMA_TABLE = {
    "0_24": 0.3,     # inches uncertainty at 1 day lead
    "24_48": 0.5,
    "48_72": 0.7,
    "72_120": 1.0,
    "120_168": 1.5,
}

_SNOW_SIGMA_TABLE = {
    "0_24": 1.0,     # inches uncertainty at 1 day lead
    "24_48": 2.0,
    "48_72": 3.0,
    "72_120": 4.0,
    "120_168": 5.0,
}

_WIND_SIGMA_TABLE = {
    "0_24": 3.0,     # mph uncertainty at 1 day lead
    "24_48": 5.0,
    "48_72": 7.0,
    "72_120": 10.0,
    "120_168": 12.0,
}


def get_amount_sigma(
    market_type: str,
    lead_hours: float,
    overconfidence_multiplier: float = 1.0,
) -> tuple:
    """Get forecast sigma for non-temperature market types.

    Returns ``(sigma, trace)`` with full pipeline visibility.
    """
    tables = {
        "precipitation": _PRECIP_SIGMA_TABLE,
        "snowfall": _SNOW_SIGMA_TABLE,
        "wind": _WIND_SIGMA_TABLE,
    }
    table = tables.get(market_type, _PRECIP_SIGMA_TABLE)
    bracket = _lead_hours_to_bracket(lead_hours)
    base_sigma = table.get(bracket, list(table.values())[-1])

    sigma_after_oc = base_sigma * overconfidence_multiplier
    final = max(0.01, sigma_after_oc)

    trace = {
        "bracket": bracket,
        "default_sigma": round(base_sigma, 3),
        "base_sigma": round(base_sigma, 3),
        "overconfidence_multiplier": overconfidence_multiplier,
        "sigma_after_oc": round(sigma_after_oc, 3),
        "final_sigma": round(final, 3),
        "source": "default",
        "capped": False,
        "sample_count": 0,
    }
    return final, trace


def compute_amount_bucket_probability(
    bucket: "TempBucket",
    forecast_amount: float,
    sigma: float,
    market_type: str = "precipitation",
) -> float:
    """Probability that the measured amount falls in this bucket.

    Works for precipitation (inches), snowfall (inches), and wind (mph).
    Uses normal CDF approximation around the forecast amount.

    For precipitation: forecast_amount is forecast total precip in inches.
    For snow: forecast total snowfall in inches.
    For wind: forecast max wind speed in mph.
    """
    if sigma <= 0:
        if bucket.lower_bound is None and bucket.upper_bound is not None:
            return 1.0 if forecast_amount <= bucket.upper_bound else 0.0
        if bucket.upper_bound is None and bucket.lower_bound is not None:
            return 1.0 if forecast_amount >= bucket.lower_bound else 0.0
        if bucket.lower_bound is not None and bucket.upper_bound is not None:
            return 1.0 if bucket.lower_bound <= forecast_amount <= bucket.upper_bound else 0.0
        return 1.0

    # Use normal CDF for all types (simple and testable)
    # No continuity correction for continuous measurements
    if bucket.lower_bound is None:
        z = (bucket.upper_bound - forecast_amount) / sigma
        return normal_cdf(z)

    if bucket.upper_bound is None:
        z = (bucket.lower_bound - forecast_amount) / sigma
        return 1.0 - normal_cdf(z)

    z_lo = (bucket.lower_bound - forecast_amount) / sigma
    z_hi = (bucket.upper_bound - forecast_amount) / sigma
    return max(normal_cdf(z_hi) - normal_cdf(z_lo), 0.0)




def compute_all_bucket_probabilities(
    buckets: List[TempBucket],
    mu: float,
    sigma: float,
) -> List[float]:
    """Compute and normalize probabilities across all buckets.

    Raw probabilities from the normal distribution may not sum exactly to 1.0
    due to floating-point precision and continuity corrections. We normalize
    so downstream EV math is consistent.

    Returns list of probabilities in same order as input buckets.
    """
    raw = [compute_bucket_probability(b, mu, sigma) for b in buckets]
    total = sum(raw)

    if total <= 0:
        # Degenerate: uniform fallback (should not happen with valid mu/sigma)
        n = len(buckets)
        return [1.0 / n] * n if n > 0 else []

    # Normalize
    return [p / total for p in raw]


# ---- EV Calculation ----

def compute_edge_bps(model_prob: float, market_price: float) -> float:
    """Edge in basis points. Positive = model thinks bucket is underpriced."""
    return round((model_prob - market_price) * 10_000, 2)


def compute_bucket_ev(model_prob: float, market_price: float) -> float:
    """Expected value for buying one share of this bucket.

    EV = P_model * (1 - market_price) - (1 - P_model) * market_price
       = P_model - market_price

    (Because payout is $1 on correct outcome, $0 otherwise.)
    """
    return model_prob - market_price


def evaluate_all_buckets(
    buckets: List[TempBucket],
    probabilities: List[float],
    market_prices: List[float],
    min_edge_bps: float = 300.0,
) -> List[Tuple[int, float, float, bool, Optional[str]]]:
    """Evaluate EV across all buckets.

    Args:
        buckets: parsed temperature buckets
        probabilities: normalized model probabilities (same order)
        market_prices: current Polymarket prices (same order)
        min_edge_bps: minimum edge threshold in basis points

    Returns list of tuples:
        (index, edge_bps, ev, is_tradable, rejection_reason)
    """
    results = []
    for i, (bucket, prob, price) in enumerate(zip(buckets, probabilities, market_prices)):
        edge_bps = compute_edge_bps(prob, price)
        ev = compute_bucket_ev(prob, price)

        if price <= 0 or price >= 1.0:
            results.append((i, edge_bps, ev, False, f"invalid_price ({price})"))
        elif edge_bps < min_edge_bps:
            results.append((i, edge_bps, ev, False,
                            f"edge {edge_bps:.0f}bps < min {min_edge_bps:.0f}bps"))
        else:
            results.append((i, edge_bps, ev, True, None))

    return results


# ---- Position Sizing ----

def kelly_size(
    model_prob: float,
    market_price: float,
    base_size: float,
    kelly_scale: float = 0.25,
    max_size: float = 8.0,
) -> float:
    """Quarter-Kelly position sizing.

    Kelly fraction = (p - q*b) / b where b = odds = (1/price - 1)
    Simplified for binary payouts: kelly_f = (p - price) / (1 - price)

    We use fractional Kelly (kelly_scale) for safety.
    Returns 0.0 if edge is non-positive or inputs are invalid.
    """
    if model_prob <= 0 or market_price <= 0 or market_price >= 1.0:
        return 0.0

    edge = model_prob - market_price
    if edge <= 0:
        return 0.0

    kelly_f = edge / (1.0 - market_price)

    # Apply fractional Kelly and base size
    raw_size = base_size * kelly_f * kelly_scale / 0.25  # normalize: at kelly_scale=0.25, 100% kelly → base_size
    # Simpler: direct application
    raw_size = base_size * min(kelly_f, 1.0) * kelly_scale * 4.0
    # At kelly_f=1.0, kelly_scale=0.25 → raw_size = base_size
    # At kelly_f=0.5, kelly_scale=0.25 → raw_size = base_size * 0.5

    return max(0.0, min(round(raw_size, 2), max_size))


# ---- Confidence Score ----

def compute_weather_confidence(
    liquidity: float,
    market_data_age_seconds: float,
    forecast_age_minutes: float,
    lead_hours: float,
    sigma: float,
    min_lead_hours: float = 4.0,
    max_lead_hours: float = 168.0,
) -> float:
    """Weather-specific execution confidence score (0 to 1).

    Five factors:
      - Liquidity depth      (0 - 0.20)
      - Market data freshness (0 - 0.20)
      - Forecast freshness    (0 - 0.20)
      - Lead time quality     (0 - 0.20)  sweet spot: 12-72h
      - Sigma quality         (0 - 0.20)  lower sigma = higher confidence
    """
    score = 0.0

    # Liquidity (weather markets are thinner)
    if liquidity > 2000:
        score += 0.20
    elif liquidity > 1000:
        score += 0.16
    elif liquidity > 500:
        score += 0.12
    elif liquidity > 200:
        score += 0.06

    # Market data freshness
    if market_data_age_seconds < 30:
        score += 0.20
    elif market_data_age_seconds < 60:
        score += 0.15
    elif market_data_age_seconds < 120:
        score += 0.08

    # Forecast freshness
    if forecast_age_minutes < 30:
        score += 0.20
    elif forecast_age_minutes < 60:
        score += 0.15
    elif forecast_age_minutes < 120:
        score += 0.08

    # Lead time quality — sweet spot is 12-72h
    if min_lead_hours < lead_hours < max_lead_hours:
        sweet_low, sweet_high = 12.0, 72.0
        if sweet_low <= lead_hours <= sweet_high:
            score += 0.20
        elif lead_hours < sweet_low:
            # Close to resolution: still okay but less confidence
            score += 0.12
        else:
            # Far out: confidence degrades
            ratio = 1.0 - (lead_hours - sweet_high) / (max_lead_hours - sweet_high)
            score += 0.20 * max(ratio, 0)

    # Sigma quality — lower sigma = more confident forecast
    if sigma < 2.0:
        score += 0.20
    elif sigma < 3.0:
        score += 0.16
    elif sigma < 4.5:
        score += 0.10
    elif sigma < 6.0:
        score += 0.05

    return round(min(score, 1.0), 3)


# ---- Forecast Blending ----

def blend_forecasts(
    forecasts: List[Tuple[float, float]],
    weights: Optional[List[float]] = None,
) -> Tuple[float, float]:
    """Blend multiple forecast sources into a single (mu, sigma).

    Args:
        forecasts: list of (forecast_high_f, source_sigma) pairs
        weights: optional weights (defaults to equal). Must sum > 0.

    Returns:
        (blended_mu, blended_sigma)

    The blended sigma includes an inter-model disagreement term that
    naturally inflates uncertainty when sources disagree.
    """
    n = len(forecasts)
    if n == 0:
        return 0.0, _SIGMA_CEILING

    if n == 1:
        mu, sigma = forecasts[0]
        return round(mu, 2), round(max(sigma, _SIGMA_FLOOR), 4)

    if weights is None:
        weights = [1.0 / n] * n
    else:
        w_sum = sum(weights)
        if w_sum <= 0:
            weights = [1.0 / n] * n
        else:
            weights = [w / w_sum for w in weights]

    # Blended mean
    mu = sum(w * f[0] for w, f in zip(weights, forecasts))

    # Blended variance = weighted avg of individual variances + inter-model disagreement
    var_within = sum(w * f[1] ** 2 for w, f in zip(weights, forecasts))
    var_between = sum(w * (f[0] - mu) ** 2 for w, f in zip(weights, forecasts))
    sigma = math.sqrt(var_within + var_between)

    return round(mu, 2), round(max(sigma, _SIGMA_FLOOR), 4)
