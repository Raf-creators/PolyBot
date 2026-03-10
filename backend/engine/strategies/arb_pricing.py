"""Composable pricing models for arbitrage edge calculation.

Each function is a standalone, deterministic estimator.
Designed for easy replacement when full order-book data becomes available.
"""

from datetime import datetime, timezone


def estimate_fees(
    yes_price: float,
    no_price: float,
    size: float,
    maker_taker_rate: float = 0.002,
    resolution_fee_rate: float = 0.02,
) -> float:
    """Total fee estimate in basis points of 1.0 payout.

    Components:
      - Trading fees: maker_taker_rate applied to total acquisition cost per leg.
      - Resolution fee: resolution_fee_rate applied to gross edge (profit).
    """
    total_cost = yes_price + no_price
    trading_fees = total_cost * maker_taker_rate
    gross_edge = max(1.0 - total_cost, 0)
    resolution_fee = gross_edge * resolution_fee_rate
    return round((trading_fees + resolution_fee) * 10000, 2)


def estimate_slippage(
    liquidity: float,
    volume: float,
    size: float,
    base_bps: float = 5.0,
) -> float:
    """Proxy slippage in basis points.

    Uses linear impact model: impact = size / liquidity.
    TODO: Replace with order-book-depth model when WS book data is available.
    """
    if liquidity <= 0:
        return round(base_bps * 10, 2)
    impact_bps = (size / max(liquidity, 1)) * 1000
    return round(base_bps + impact_bps, 2)


def estimate_execution_penalty(
    data_age_seconds: float,
    confidence: float,
    base_bps: float = 3.0,
) -> float:
    """Penalty for execution uncertainty in basis points.

    Higher when data is stale or confidence is low.
    """
    age_penalty = min(data_age_seconds / 30, 10)  # cap at 10 bps
    confidence_penalty = base_bps * max(1.0 - confidence, 0)
    return round(base_bps + age_penalty + confidence_penalty, 2)


def compute_confidence(
    liquidity: float,
    data_age_seconds: float,
    spread_proxy: float,
    volume: float,
) -> float:
    """Execution confidence score (0 to 1). Deterministic and explainable.

    Four factors scored independently and summed:
      - Liquidity depth   (0 - 0.30)
      - Data freshness     (0 - 0.30)
      - Spread tightness   (0 - 0.20)
      - Volume activity    (0 - 0.20)
    """
    score = 0.0

    # Liquidity depth
    if liquidity > 10000:
        score += 0.30
    elif liquidity > 2000:
        score += 0.20
    elif liquidity > 500:
        score += 0.15
    elif liquidity > 100:
        score += 0.05

    # Freshness
    if data_age_seconds < 30:
        score += 0.30
    elif data_age_seconds < 60:
        score += 0.20
    elif data_age_seconds < 120:
        score += 0.10

    # Spread tightness (spread_proxy = |1.0 - (yes + no)|)
    if spread_proxy < 0.02:
        score += 0.20
    elif spread_proxy < 0.05:
        score += 0.15
    elif spread_proxy < 0.10:
        score += 0.10

    # Volume activity
    if volume > 100000:
        score += 0.20
    elif volume > 10000:
        score += 0.15
    elif volume > 1000:
        score += 0.10
    elif volume > 100:
        score += 0.05

    return round(min(score, 1.0), 3)


def compute_data_age(updated_at: str) -> float:
    """Seconds since the market data was last updated."""
    try:
        dt = datetime.fromisoformat(updated_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - dt).total_seconds(), 0)
    except Exception:
        return 9999.0
