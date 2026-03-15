"""Unit tests for LiquidityService — scoring, heatmap generation."""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.liquidity_service import compute_liquidity_score, compute_market_liquidity, LiquidityService
from models import MarketSnapshot


class TestLiquidityScoring:
    def test_zero_inputs_returns_zero(self):
        """Zero spread, zero depth, zero volume → 0 score."""
        score = compute_liquidity_score(spread=None, liquidity=0.0, volume_24h=0.0)
        assert score == 0.0

    def test_perfect_market(self):
        """Very tight spread, deep liquidity, high volume → near-max score."""
        score = compute_liquidity_score(spread=0.001, liquidity=5000.0, volume_24h=20000.0)
        assert score >= 80.0

    def test_wide_spread_low_score(self):
        """Wide spread with decent depth still scores low."""
        score = compute_liquidity_score(spread=0.10, liquidity=1000.0, volume_24h=1000.0)
        assert score < 30.0

    def test_score_bounded_0_100(self):
        """Score should always be between 0 and 100."""
        for spread, liq, vol in [
            (0.0, 100000, 100000),   # extreme values
            (1.0, 0, 0),              # terrible market
            (0.02, 500, 2000),         # normal market
            (None, 0, 0),             # no spread data
        ]:
            score = compute_liquidity_score(spread=spread, liquidity=liq, volume_24h=vol)
            assert 0 <= score <= 100, f"Score {score} out of bounds for ({spread}, {liq}, {vol})"

    def test_tighter_spread_higher_score(self):
        """Tighter spread should give higher score, all else equal."""
        s1 = compute_liquidity_score(spread=0.01, liquidity=500, volume_24h=500)
        s2 = compute_liquidity_score(spread=0.05, liquidity=500, volume_24h=500)
        assert s1 > s2

    def test_more_liquidity_higher_score(self):
        """Higher liquidity should give higher score."""
        s1 = compute_liquidity_score(spread=0.03, liquidity=2000, volume_24h=500)
        s2 = compute_liquidity_score(spread=0.03, liquidity=200, volume_24h=500)
        assert s1 > s2

    def test_more_volume_higher_score(self):
        """Higher volume should give higher score."""
        s1 = compute_liquidity_score(spread=0.03, liquidity=500, volume_24h=5000)
        s2 = compute_liquidity_score(spread=0.03, liquidity=500, volume_24h=100)
        assert s1 > s2


class TestComputeMarketLiquidity:
    def test_market_snapshot_metrics(self):
        """compute_market_liquidity returns correct shape."""
        snap = MarketSnapshot(
            token_id="tok1", condition_id="cond1",
            question="Will high be 43-44F?", outcome="Yes",
            mid_price=0.25, best_bid=0.24, best_ask=0.26,
            liquidity=1500.0, volume_24h=3000.0,
        )
        metrics = compute_market_liquidity(snap)
        assert metrics["token_id"] == "tok1"
        assert metrics["spread"] == pytest.approx(0.02, abs=0.001)
        assert metrics["liquidity_score"] > 0
        assert 0 <= metrics["liquidity_score"] <= 100

    def test_no_bid_ask_no_spread(self):
        """No bid/ask → spread is None."""
        snap = MarketSnapshot(
            token_id="tok2", condition_id="cond2",
            question="Test", outcome="Yes",
            mid_price=0.50, liquidity=100,
        )
        metrics = compute_market_liquidity(snap)
        assert metrics["spread"] is None


class TestLiquidityServiceHeatmap:
    def _make_state(self, markets):
        """Create a mock state with given market snapshots."""
        class MockState:
            def __init__(self, market_list):
                self.markets = {}
                for m in market_list:
                    self.markets[m.token_id] = m
            def get_market(self, token_id):
                return self.markets.get(token_id)
        return MockState(markets)

    def test_empty_state_returns_empty(self):
        state = self._make_state([])
        svc = LiquidityService(state)
        result = svc.get_heatmap()
        assert result["tile_count"] == 0
        assert result["token_count"] == 0

    def test_heatmap_with_classifications(self):
        """Heatmap should produce tiles from weather classifications."""
        from engine.strategies.weather_models import WeatherMarketClassification, TempBucket
        markets = [
            MarketSnapshot(
                token_id=f"tok_{i}", condition_id="cond1",
                question="NYC high temp", outcome=f"{40+i}-{41+i}F",
                mid_price=0.2, best_bid=0.19, best_ask=0.21,
                liquidity=500 + i * 100, volume_24h=100 + i * 50,
            )
            for i in range(5)
        ]
        state = self._make_state(markets)

        classifications = {
            "cond1": WeatherMarketClassification(
                condition_id="cond1", station_id="KLGA", city="New York",
                target_date="2026-03-20", resolution_type="daily_high",
                question="NYC high temp",
                buckets=[TempBucket(label=f"{40+i}-{41+i}F", token_id=f"tok_{i}") for i in range(5)],
            )
        }

        svc = LiquidityService(state)
        result = svc.get_heatmap(weather_classifications=classifications)

        assert result["tile_count"] == 1
        tile = result["tiles"][0]
        assert tile["city"] == "New York"
        assert tile["station_id"] == "KLGA"
        assert tile["priced_buckets"] == 5
        assert tile["avg_liquidity_score"] > 0
        assert tile["total_liquidity"] > 0
        assert len(tile["buckets"]) == 5

    def test_token_scores(self):
        """get_token_scores returns {token_id: score} for all markets."""
        markets = [
            MarketSnapshot(
                token_id="t1", condition_id="c1", question="Q", outcome="Y",
                mid_price=0.5, best_bid=0.49, best_ask=0.51, liquidity=1000,
            ),
            MarketSnapshot(
                token_id="t2", condition_id="c2", question="Q2", outcome="N",
                mid_price=0.3, liquidity=50,
            ),
        ]
        state = self._make_state(markets)
        svc = LiquidityService(state)
        scores = svc.get_token_scores()
        assert "t1" in scores
        assert "t2" in scores
        assert scores["t1"] > scores["t2"]  # t1 has tighter spread and more liquidity
