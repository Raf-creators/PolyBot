"""Lightweight pricing models for crypto sniper fair-probability estimation.

Uses math.erf for normal CDF — no scipy dependency.
All functions are pure, deterministic, and allocation-free.
"""

import math
from collections import deque
from typing import Optional, Tuple

# Seconds in a year (365.25 days)
_SECONDS_PER_YEAR = 31_536_000.0


def normal_cdf(x: float) -> float:
    """Standard normal CDF via math.erf. Accurate to ~1e-7."""
    return 0.5 * (1.0 + math.erf(x / 1.4142135623730951))


def compute_fair_probability(
    spot: float,
    strike: float,
    vol: float,
    tte_seconds: float,
    direction: str,
    momentum: float = 0.0,
    momentum_weight: float = 0.3,
    vol_floor: float = 0.10,
) -> float:
    """Fair probability that price will be above/below strike at expiry.

    Simplified Black-Scholes digital option model:
        d2 = [ln(S/K) + drift*tau] / (sigma * sqrt(tau))
        P(above) = Phi(d2)
        P(below) = 1 - Phi(d2)

    Returns probability clamped to [0.001, 0.999].
    """
    if strike <= 0 or spot <= 0 or tte_seconds <= 0:
        return 0.5

    tau = tte_seconds / _SECONDS_PER_YEAR
    sigma = max(vol, vol_floor)
    sqrt_tau = math.sqrt(tau)
    sigma_sqrt_tau = sigma * sqrt_tau

    if sigma_sqrt_tau < 1e-12:
        # Near-zero denominator: if S > K → ~1.0, else ~0.0
        p = 1.0 if spot > strike else 0.0
    else:
        # Momentum is a fractional return (same scale as ln(S/K)),
        # so it's added directly to the numerator — NOT scaled by tau,
        # which would make it negligible at short horizons.
        drift = momentum_weight * momentum
        d2 = (math.log(spot / strike) + drift) / sigma_sqrt_tau
        p = normal_cdf(d2)

    if direction == "below":
        p = 1.0 - p

    return max(0.001, min(p, 0.999))


def compute_realized_volatility(
    prices: deque,
    min_samples: int = 30,
) -> Optional[float]:
    """Annualized realized volatility from (timestamp, price) deque.

    Returns None if insufficient samples.
    """
    n = len(prices)
    if n < min_samples:
        return None

    # Compute log returns and time span in a single pass
    sum_r = 0.0
    sum_r2 = 0.0
    count = 0

    prev_p = prices[0][1]
    for i in range(1, n):
        t, p = prices[i]
        if prev_p > 0 and p > 0:
            r = math.log(p / prev_p)
            sum_r += r
            sum_r2 += r * r
            count += 1
        prev_p = p

    if count < 2:
        return None

    # Variance of log returns
    mean_r = sum_r / count
    variance = (sum_r2 / count) - (mean_r * mean_r)
    if variance <= 0:
        return None

    std_r = math.sqrt(variance)

    # Annualize: scale by sqrt(samples_per_year)
    total_span = prices[-1][0] - prices[0][0]
    if total_span <= 0:
        return None
    avg_interval = total_span / count
    if avg_interval <= 0:
        return None
    samples_per_year = _SECONDS_PER_YEAR / avg_interval
    annualized_vol = std_r * math.sqrt(samples_per_year)

    return round(annualized_vol, 6)


def compute_momentum(
    prices: deque,
    lookback_seconds: float = 300.0,
) -> float:
    """Recent price momentum as fractional return over lookback window.

    Returns 0.0 if insufficient data.
    """
    if len(prices) < 2:
        return 0.0

    current_t, current_p = prices[-1]
    cutoff = current_t - lookback_seconds

    # Walk backwards to find oldest price within lookback
    oldest_p = None
    for t, p in prices:
        if t >= cutoff:
            oldest_p = p
            break

    if oldest_p is None or oldest_p <= 0 or current_p <= 0:
        return 0.0

    return (current_p - oldest_p) / oldest_p


def compute_signal_confidence(
    liquidity: float,
    data_age_seconds: float,
    spread: float,
    vol_quality: float,
    tte_seconds: float,
    min_tte: float = 30.0,
    max_tte: float = 900.0,
) -> float:
    """Execution confidence score (0 to 1).

    Five factors:
      - Liquidity depth   (0 - 0.25)
      - Data freshness    (0 - 0.25)
      - Spread tightness  (0 - 0.20)
      - Vol data quality  (0 - 0.15)
      - TTE quality       (0 - 0.15)
    """
    score = 0.0

    # Liquidity
    if liquidity > 5000:
        score += 0.25
    elif liquidity > 2000:
        score += 0.20
    elif liquidity > 500:
        score += 0.12
    elif liquidity > 100:
        score += 0.05

    # Freshness
    if data_age_seconds < 15:
        score += 0.25
    elif data_age_seconds < 30:
        score += 0.20
    elif data_age_seconds < 60:
        score += 0.10

    # Spread tightness
    if spread < 0.02:
        score += 0.20
    elif spread < 0.05:
        score += 0.15
    elif spread < 0.10:
        score += 0.08

    # Vol data quality (0-1 ratio of samples/required)
    if vol_quality >= 1.0:
        score += 0.15
    elif vol_quality >= 0.5:
        score += 0.08

    # TTE quality — sweet spot is mid-range
    if min_tte < tte_seconds < max_tte:
        mid = (min_tte + max_tte) / 2
        ratio = 1.0 - abs(tte_seconds - mid) / mid
        score += 0.15 * max(ratio, 0)

    return round(min(score, 1.0), 3)


def compute_edge_bps(fair_prob: float, market_prob: float) -> float:
    """Edge in basis points. Positive = model thinks market is cheap."""
    return round((fair_prob - market_prob) * 10_000, 2)
