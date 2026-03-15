"""Liquidity Service — computes per-market and per-event liquidity scores.

Scoring formula (0–100):
  - Spread component (40%): tighter spread → higher score
  - Depth component (30%): higher liquidity $ → higher score
  - Volume component (30%): higher 24h volume → higher score

The service aggregates individual token snapshots into weather-market-level
heatmap tiles grouped by condition_id (city + date).
"""

import logging
from typing import Dict, List, Optional

from models import MarketSnapshot

logger = logging.getLogger(__name__)

# Scoring parameters
SPREAD_WEIGHT = 0.40
DEPTH_WEIGHT = 0.30
VOLUME_WEIGHT = 0.30

# Reference values for normalization (approximate Polymarket weather market medians)
REF_SPREAD = 0.04       # 4c spread is "okay"
REF_DEPTH = 1000.0      # $1000 liquidity is "okay"
REF_VOLUME = 5000.0     # $5000 24h volume is "okay"


def compute_liquidity_score(
    spread: Optional[float],
    liquidity: float,
    volume_24h: float,
) -> float:
    """Compute a 0–100 liquidity score for a single token.

    Higher = more liquid. Capped at 100.
    """
    # Spread score: 0 spread → 100, REF_SPREAD → 50, 2*REF_SPREAD → 0
    if spread is not None and spread >= 0:
        spread_score = max(0, 100.0 * (1.0 - spread / (2 * REF_SPREAD)))
    else:
        spread_score = 0.0

    # Depth score: log-scale capped at 100
    depth_score = min(100.0, 100.0 * min(liquidity / REF_DEPTH, 2.0) / 2.0) if liquidity > 0 else 0.0

    # Volume score: log-scale capped at 100
    volume_score = min(100.0, 100.0 * min(volume_24h / REF_VOLUME, 2.0) / 2.0) if volume_24h > 0 else 0.0

    score = (
        SPREAD_WEIGHT * spread_score
        + DEPTH_WEIGHT * depth_score
        + VOLUME_WEIGHT * volume_score
    )
    return round(min(100.0, max(0.0, score)), 1)


def compute_market_liquidity(snap: MarketSnapshot) -> dict:
    """Compute liquidity metrics for a single MarketSnapshot."""
    spread = snap.spread
    if spread is None and snap.best_bid is not None and snap.best_ask is not None:
        spread = snap.best_ask - snap.best_bid

    score = compute_liquidity_score(spread, snap.liquidity, snap.volume_24h)

    return {
        "token_id": snap.token_id,
        "condition_id": snap.condition_id,
        "question": snap.question,
        "outcome": snap.outcome,
        "mid_price": snap.mid_price,
        "best_bid": snap.best_bid,
        "best_ask": snap.best_ask,
        "spread": round(spread, 6) if spread is not None else None,
        "liquidity": snap.liquidity,
        "volume_24h": snap.volume_24h,
        "liquidity_score": score,
        "updated_at": snap.updated_at,
    }


class LiquidityService:
    """Aggregates market data into liquidity heatmap tiles."""

    def __init__(self, state):
        self._state = state

    def get_heatmap(self, weather_classifications: Optional[Dict] = None) -> dict:
        """Build heatmap data from current market state.

        Returns:
            {
                "tiles": [...],     # per-condition tiles with aggregated scores
                "tokens": [...],    # per-token detail
                "summary": {...},   # overall stats
            }
        """
        all_tokens = []
        tiles_by_cid: Dict[str, dict] = {}

        # If weather classifications provided, build tiles from them
        if weather_classifications:
            for cid, cm in weather_classifications.items():
                buckets_data = []
                total_score = 0.0
                total_liquidity = 0.0
                total_volume = 0.0
                spreads = []
                n = 0

                for bucket in cm.buckets:
                    snap = self._state.get_market(bucket.token_id)
                    if not snap:
                        buckets_data.append({
                            "label": bucket.label,
                            "token_id": bucket.token_id,
                            "mid_price": None,
                            "spread": None,
                            "liquidity": 0,
                            "volume_24h": 0,
                            "liquidity_score": 0,
                        })
                        continue

                    metrics = compute_market_liquidity(snap)
                    all_tokens.append(metrics)
                    buckets_data.append({
                        "label": bucket.label,
                        "token_id": bucket.token_id,
                        "mid_price": snap.mid_price,
                        "spread": metrics["spread"],
                        "liquidity": snap.liquidity,
                        "volume_24h": snap.volume_24h,
                        "liquidity_score": metrics["liquidity_score"],
                    })

                    total_score += metrics["liquidity_score"]
                    total_liquidity += snap.liquidity
                    total_volume += snap.volume_24h
                    if metrics["spread"] is not None:
                        spreads.append(metrics["spread"])
                    n += 1

                avg_score = round(total_score / n, 1) if n > 0 else 0.0
                avg_spread = round(sum(spreads) / len(spreads), 6) if spreads else None

                tiles_by_cid[cid] = {
                    "condition_id": cid,
                    "station_id": cm.station_id,
                    "city": cm.city,
                    "target_date": cm.target_date,
                    "bucket_count": len(cm.buckets),
                    "priced_buckets": n,
                    "avg_liquidity_score": avg_score,
                    "total_liquidity": round(total_liquidity, 2),
                    "total_volume_24h": round(total_volume, 2),
                    "avg_spread": avg_spread,
                    "buckets": buckets_data,
                }

        # Also include non-weather markets as individual tiles
        for snap in self._state.markets.values():
            if snap.condition_id in tiles_by_cid:
                continue  # already in a weather tile
            if snap.token_id in {t["token_id"] for t in all_tokens}:
                continue

            metrics = compute_market_liquidity(snap)
            all_tokens.append(metrics)

        # Sort tiles by score descending
        tiles = sorted(tiles_by_cid.values(), key=lambda t: t["avg_liquidity_score"], reverse=True)

        # Summary
        scores = [t["avg_liquidity_score"] for t in tiles if t["avg_liquidity_score"] > 0]
        return {
            "tiles": tiles,
            "token_count": len(all_tokens),
            "tile_count": len(tiles),
            "summary": {
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
                "max_score": max(scores) if scores else 0,
                "min_score": min(scores) if scores else 0,
                "total_liquidity": round(sum(t["total_liquidity"] for t in tiles), 2),
                "total_volume_24h": round(sum(t["total_volume_24h"] for t in tiles), 2),
            },
        }

    def get_token_scores(self) -> Dict[str, float]:
        """Return {token_id: liquidity_score} for all markets in state."""
        scores = {}
        for snap in self._state.markets.values():
            metrics = compute_market_liquidity(snap)
            scores[snap.token_id] = metrics["liquidity_score"]
        return scores
