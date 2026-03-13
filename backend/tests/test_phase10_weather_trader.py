"""Tests for Phase 10 Step 5 (weather_trader.py) and Step 6 (server integration).

Covers:
  - WeatherTrader classification from state markets
  - Forecast missing/stale handling
  - EV/opportunity filtering with all risk filters
  - Cooldown / duplicate prevention
  - Kill switch gating
  - RiskEngine rejection
  - Signal generation with correct fields
  - Execution lifecycle (submit → fill → finalize)
  - API endpoint responses
  - Config persistence integration
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.strategies.weather_trader import WeatherTrader
from engine.strategies.weather_models import (
    WeatherConfig, WeatherSignal, WeatherExecution, WeatherSignalStatus,
)
from engine.strategies.weather_parser import STATION_REGISTRY
from models import (
    MarketSnapshot, Event, EventType, OrderRecord,
    RiskConfig, StrategyConfig, StrategyStatusEnum,
)


# ---- Helpers ----

def _make_weather_config(**overrides):
    defaults = dict(
        scan_interval=1.0,
        classification_refresh_interval=1.0,
        forecast_refresh_interval=1800.0,
        min_edge_bps=300.0,
        min_liquidity=200.0,
        min_confidence=0.0,  # disabled for unit tests
        max_stale_forecast_minutes=120.0,
        max_stale_market_seconds=120.0,
        min_hours_to_resolution=4.0,
        max_hours_to_resolution=168.0,
        max_sigma=8.0,
        cooldown_seconds=1800.0,
        max_concurrent_signals=8,
        max_buckets_per_market=2,
    )
    defaults.update(overrides)
    return WeatherConfig(**defaults)


def _tomorrow_str():
    return (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%B %d, %Y")


def _tomorrow_iso():
    return (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")


def _make_mock_state():
    """Mock StateManager with weather markets."""
    state = MagicMock()
    state.risk_config = RiskConfig()
    state.strategies = {}
    state.markets = {}

    def get_market(token_id):
        return state.markets.get(token_id)
    state.get_market = get_market

    def update_market(token_id, snap):
        state.markets[token_id] = snap
    state.update_market = update_market

    return state


def _inject_weather_market(state, uid="t1", mu_target=43.5):
    """Inject a 5-bucket NYC weather market into mock state."""
    tomorrow = _tomorrow_str()
    cid = f"test-weather-{uid}"
    question = f"Highest temperature in NYC on {tomorrow}?"

    bucket_defs = [
        ("40F or below", 0.05),
        ("41-42F", 0.10),
        ("43-44F", 0.22),
        ("45-46F", 0.35),
        ("47F or higher", 0.28),
    ]

    for i, (label, price) in enumerate(bucket_defs):
        tid = f"weather-{uid}-{i}"
        state.update_market(tid, MarketSnapshot(
            token_id=tid,
            condition_id=cid,
            question=question,
            outcome=label,
            mid_price=price,
            last_price=price,
            volume_24h=5000,
            liquidity=500,
        ))

    return cid, [f"weather-{uid}-{i}" for i in range(5)]


# ===========================================================================
# Classification
# ===========================================================================

class TestClassification:
    def test_classifies_weather_market(self):
        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        trader = WeatherTrader(config=_make_weather_config())
        trader._state = state
        classified = trader._classify_markets()
        assert cid in classified
        cm = classified[cid]
        assert cm.station_id == "KLGA"
        assert len(cm.buckets) == 5

    def test_ignores_non_weather_market(self):
        state = _make_mock_state()
        # Inject a crypto market
        state.update_market("btc-yes", MarketSnapshot(
            token_id="btc-yes", condition_id="btc-cond",
            question="Will BTC be above $97,000?", outcome="Yes",
            mid_price=0.55, liquidity=3000,
        ))
        state.update_market("btc-no", MarketSnapshot(
            token_id="btc-no", condition_id="btc-cond",
            question="Will BTC be above $97,000?", outcome="No",
            mid_price=0.45, liquidity=3000,
        ))
        trader = WeatherTrader(config=_make_weather_config())
        trader._state = state
        classified = trader._classify_markets()
        assert "btc-cond" not in classified

    def test_classifies_multiple_markets(self):
        state = _make_mock_state()
        cid1, _ = _inject_weather_market(state, uid="nyc1")
        cid2, _ = _inject_weather_market(state, uid="nyc2")
        trader = WeatherTrader(config=_make_weather_config())
        trader._state = state
        classified = trader._classify_markets()
        assert len(classified) >= 2


# ===========================================================================
# Forecast Missing / Stale
# ===========================================================================

class TestForecastHandling:
    def test_no_forecast_generates_rejection(self):
        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        trader = WeatherTrader(config=_make_weather_config())
        trader._state = state
        trader._classified = trader._classify_markets()

        # No forecasts in feed cache
        cm = trader._classified[cid]
        signals = trader._evaluate_market(cm, time.time())

        # Should have a rejection signal
        assert len(signals) >= 1
        assert signals[0].is_tradable is False
        assert "no_forecast" in signals[0].rejection_reason

    def test_stale_forecast_rejected(self):
        from engine.strategies.weather_models import ForecastSnapshot
        from engine.strategies.weather_feeds import _CacheEntry

        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        config = _make_weather_config(max_stale_forecast_minutes=0.001)  # ~0.06 sec
        trader = WeatherTrader(config=config)
        trader._state = state
        trader._classified = trader._classify_markets()

        # Inject a forecast but make it stale
        cm = trader._classified[cid]
        snap = ForecastSnapshot(
            station_id="KLGA", target_date=cm.target_date,
            forecast_high_f=44.0, lead_hours=36.0,
        )
        cache_key = f"KLGA:{cm.target_date}"
        entry = _CacheEntry(snap)
        entry.fetched_at_mono = time.monotonic() - 600  # 10 min ago
        trader._feed._forecast_cache[cache_key] = entry

        signals = trader._evaluate_market(cm, time.time())
        assert any("stale_forecast" in (s.rejection_reason or "") for s in signals)


# ===========================================================================
# EV / Opportunity Filtering
# ===========================================================================

class TestEVFiltering:
    def _setup_trader_with_forecast(self, state, cid, mu=43.5, lead_hours=36.0, **config_kw):
        from engine.strategies.weather_models import ForecastSnapshot
        from engine.strategies.weather_feeds import _CacheEntry

        config = _make_weather_config(**config_kw)
        trader = WeatherTrader(config=config)
        trader._state = state
        trader._classified = trader._classify_markets()

        cm = trader._classified[cid]
        snap = ForecastSnapshot(
            station_id="KLGA", target_date=cm.target_date,
            forecast_high_f=mu, lead_hours=lead_hours,
        )
        cache_key = f"KLGA:{cm.target_date}"
        trader._feed._forecast_cache[cache_key] = _CacheEntry(snap)
        return trader, cm

    def test_edge_below_threshold_rejected(self):
        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        trader, cm = self._setup_trader_with_forecast(
            state, cid, mu=45.5, min_edge_bps=9000.0)  # impossibly high threshold
        signals = trader._evaluate_market(cm, time.time())
        tradable = [s for s in signals if s.is_tradable]
        assert len(tradable) == 0

    def test_low_liquidity_rejected(self):
        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        # Set liquidity to 10 (below 200 threshold)
        for tid in tids:
            snap = state.markets[tid]
            snap.liquidity = 10
        trader, cm = self._setup_trader_with_forecast(state, cid, min_liquidity=200.0)
        signals = trader._evaluate_market(cm, time.time())
        rejected_liq = [s for s in signals if "liquidity" in (s.rejection_reason or "")]
        assert len(rejected_liq) > 0

    def test_lead_time_too_short(self):
        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        trader, cm = self._setup_trader_with_forecast(
            state, cid, lead_hours=2.0, min_hours_to_resolution=4.0)
        signals = trader._evaluate_market(cm, time.time())
        assert any("lead_too_short" in (s.rejection_reason or "") for s in signals)

    def test_lead_time_too_long(self):
        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        trader, cm = self._setup_trader_with_forecast(
            state, cid, lead_hours=200.0, max_hours_to_resolution=168.0)
        signals = trader._evaluate_market(cm, time.time())
        assert any("lead_too_long" in (s.rejection_reason or "") for s in signals)

    def test_sigma_too_high(self):
        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        trader, cm = self._setup_trader_with_forecast(
            state, cid, lead_hours=160.0, max_sigma=1.0)  # sigma will be ~6F
        signals = trader._evaluate_market(cm, time.time())
        assert any("sigma_too_high" in (s.rejection_reason or "") for s in signals)


# ===========================================================================
# Cooldown / Duplicate Prevention
# ===========================================================================

class TestCooldown:
    def test_cooldown_prevents_repeat_signal(self):
        from engine.strategies.weather_models import ForecastSnapshot
        from engine.strategies.weather_feeds import _CacheEntry

        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        # Set one bucket to have high edge
        state.markets[tids[0]].mid_price = 0.01  # "40F or below" very cheap
        state.markets[tids[0]].liquidity = 500

        config = _make_weather_config(min_edge_bps=100.0, cooldown_seconds=3600.0)
        trader = WeatherTrader(config=config)
        trader._state = state
        trader._classified = trader._classify_markets()

        cm = trader._classified[cid]
        snap = ForecastSnapshot(
            station_id="KLGA", target_date=cm.target_date,
            forecast_high_f=38.0, lead_hours=36.0,  # mu=38 → high prob for <=40
        )
        cache_key = f"KLGA:{cm.target_date}"
        trader._feed._forecast_cache[cache_key] = _CacheEntry(snap)

        # First evaluation — should find tradable signals
        signals1 = trader._evaluate_market(cm, time.time())
        tradable1 = [s for s in signals1 if s.is_tradable]

        # Set cooldown manually for all tradable
        for s in tradable1:
            trader._cooldown[f"{cid}:{s.token_id}"] = time.time()

        # Second evaluation — same token_ids should be skipped
        signals2 = trader._evaluate_market(cm, time.time())
        tradable2 = [s for s in signals2 if s.is_tradable]
        assert len(tradable2) < len(tradable1)


# ===========================================================================
# Kill Switch
# ===========================================================================

class TestKillSwitch:
    def test_kill_switch_rejects_all(self):
        from engine.strategies.weather_models import ForecastSnapshot
        from engine.strategies.weather_feeds import _CacheEntry

        state = _make_mock_state()
        state.risk_config.kill_switch_active = True

        cid, tids = _inject_weather_market(state)
        config = _make_weather_config(min_edge_bps=100.0)
        trader = WeatherTrader(config=config)
        trader._state = state
        trader._classified = trader._classify_markets()

        cm = trader._classified[cid]
        snap = ForecastSnapshot(
            station_id="KLGA", target_date=cm.target_date,
            forecast_high_f=43.5, lead_hours=36.0,
        )
        trader._feed._forecast_cache[f"KLGA:{cm.target_date}"] = _CacheEntry(snap)

        signals = trader._evaluate_market(cm, time.time())
        tradable = [s for s in signals if s.is_tradable]
        assert len(tradable) == 0
        assert any("kill_switch" in (s.rejection_reason or "") for s in signals)


# ===========================================================================
# Execution Lifecycle
# ===========================================================================

class TestExecution:
    def test_execute_signal_calls_risk_and_exec(self):
        trader = WeatherTrader(config=_make_weather_config())
        trader._state = _make_mock_state()
        trader._bus = MagicMock()
        trader._bus.emit = AsyncMock()
        trader._risk_engine = MagicMock()
        trader._risk_engine.check_order = MagicMock(return_value=(True, None))
        trader._execution_engine = MagicMock()
        trader._execution_engine.submit_order = AsyncMock()

        signal = WeatherSignal(
            condition_id="c1", station_id="KLGA", target_date="2026-03-15",
            bucket_label="43-44F", token_id="t3",
            forecast_high_f=44.0, sigma=2.5, lead_hours=36.0,
            model_prob=0.35, market_price=0.22, edge_bps=1300.0,
            confidence=0.65, recommended_size=3.0, is_tradable=True,
        )

        asyncio.run(trader._execute_signal(signal))

        trader._risk_engine.check_order.assert_called_once()
        trader._execution_engine.submit_order.assert_called_once()
        assert len(trader._active_executions) == 1
        assert trader._m["signals_executed"] == 1

    def test_risk_rejection(self):
        trader = WeatherTrader(config=_make_weather_config())
        trader._state = _make_mock_state()
        trader._bus = MagicMock()
        trader._bus.emit = AsyncMock()
        trader._risk_engine = MagicMock()
        trader._risk_engine.check_order = MagicMock(return_value=(False, "max_position"))
        trader._execution_engine = MagicMock()

        signal = WeatherSignal(
            condition_id="c1", station_id="KLGA", target_date="2026-03-15",
            bucket_label="43-44F", token_id="t3",
            forecast_high_f=44.0, sigma=2.5, lead_hours=36.0,
            model_prob=0.35, market_price=0.22, edge_bps=1300.0,
            confidence=0.65, recommended_size=3.0, is_tradable=True,
        )

        asyncio.run(trader._execute_signal(signal))

        trader._execution_engine.submit_order.assert_not_called()
        assert len(trader._active_executions) == 0

    def test_fill_tracking(self):
        trader = WeatherTrader(config=_make_weather_config())
        trader._state = _make_mock_state()
        trader._bus = MagicMock()
        trader._bus.emit = AsyncMock()
        trader._risk_engine = MagicMock()
        trader._risk_engine.check_order = MagicMock(return_value=(True, None))
        trader._execution_engine = MagicMock()
        trader._execution_engine.submit_order = AsyncMock()

        signal = WeatherSignal(
            condition_id="c1", station_id="KLGA", target_date="2026-03-15",
            bucket_label="43-44F", token_id="t3",
            forecast_high_f=44.0, sigma=2.5, lead_hours=36.0,
            model_prob=0.35, market_price=0.22, edge_bps=1300.0,
            confidence=0.65, recommended_size=3.0, is_tradable=True,
        )

        asyncio.run(trader._execute_signal(signal))
        assert len(trader._active_executions) == 1

        # Get the order_id that was submitted
        exec_obj = list(trader._active_executions.values())[0]
        order_id = exec_obj.order_id

        # Simulate fill event
        fill_event = Event(
            type=EventType.ORDER_UPDATE,
            source="paper_adapter",
            data={"order_id": order_id, "status": "filled", "fill_price": 0.23},
        )
        asyncio.run(trader._on_order_update(fill_event))

        assert len(trader._active_executions) == 0
        assert len(trader._completed_executions) == 1
        assert trader._completed_executions[0].status == WeatherSignalStatus.FILLED
        assert trader._completed_executions[0].entry_price == 0.23


# ===========================================================================
# API Data Accessors
# ===========================================================================

class TestDataAccessors:
    def test_get_signals(self):
        trader = WeatherTrader(config=_make_weather_config())
        trader._signals = [
            WeatherSignal(
                condition_id="c1", station_id="KLGA", target_date="2026-03-15",
                bucket_label="43-44F", token_id="t3",
                forecast_high_f=44.0, sigma=2.5, lead_hours=36.0,
                model_prob=0.35, market_price=0.22, edge_bps=1300.0,
                confidence=0.65, recommended_size=3.0, is_tradable=True,
            ),
            WeatherSignal(
                condition_id="c1", station_id="KLGA", target_date="2026-03-15",
                bucket_label="40F or below", token_id="t1",
                forecast_high_f=44.0, sigma=2.5, lead_hours=36.0,
                model_prob=0.03, market_price=0.05, edge_bps=-200.0,
                confidence=0.0, recommended_size=0, is_tradable=False,
                rejection_reason="edge -200bps < 300bps",
            ),
        ]
        result = trader.get_signals(limit=10)
        assert len(result) == 2

    def test_get_health(self):
        trader = WeatherTrader(config=_make_weather_config())
        trader._state = _make_mock_state()
        health = trader.get_health()
        assert "total_scans" in health
        assert "running" in health
        assert "feed_health" in health
        assert "stations" in health
        assert "config" in health

    def test_get_config(self):
        trader = WeatherTrader(config=_make_weather_config())
        trader._running = True
        cfg = trader.get_config()
        assert isinstance(cfg, StrategyConfig)
        assert cfg.strategy_id == "weather_trader"
        assert cfg.enabled is True

    def test_get_stations(self):
        trader = WeatherTrader(config=_make_weather_config())
        stations = trader.get_stations()
        assert len(stations) == 8
        assert all("station_id" in s for s in stations)

    def test_get_forecasts_empty(self):
        trader = WeatherTrader(config=_make_weather_config())
        assert trader.get_forecasts() == {}


# ===========================================================================
# Max Buckets Per Market
# ===========================================================================

class TestMaxBucketsPerMarket:
    def test_limits_buckets_traded(self):
        from engine.strategies.weather_models import ForecastSnapshot
        from engine.strategies.weather_feeds import _CacheEntry

        state = _make_mock_state()
        cid, tids = _inject_weather_market(state)
        # Make ALL buckets very cheap → all have positive edge
        for tid in tids:
            state.markets[tid].mid_price = 0.01
            state.markets[tid].liquidity = 500

        config = _make_weather_config(
            min_edge_bps=100.0,
            max_buckets_per_market=2,
        )
        trader = WeatherTrader(config=config)
        trader._state = state
        trader._classified = trader._classify_markets()

        cm = trader._classified[cid]
        snap = ForecastSnapshot(
            station_id="KLGA", target_date=cm.target_date,
            forecast_high_f=43.5, lead_hours=36.0,
        )
        trader._feed._forecast_cache[f"KLGA:{cm.target_date}"] = _CacheEntry(snap)

        signals = trader._evaluate_market(cm, time.time())
        tradable = [s for s in signals if s.is_tradable]
        assert len(tradable) <= 2  # max_buckets_per_market
