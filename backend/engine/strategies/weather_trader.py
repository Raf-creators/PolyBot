"""Weather Trader Strategy — temperature bucket trading on Polymarket weather markets.

Uses Open-Meteo forecast data and a normal-distribution probability model
to price temperature buckets, then trades when Polymarket prices diverge
beyond a configurable edge threshold.

Architecture (5-stage scan loop, 60s default):
  Stage 1 — Classification (every 5 min): scan markets for weather keywords → cache
  Stage 2 — Forecast Ingestion (every 30 min): fetch forecasts for classified stations
  Stage 3 — Probability Modeling (every scan): compute bucket probs from forecast + sigma
  Stage 4 — EV Evaluation (every scan): compare model probs to market prices → filter
  Stage 5 — Execution (async): route tradable signals through RiskEngine → ExecutionEngine
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, date as date_type
from typing import Dict, List, Optional

from models import (
    Event, EventType, OrderRecord, OrderSide,
    StrategyConfig, StrategyStatusEnum, utc_now,
)
from engine.strategies.base import BaseStrategy
from engine.strategies.weather_models import (
    WeatherConfig, WeatherMarketClassification, WeatherSignal,
    WeatherExecution, WeatherSignalStatus, BucketProbability,
    SigmaCalibration, StationType, ForecastAccuracyRecord,
    WeatherMarketType, PositionLifecycleEval, ExitReason,
    SHADOW_CONFIG_OVERRIDES,
)
from engine.strategies.weather_parser import (
    STATION_REGISTRY, classify_weather_market, classify_binary_weather_markets,
)
from engine.strategies.weather_pricing import (
    calibrate_sigma, compute_all_bucket_probabilities,
    compute_edge_bps, compute_weather_confidence,
    kelly_size, get_season,
    compute_amount_bucket_probability, get_amount_sigma,
)
from engine.strategies.weather_feeds import WeatherFeedManager

# Import at module level to avoid repeated import in hot loop
from engine.strategies.arb_pricing import compute_data_age

logger = logging.getLogger(__name__)


class WeatherTrader(BaseStrategy):
    """Temperature bucket trading on Polymarket weather markets.

    Uses Open-Meteo forecasts + calibrated normal distribution to compute
    bucket probabilities, trades when market prices diverge from model.
    """

    def __init__(self, config: Optional[WeatherConfig] = None):
        super().__init__(strategy_id="weather_trader", name="Weather Trader")
        self.config = config or WeatherConfig()
        self._risk_engine = None
        self._execution_engine = None
        self._scan_task: Optional[asyncio.Task] = None
        self._feed: WeatherFeedManager = WeatherFeedManager(
            forecast_cache_ttl_seconds=self.config.forecast_refresh_interval,
        )

        # Classification cache
        self._classified: Dict[str, WeatherMarketClassification] = {}
        self._last_classification_time: float = 0.0
        self._last_market_count: int = 0

        # Calibration (per-station, loaded/computed on start)
        self._calibrations: Dict[str, SigmaCalibration] = {}
        # Rolling calibration service (injected from server.py)
        self._rolling_calibration_service = None
        # Active calibration source tracking
        self._calibration_sources: Dict[str, str] = {}  # station_id → source name

        # Signal + execution tracking
        self._signals: List[WeatherSignal] = []
        self._active_executions: Dict[str, WeatherExecution] = {}
        self._completed_executions: List[WeatherExecution] = []
        self._order_to_execution: Dict[str, str] = {}
        self._cooldown: Dict[str, float] = {}  # key: "condition_id:token_id" → timestamp
        self._liquidity_scores: Dict[str, float] = {}  # token_id → liquidity score (0-100)

        # Forecast accuracy service (injected from server.py)
        self._accuracy_service = None
        # Calibration service (injected from server.py)
        self._calibration_service = None
        # CLOB WebSocket client (injected from server.py)
        self._clob_ws = None
        # Weather alert service (injected from server.py)
        self._alert_service = None

        # Position lifecycle evaluations: token_id → PositionLifecycleEval
        self._lifecycle_evals: Dict[str, PositionLifecycleEval] = {}
        self._lifecycle_shadow_exits: List[dict] = []  # log of shadow exit decisions
        # Snapshots of when positions were first flagged as exit candidates
        # token_id → {first_flagged_at, flagged_price, avg_cost, size, reason, market_question}
        self._exit_candidate_snapshots: Dict[str, dict] = {}

        # Metrics
        self._m: Dict = {
            "total_scans": 0,
            "last_scan_time": None,
            "last_scan_duration_ms": 0.0,
            "markets_classified": 0,
            "classification_failures": 0,
            "classification_failure_reasons": {},
            "forecasts_fetched": 0,
            "forecasts_missing": 0,
            "forecasts_stale": 0,
            "opportunities_evaluated": 0,
            "opportunities_rejected": 0,
            "rejection_reasons": {},
            "signals_generated": 0,
            "signals_executed": 0,
            "signals_filled": 0,
            "active_executions": 0,
            "completed_executions": 0,
            "last_execution_time": None,
            # Per-market-type breakdown
            "by_market_type": {
                "temperature": {"classified": 0, "signals": 0, "executed": 0, "rejected": 0},
                "precipitation": {"classified": 0, "signals": 0, "executed": 0, "rejected": 0},
                "snowfall": {"classified": 0, "signals": 0, "executed": 0, "rejected": 0},
                "wind": {"classified": 0, "signals": 0, "executed": 0, "rejected": 0},
            },
            # Asymmetric mode metrics
            "asymmetric": {
                "signals_generated": 0,
                "signals_executed": 0,
                "active_positions": 0,
                "best_signal_this_scan": None,
            },
            # Position lifecycle metrics
            "lifecycle": {
                "mode": "tag_only",
                "positions_evaluated": 0,
                "exit_candidates": 0,
                "shadow_exits": 0,
                "auto_exits": 0,
                "last_eval_time": None,
            },
        }

    # ---- Lifecycle ----

    def set_execution_context(self, risk_engine, execution_engine):
        self._risk_engine = risk_engine
        self._execution_engine = execution_engine

    def set_accuracy_service(self, service):
        """Inject forecast accuracy tracking service."""
        self._accuracy_service = service

    def set_calibration_service(self, service):
        """Inject calibration service for sigma loading."""
        self._calibration_service = service

    def set_clob_ws(self, client):
        """Inject CLOB WebSocket client for real-time price subscriptions."""
        self._clob_ws = client

    def set_alert_service(self, service):
        """Inject weather alert service for real-time signal alerts."""
        self._alert_service = service

    def set_rolling_calibration_service(self, service):
        """Inject rolling calibration service."""
        self._rolling_calibration_service = service

    async def reload_rolling_calibrations(self):
        """Hot-reload rolling calibrations into the active calibration table."""
        if not self._rolling_calibration_service:
            return {"status": "no_service"}
        rolling_cals = self._rolling_calibration_service.get_cached_calibrations()
        min_samples = self.config.rolling_min_samples
        upgraded = 0
        for sid, rcal in rolling_cals.items():
            if rcal.sample_count >= min_samples:
                self._calibrations[sid] = SigmaCalibration(
                    station_id=sid,
                    calibrated_at=rcal.calibrated_at,
                    sample_count=rcal.sample_count,
                    sigma_by_lead_hours=rcal.sigma_by_lead_hours,
                    seasonal_factors=rcal.seasonal_factors,
                    station_type_factor=rcal.station_type_factor,
                    mean_bias_f=rcal.mean_bias_f,
                )
                self._calibration_sources[sid] = "rolling_live"
                upgraded += 1
        return {"status": "reloaded", "rolling_stations": upgraded}

    def refresh_liquidity_scores(self):
        """Compute and cache liquidity scores for all tracked markets."""
        from services.liquidity_service import compute_market_liquidity
        for snap in self._state.markets.values():
            metrics = compute_market_liquidity(snap)
            self._liquidity_scores[snap.token_id] = metrics["liquidity_score"]

    def get_liquidity_score(self, token_id: str) -> float:
        """Get cached liquidity score for a token. 0 if unknown."""
        return self._liquidity_scores.get(token_id, 0.0)

    def apply_shadow_overrides(self):
        """Apply conservative shadow-mode config overrides."""
        for key, val in SHADOW_CONFIG_OVERRIDES.items():
            if hasattr(self.config, key):
                setattr(self.config, key, val)
        logger.info(
            f"WeatherTrader shadow overrides applied: "
            f"min_edge={self.config.min_edge_bps}bps, "
            f"kelly={self.config.kelly_scale}, "
            f"max_stale={self.config.max_stale_market_seconds}s"
        )

    async def start(self, state, bus):
        await super().start(state, bus)
        self._bus.on(EventType.ORDER_UPDATE, self._on_order_update)
        await self._feed.start()

        # Load calibrations: rolling > historical > defaults
        # Step 1: Load historical bootstrap calibrations
        if self._calibration_service:
            try:
                calibrations = await self._calibration_service.get_all_calibrations()
                if calibrations:
                    self._calibrations = calibrations
                    for sid in calibrations:
                        self._calibration_sources[sid] = "historical_bootstrap"
                    logger.info(
                        f"WeatherTrader loaded {len(calibrations)} historical calibrations: "
                        f"{list(calibrations.keys())}"
                    )
                else:
                    logger.info("WeatherTrader: no historical calibrations found, using defaults")
            except Exception as e:
                logger.warning(f"WeatherTrader: failed to load historical calibrations: {e}")

        # Step 2: Overlay rolling calibrations (higher priority)
        if self._rolling_calibration_service:
            try:
                await self._rolling_calibration_service.load_cached()
                rolling_cals = self._rolling_calibration_service.get_cached_calibrations()
                min_samples = self.config.rolling_min_samples
                for sid, rcal in rolling_cals.items():
                    if rcal.sample_count >= min_samples:
                        # Convert RollingCalibration to SigmaCalibration for use in calibrate_sigma()
                        self._calibrations[sid] = SigmaCalibration(
                            station_id=sid,
                            calibrated_at=rcal.calibrated_at,
                            sample_count=rcal.sample_count,
                            sigma_by_lead_hours=rcal.sigma_by_lead_hours,
                            seasonal_factors=rcal.seasonal_factors,
                            station_type_factor=rcal.station_type_factor,
                            mean_bias_f=rcal.mean_bias_f,
                        )
                        self._calibration_sources[sid] = "rolling_live"
                if rolling_cals:
                    live_count = sum(1 for s in self._calibration_sources.values() if s == "rolling_live")
                    logger.info(
                        f"WeatherTrader: {live_count} stations using rolling calibration "
                        f"(min_samples={min_samples})"
                    )
            except Exception as e:
                logger.warning(f"WeatherTrader: failed to load rolling calibrations: {e}")

        # Set source for stations with no calibration
        for sid in STATION_REGISTRY:
            if sid not in self._calibration_sources:
                self._calibration_sources[sid] = "default_sigma_table"
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info(
            f"WeatherTrader started "
            f"(scan={self.config.scan_interval}s, "
            f"min_edge={self.config.min_edge_bps}bps)"
        )

    async def stop(self):
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        if self._bus:
            self._bus.off(EventType.ORDER_UPDATE, self._on_order_update)
        await self._feed.stop()
        await super().stop()
        logger.info("WeatherTrader stopped")

    async def on_market_update(self, event):
        pass  # Uses own scan loop

    # ---- Scan Loop (5 stages) ----

    async def _scan_loop(self):
        await asyncio.sleep(8)  # let market data settle
        while self._running:
            t0 = time.monotonic()
            try:
                # Stage 1: Refresh classifications if stale
                await self._maybe_refresh_classifications()

                # Stage 2: Fetch forecasts for classified stations
                await self._refresh_forecasts()

                # Stage 2.5: Refresh liquidity scores
                self.refresh_liquidity_scores()

                # Stage 3+4: Evaluate all classified markets
                signals = await self._evaluate_all()

                # Stage 5: Execute eligible signals — sorted by edge (highest first)
                # Separate standard and asymmetric signals
                standard_eligible = sorted(
                    [s for s in signals if s.is_tradable and not s.is_asymmetric],
                    key=lambda s: s.quality_score,
                    reverse=True,
                )
                asymmetric_eligible = sorted(
                    [s for s in signals if s.is_tradable and s.is_asymmetric],
                    key=lambda s: s.edge_bps,
                    reverse=True,
                )

                # Track best standard signal
                if standard_eligible:
                    best = standard_eligible[0]
                    self._m["best_signal_this_scan"] = {
                        "station": best.station_id,
                        "date": best.target_date,
                        "bucket": best.bucket_label,
                        "market_type": best.market_type,
                        "edge_bps": round(best.edge_bps, 0),
                        "confidence": round(best.confidence, 3),
                        "quality_score": best.quality_score,
                        "thesis": best.explanation.get("thesis", ""),
                    }
                    logger.info(
                        f"[WEATHER] Best signal: {best.station_id} {best.target_date} "
                        f"bucket={best.bucket_label} quality={best.quality_score:.3f} "
                        f"edge={best.edge_bps:.0f}bps conf={best.confidence:.3f}"
                    )
                else:
                    self._m["best_signal_this_scan"] = None

                # Track best asymmetric signal
                if asymmetric_eligible:
                    best_asym = asymmetric_eligible[0]
                    self._m["asymmetric"]["best_signal_this_scan"] = {
                        "station": best_asym.station_id,
                        "date": best_asym.target_date,
                        "bucket": best_asym.bucket_label,
                        "market_price": round(best_asym.market_price, 4),
                        "model_prob": round(best_asym.model_prob, 4),
                        "edge": round(best_asym.model_prob - best_asym.market_price, 4),
                        "expected_payoff": round((1.0 / best_asym.market_price - 1) * 100, 1) if best_asym.market_price > 0 else 0,
                        "thesis": best_asym.explanation.get("thesis", ""),
                    }
                    logger.info(
                        f"[WEATHER-ASYM] Best: {best_asym.station_id} {best_asym.target_date} "
                        f"bucket={best_asym.bucket_label} price={best_asym.market_price:.4f} "
                        f"prob={best_asym.model_prob:.4f} edge={best_asym.model_prob - best_asym.market_price:.4f}"
                    )
                else:
                    self._m["asymmetric"]["best_signal_this_scan"] = None

                # Execute standard signals
                for sig in standard_eligible:
                    if len(self._active_executions) >= self.config.max_concurrent_signals:
                        break
                    open_weather = self._count_open_weather_positions()
                    if open_weather >= self.config.max_weather_positions:
                        logger.info(
                            f"[WEATHER] Skipping execution: {open_weather} open positions >= "
                            f"max_weather_positions ({self.config.max_weather_positions})"
                        )
                        break
                    await self._execute_signal(sig)

                # Execute asymmetric signals (separate position cap)
                open_asym = self._count_asymmetric_positions()
                self._m["asymmetric"]["active_positions"] = open_asym
                for sig in asymmetric_eligible:
                    if open_asym >= self.config.asymmetric_max_positions:
                        break
                    if len(self._active_executions) >= self.config.max_concurrent_signals:
                        break
                    await self._execute_signal(sig)
                    open_asym += 1

                # Stage 5.5: Position Lifecycle — evaluate open standard weather positions
                await self._evaluate_position_lifecycle()

                # Stage 6: Record forecast accuracy entries for new classifications
                await self._record_forecast_accuracy(signals)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Weather scan error: {e}", exc_info=True)

            elapsed_ms = (time.monotonic() - t0) * 1000
            self._m["total_scans"] += 1
            self._m["last_scan_time"] = utc_now()
            self._m["last_scan_duration_ms"] = round(elapsed_ms, 2)

            await asyncio.sleep(self.config.scan_interval)

    # ---- Stage 1: Classification ----

    async def _maybe_refresh_classifications(self):
        now = time.monotonic()
        needs_refresh = (
            now - self._last_classification_time >= self.config.classification_refresh_interval
        )
        if not needs_refresh:
            return

        self._classified = await self._classify_markets()
        self._last_classification_time = now
        self._m["markets_classified"] = len(self._classified)
        # Count by market type
        type_counts = {"temperature": 0, "precipitation": 0, "snowfall": 0, "wind": 0}
        for cm in self._classified.values():
            mtype = getattr(cm, 'market_type', WeatherMarketType.TEMPERATURE)
            type_counts[mtype.value if hasattr(mtype, 'value') else str(mtype)] = \
                type_counts.get(mtype.value if hasattr(mtype, 'value') else str(mtype), 0) + 1
        for mtype_key, count in type_counts.items():
            if mtype_key in self._m["by_market_type"]:
                self._m["by_market_type"][mtype_key]["classified"] = count

    async def _classify_markets(self) -> Dict[str, WeatherMarketClassification]:
        """Discover and classify weather temperature markets.

        Uses two strategies:
          1. Scan StateManager for multi-outcome weather markets (original path)
          2. Discover weather events from Gamma API (real Polymarket structure:
             each bucket is a separate binary Yes/No market grouped by event)
        """
        results = {}
        fail_reasons = {}

        # --- Strategy 1: Scan StateManager (works for injected test markets) ---
        by_condition: Dict[str, List] = {}
        for snap in self._state.markets.values():
            cid = snap.condition_id
            if not cid:
                continue
            if cid not in by_condition:
                by_condition[cid] = []
            by_condition[cid].append(snap)

        for cid, snaps in by_condition.items():
            if len(snaps) < 3:
                continue
            question = snaps[0].question
            if not question:
                continue
            outcomes = [s.outcome or "" for s in snaps]
            token_ids = [s.token_id for s in snaps]
            classification, reason = classify_weather_market(
                question=question, condition_id=cid,
                outcomes=outcomes, token_ids=token_ids,
            )
            if classification:
                results[cid] = classification
            elif reason:
                fail_reasons[reason] = fail_reasons.get(reason, 0) + 1

        # --- Strategy 2: Gamma API event discovery (real Polymarket) ---
        try:
            cities = [s.city for s in STATION_REGISTRY.values()]
            raw_markets = await self._feed.discover_weather_events(cities, days_ahead=5)
            if raw_markets:
                # Inject discovered markets into state for pricing
                from models import MarketSnapshot
                for m in raw_markets:
                    if m["yes_token_id"] and m["yes_token_id"] not in self._state.markets:
                        self._state.update_market(m["yes_token_id"], MarketSnapshot(
                            token_id=m["yes_token_id"],
                            condition_id=m["condition_id"],
                            question=m["question"],
                            outcome="Yes",
                            mid_price=m["mid_price"],
                            last_price=m["mid_price"],
                            volume_24h=0,
                            liquidity=m.get("liquidity", 0),
                        ))

                classifications, cls_errors = classify_binary_weather_markets(raw_markets)
                for cm in classifications:
                    if cm.condition_id not in results:
                        results[cm.condition_id] = cm
                for err in cls_errors:
                    fail_reasons[err] = fail_reasons.get(err, 0) + 1

                # Subscribe discovered tokens to CLOB WS for real-time updates
                if self._clob_ws:
                    ws_tokens = [m["yes_token_id"] for m in raw_markets if m.get("yes_token_id")]
                    if ws_tokens:
                        self._clob_ws.subscribe_tokens(ws_tokens)
                self._m["gamma_events_discovered"] = len(raw_markets)
        except Exception as e:
            logger.warning(f"Gamma event discovery error: {e}", exc_info=True)
            self._m["gamma_discovery_error"] = str(e)

        self._m["classification_failures"] = sum(fail_reasons.values())
        self._m["classification_failure_reasons"] = fail_reasons
        return results

    # ---- Stage 2: Forecast Ingestion ----

    async def _refresh_forecasts(self):
        """Fetch forecasts for all classified stations that need refreshing."""
        station_dates = set()
        for cm in self._classified.values():
            station_dates.add((cm.station_id, cm.target_date))

        fetched = 0
        missing = 0
        for station_id, target_date in station_dates:
            snapshot = await self._feed.get_forecast(station_id, target_date)
            if snapshot:
                fetched += 1
            else:
                missing += 1

        self._m["forecasts_fetched"] = fetched
        self._m["forecasts_missing"] = missing

    # ---- Stage 3+4: Evaluate + Filter ----

    async def _evaluate_all(self) -> List[WeatherSignal]:
        results = []
        evaluated = 0

        # Expire cooldowns
        now = time.time()
        self._cooldown = {
            key: ts for key, ts in self._cooldown.items()
            if now - ts < self.config.cooldown_seconds
        }

        for cid, cm in self._classified.items():
            bucket_signals = self._evaluate_market(cm, now)
            results.extend(bucket_signals)
            evaluated += 1

        self._m["opportunities_evaluated"] = evaluated

        # Prepend new signals, keep last 300
        self._signals = results + self._signals
        if len(self._signals) > 300:
            self._signals = self._signals[:300]

        return results

    def _count_open_weather_positions(self) -> int:
        """Count total open weather positions (state positions + active executions)."""
        from engine.risk import classify_strategy
        state_count = sum(
            1 for pos in self._state.positions.values()
            if classify_strategy(pos) == "weather"
        )
        return state_count

    def _count_asymmetric_positions(self) -> int:
        """Count open positions tagged as weather_asymmetric."""
        return sum(
            1 for pos in self._state.positions.values()
            if getattr(pos, 'strategy_id', '') == 'weather_asymmetric'
        )


    def _evaluate_market(
        self, cm: WeatherMarketClassification, now: float
    ) -> List[WeatherSignal]:
        """Evaluate all buckets in a classified weather market.
        Returns list of WeatherSignals (both tradable and rejected).
        """
        signals = []

        # --- Get forecast ---
        forecast = self._feed.get_cached_forecast(cm.station_id, cm.target_date)
        if not forecast:
            self._m["forecasts_missing"] += 1
            return [self._reject_signal(cm, None, 0, 0, 0, 0, 0,
                                        "no_forecast", bucket_label="(all)")]

        # --- Check forecast freshness ---
        forecast_age_min = self._feed.get_forecast_age_minutes(cm.station_id, cm.target_date)
        if forecast_age_min and forecast_age_min > self.config.max_stale_forecast_minutes:
            self._m["forecasts_stale"] += 1
            return [self._reject_signal(cm, forecast, 0, 0, 0, forecast_age_min, 0,
                                        f"stale_forecast ({forecast_age_min:.0f}min)",
                                        bucket_label="(all)")]

        mu = forecast.forecast_high_f
        lead_hours = forecast.lead_hours

        # --- For non-temperature markets, extract the relevant forecast value ---
        mtype = getattr(cm, 'market_type', WeatherMarketType.TEMPERATURE)
        if mtype == WeatherMarketType.PRECIPITATION:
            forecast_val = forecast.forecast_precip_in
            if forecast_val is None:
                return [self._reject_signal(cm, forecast, 0, 0, lead_hours, 0, 0,
                                            "no_precip_forecast", bucket_label="(all)")]
            mu = forecast_val  # override mu with precip amount
        elif mtype == WeatherMarketType.SNOWFALL:
            forecast_val = forecast.forecast_snow_in
            if forecast_val is None:
                return [self._reject_signal(cm, forecast, 0, 0, lead_hours, 0, 0,
                                            "no_snow_forecast", bucket_label="(all)")]
            mu = forecast_val
        elif mtype == WeatherMarketType.WIND:
            forecast_val = forecast.forecast_wind_mph
            if forecast_val is None:
                return [self._reject_signal(cm, forecast, 0, 0, lead_hours, 0, 0,
                                            "no_wind_forecast", bucket_label="(all)")]
            mu = forecast_val

        # --- Lead time bounds ---
        if lead_hours < self.config.min_hours_to_resolution:
            return [self._reject_signal(cm, forecast, mu, 0, lead_hours, 0, 0,
                                        f"lead_too_short ({lead_hours:.0f}h)",
                                        bucket_label="(all)")]
        if lead_hours > self.config.max_hours_to_resolution:
            return [self._reject_signal(cm, forecast, mu, 0, lead_hours, 0, 0,
                                        f"lead_too_long ({lead_hours:.0f}h)",
                                        bucket_label="(all)")]

        # --- Calibrate sigma ---
        try:
            target = date_type.fromisoformat(cm.target_date)
            month = target.month
        except (ValueError, TypeError):
            month = datetime.now(timezone.utc).month

        mtype_str = mtype.value if hasattr(mtype, 'value') else str(mtype)
        oc_mult = self.config.sigma_overconfidence_multiplier
        max_adj = self.config.calibration_max_adjustment_pct
        min_samp = self.config.calibration_min_samples_per_segment

        if mtype == WeatherMarketType.TEMPERATURE:
            station = STATION_REGISTRY.get(cm.station_id)
            station_type = station.station_type if station else StationType.INLAND
            calibration = self._calibrations.get(cm.station_id)
            sigma, sigma_trace = calibrate_sigma(
                lead_hours, month, station_type, calibration,
                overconfidence_multiplier=oc_mult,
                max_adjustment_pct=max_adj,
                min_samples_for_cal=min_samp,
            )
        else:
            sigma, sigma_trace = get_amount_sigma(mtype_str, lead_hours, overconfidence_multiplier=oc_mult)

        if sigma > self.config.max_sigma:
            return [self._reject_signal(cm, forecast, mu, sigma, lead_hours, 0, 0,
                                        f"sigma_too_high ({sigma:.1f}F)",
                                        bucket_label="(all)", sigma_trace=sigma_trace)]

        # --- Compute bucket probabilities ---
        if mtype == WeatherMarketType.TEMPERATURE:
            probs = compute_all_bucket_probabilities(cm.buckets, mu, sigma)
        else:
            # Non-temperature: compute each bucket individually
            probs = [
                compute_amount_bucket_probability(b, mu, sigma, mtype_str)
                for b in cm.buckets
            ]

        # --- Spread-sum validation: check if market prices are coherent ---
        market_prices_sum = 0
        price_count = 0
        for bucket in cm.buckets:
            snap = self._state.get_market(bucket.token_id)
            if snap and snap.mid_price and 0 < snap.mid_price < 1:
                market_prices_sum += snap.mid_price
                price_count += 1
        if price_count >= 2:
            spread_sum_deviation = abs(market_prices_sum - 1.0)
            # Alert on spread deviation even if below rejection threshold
            if self._alert_service:
                self._alert_service.check_spread_deviation(
                    station_id=cm.station_id, city=self._get_city(cm.station_id),
                    target_date=cm.target_date, spread_deviation=spread_sum_deviation,
                    max_spread_sum=self.config.max_spread_sum,
                )
            if spread_sum_deviation > self.config.max_spread_sum:
                return [self._reject_signal(cm, forecast, mu, sigma, lead_hours, 0, 0,
                                            f"spread_sum_deviation ({spread_sum_deviation:.3f} > {self.config.max_spread_sum})",
                                            bucket_label="(all)", sigma_trace=sigma_trace)]

        # --- Evaluate each bucket ---
        buckets_traded = 0
        for i, bucket in enumerate(cm.buckets):
            prob = probs[i]
            cooldown_key = f"{cm.condition_id}:{bucket.token_id}"

            # Get market price
            snap = self._state.get_market(bucket.token_id)
            if not snap:
                continue

            market_price = snap.mid_price or 0
            if market_price <= 0 or market_price >= 1.0:
                continue

            edge_bps = compute_edge_bps(prob, market_price)

            # --- Compute confidence for alert purposes (even if bucket gets rejected) ---
            data_age = compute_data_age(snap.updated_at)
            liquidity = snap.liquidity
            bucket_confidence = 0.0
            if data_age <= self.config.max_stale_market_seconds and liquidity >= self.config.min_liquidity:
                bucket_confidence = compute_weather_confidence(
                    liquidity=liquidity,
                    market_data_age_seconds=data_age,
                    forecast_age_minutes=forecast_age_min or 0,
                    lead_hours=lead_hours,
                    sigma=sigma,
                )

            # --- Alert service: track price/edge/tradability changes ---
            is_bucket_tradable = (
                edge_bps >= self.config.min_edge_bps
                and bucket_confidence >= self.config.min_confidence
                and data_age <= self.config.max_stale_market_seconds
                and liquidity >= self.config.min_liquidity
            )
            if self._alert_service:
                self._alert_service.check_and_alert(
                    station_id=cm.station_id,
                    city=self._get_city(cm.station_id),
                    target_date=cm.target_date,
                    bucket_label=bucket.label,
                    token_id=bucket.token_id,
                    model_prob=prob,
                    market_price=market_price,
                    edge_bps=edge_bps,
                    confidence=bucket_confidence,
                    is_tradable=is_bucket_tradable,
                )

            # --- Market freshness ---
            if data_age > self.config.max_stale_market_seconds:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"stale_market ({data_age:.0f}s)", bucket_label=bucket.label, sigma_trace=sigma_trace))
                continue

            # --- Liquidity ---
            if liquidity < self.config.min_liquidity:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"low_liquidity ({liquidity:.0f})", bucket_label=bucket.label, sigma_trace=sigma_trace))
                continue

            # --- Liquidity score filter ---
            liq_score = self.get_liquidity_score(bucket.token_id)
            if self.config.min_liquidity_score > 0 and liq_score < self.config.min_liquidity_score:
                self._m["rejection_reasons"]["liquidity_too_low"] = self._m["rejection_reasons"].get("liquidity_too_low", 0) + 1
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"liquidity_too_low (score {liq_score:.0f} < {self.config.min_liquidity_score:.0f})",
                    bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price,
                    liquidity_score=liq_score, sigma_trace=sigma_trace))
                continue

            # --- Edge threshold ---
            if edge_bps < self.config.min_edge_bps:
                # Check asymmetric opportunity before rejecting
                raw_edge = prob - market_price
                if (self.config.asymmetric_enabled
                    and market_price <= self.config.asymmetric_max_market_price
                    and prob >= self.config.asymmetric_min_model_prob
                    and raw_edge >= self.config.asymmetric_min_edge
                    and bucket_confidence >= self.config.asymmetric_min_confidence
                    and cooldown_key not in self._cooldown
                    and not self._state.risk_config.kill_switch_active):
                    # Asymmetric signal — hold-to-resolution play
                    asym_size = kelly_size(
                        model_prob=prob,
                        market_price=market_price,
                        base_size=self.config.asymmetric_default_size,
                        kelly_scale=self.config.asymmetric_kelly_scale,
                        max_size=self.config.asymmetric_max_size,
                    )
                    if asym_size > 0:
                        expected_payoff = round((1.0 / market_price - 1) * 100, 1) if market_price > 0 else 0
                        city_name = self._get_city(cm.station_id)
                        asym_explanation = {
                            "market": cm.question[:120],
                            "location": city_name or cm.station_id,
                            "contract_type": "asymmetric_weather",
                            "market_type": mtype_str,
                            "bucket": bucket.label,
                            "forecast_summary": f"Forecast {mu:.1f} (sigma {sigma:.1f}, lead {lead_hours:.0f}h)",
                            "model_probability": round(prob, 4),
                            "market_price": round(market_price, 4),
                            "raw_edge": round(raw_edge, 4),
                            "expected_payoff_pct": expected_payoff,
                            "risk_reward": f"Risk ${asym_size * market_price:.2f} for potential ${asym_size * (1.0 - market_price):.2f}",
                            "confidence": round(bucket_confidence, 3),
                            "sigma_trace": sigma_trace,
                            "thesis": f"Asymmetric: Market prices {bucket.label} at {market_price:.0%} but model says {prob:.0%}. "
                                      f"If correct, {expected_payoff:.0f}% return. Hold to resolution.",
                        }
                        asym_signal = WeatherSignal(
                            condition_id=cm.condition_id,
                            station_id=cm.station_id,
                            target_date=cm.target_date,
                            bucket_label=bucket.label,
                            token_id=bucket.token_id,
                            forecast_high_f=round(mu, 1),
                            sigma=round(sigma, 2),
                            lead_hours=round(lead_hours, 1),
                            model_prob=round(prob, 6),
                            market_price=round(market_price, 6),
                            edge_bps=edge_bps,
                            confidence=bucket_confidence,
                            recommended_size=asym_size,
                            is_tradable=True,
                            is_asymmetric=True,
                            liquidity_score=round(liq_score, 1),
                            quality_score=round(raw_edge, 4),  # for asymmetric, raw edge is the quality
                            market_type=mtype_str,
                            explanation=asym_explanation,
                        )
                        signals.append(asym_signal)
                        self._m["asymmetric"]["signals_generated"] += 1
                        logger.info(
                            f"[WEATHER-ASYM] Signal: {cm.station_id} {cm.target_date} "
                            f"bucket={bucket.label} price={market_price:.4f} prob={prob:.4f} "
                            f"edge={raw_edge:.4f} payoff={expected_payoff:.0f}% size={asym_size}"
                        )
                        continue
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"edge {edge_bps:.0f}bps < {self.config.min_edge_bps:.0f}bps",
                    bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price, sigma_trace=sigma_trace))
                continue

            # --- Confidence ---
            confidence = bucket_confidence
            if confidence < self.config.min_confidence:
                # Also check asymmetric for confidence-rejected buckets
                raw_edge = prob - market_price
                if (self.config.asymmetric_enabled
                    and market_price <= self.config.asymmetric_max_market_price
                    and prob >= self.config.asymmetric_min_model_prob
                    and raw_edge >= self.config.asymmetric_min_edge
                    and bucket_confidence >= self.config.asymmetric_min_confidence
                    and cooldown_key not in self._cooldown
                    and not self._state.risk_config.kill_switch_active):
                    asym_size = kelly_size(
                        model_prob=prob,
                        market_price=market_price,
                        base_size=self.config.asymmetric_default_size,
                        kelly_scale=self.config.asymmetric_kelly_scale,
                        max_size=self.config.asymmetric_max_size,
                    )
                    if asym_size > 0:
                        expected_payoff = round((1.0 / market_price - 1) * 100, 1) if market_price > 0 else 0
                        city_name = self._get_city(cm.station_id)
                        asym_explanation = {
                            "market": cm.question[:120],
                            "location": city_name or cm.station_id,
                            "contract_type": "asymmetric_weather",
                            "market_type": mtype_str,
                            "bucket": bucket.label,
                            "forecast_summary": f"Forecast {mu:.1f} (sigma {sigma:.1f}, lead {lead_hours:.0f}h)",
                            "model_probability": round(prob, 4),
                            "market_price": round(market_price, 4),
                            "raw_edge": round(raw_edge, 4),
                            "expected_payoff_pct": expected_payoff,
                            "confidence": round(bucket_confidence, 3),
                            "sigma_trace": sigma_trace,
                            "thesis": f"Asymmetric: Market prices {bucket.label} at {market_price:.0%} but model says {prob:.0%}. "
                                      f"If correct, {expected_payoff:.0f}% return. Hold to resolution.",
                        }
                        asym_signal = WeatherSignal(
                            condition_id=cm.condition_id,
                            station_id=cm.station_id,
                            target_date=cm.target_date,
                            bucket_label=bucket.label,
                            token_id=bucket.token_id,
                            forecast_high_f=round(mu, 1),
                            sigma=round(sigma, 2),
                            lead_hours=round(lead_hours, 1),
                            model_prob=round(prob, 6),
                            market_price=round(market_price, 6),
                            edge_bps=edge_bps,
                            confidence=bucket_confidence,
                            recommended_size=asym_size,
                            is_tradable=True,
                            is_asymmetric=True,
                            liquidity_score=round(liq_score, 1),
                            quality_score=round(raw_edge, 4),
                            market_type=mtype_str,
                            explanation=asym_explanation,
                        )
                        signals.append(asym_signal)
                        self._m["asymmetric"]["signals_generated"] += 1
                        continue
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"confidence {confidence:.3f} < {self.config.min_confidence}",
                    bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price, sigma_trace=sigma_trace))
                continue

            # --- Cooldown ---
            if cooldown_key in self._cooldown:
                continue

            # --- Kill switch ---
            if self._state.risk_config.kill_switch_active:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    "kill_switch_active", bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price, sigma_trace=sigma_trace))
                continue

            # --- Concurrency ---
            if len(self._active_executions) >= self.config.max_concurrent_signals:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    "max_concurrent_signals", bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price, sigma_trace=sigma_trace))
                continue

            # --- Max buckets per market ---
            if buckets_traded >= self.config.max_buckets_per_market:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    "max_buckets_per_market", bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price, sigma_trace=sigma_trace))
                continue

            # --- Tradable signal ---
            size = kelly_size(
                model_prob=prob,
                market_price=market_price,
                base_size=self.config.default_size,
                kelly_scale=self.config.kelly_scale,
                max_size=self.config.max_signal_size,
            )
            if size <= 0:
                continue

            # Quality score: normalized composite of edge, confidence, liquidity
            q_edge = min(edge_bps / 2000.0, 1.0)     # 2000bps = perfect
            q_conf = confidence                        # already 0-1
            q_liq = min(liq_score / 100.0, 1.0)       # 100 = perfect
            quality_score = round(q_edge * 0.5 + q_conf * 0.3 + q_liq * 0.2, 4)

            # Explanation: structured reasoning for debugging and UI
            city_name = self._get_city(cm.station_id)
            _TYPE_LABELS = {
                "temperature": ("temperature_bucket", "F"),
                "precipitation": ("precipitation_threshold", "in"),
                "snowfall": ("snowfall_threshold", "in"),
                "wind": ("wind_threshold", "mph"),
            }
            ctype, unit = _TYPE_LABELS.get(mtype_str, ("weather_bucket", ""))
            if mtype == WeatherMarketType.TEMPERATURE:
                fcst_summary = f"Forecast high {mu:.1f}F (sigma {sigma:.1f}F, lead {lead_hours:.0f}h)"
            else:
                fcst_summary = f"Forecast {mtype_str} {mu:.2f}{unit} (sigma {sigma:.2f}{unit}, lead {lead_hours:.0f}h)"
            explanation = {
                "market": cm.question[:120],
                "location": city_name or cm.station_id,
                "contract_type": ctype,
                "market_type": mtype_str,
                "bucket": bucket.label,
                "forecast_summary": fcst_summary,
                "model_probability": round(prob, 4),
                "market_price": round(market_price, 4),
                "edge": round(edge_bps, 0),
                "confidence": round(confidence, 3),
                "liquidity_score": round(liq_score, 1),
                "quality_score": quality_score,
                "sigma_trace": sigma_trace,
                "thesis": self._build_thesis(mu, sigma, bucket, prob, market_price, edge_bps),
            }

            signal = WeatherSignal(
                condition_id=cm.condition_id,
                station_id=cm.station_id,
                target_date=cm.target_date,
                bucket_label=bucket.label,
                token_id=bucket.token_id,
                forecast_high_f=round(mu, 1),
                sigma=round(sigma, 2),
                lead_hours=round(lead_hours, 1),
                model_prob=round(prob, 6),
                market_price=round(market_price, 6),
                edge_bps=edge_bps,
                confidence=confidence,
                recommended_size=size,
                is_tradable=True,
                liquidity_score=round(liq_score, 1),
                quality_score=quality_score,
                market_type=mtype_str,
                explanation=explanation,
            )
            signals.append(signal)
            buckets_traded += 1
            self._m["signals_generated"] += 1
            if mtype_str in self._m["by_market_type"]:
                self._m["by_market_type"][mtype_str]["signals"] += 1

            logger.info(
                f"[WEATHER] Signal: {cm.station_id} {cm.target_date} "
                f"bucket={bucket.label} mu={mu:.1f}F sigma={sigma:.2f} "
                f"prob={prob:.4f} mkt={market_price:.4f} "
                f"edge={edge_bps:.0f}bps conf={confidence:.3f} "
                f"quality={quality_score:.3f} size={size}"
            )

        return signals

    def _reject_signal(
        self, cm, forecast, mu, sigma, lead_hours,
        forecast_age_min, data_age, reason,
        bucket_label="", model_prob=0.0, market_price=0.0,
        liquidity_score=0.0, sigma_trace=None,
    ) -> WeatherSignal:
        """Create a rejected signal for the log and update metrics."""
        self._m["opportunities_rejected"] += 1
        bucket = reason.split(" ")[0] if reason else "unknown"
        self._m["rejection_reasons"][bucket] = self._m["rejection_reasons"].get(bucket, 0) + 1

        # Track by market type
        mtype_str = getattr(cm, 'market_type', WeatherMarketType.TEMPERATURE)
        if hasattr(mtype_str, 'value'):
            mtype_str = mtype_str.value
        if mtype_str in self._m["by_market_type"]:
            self._m["by_market_type"][mtype_str]["rejected"] += 1

        city_name = self._get_city(cm.station_id) if cm else ""
        explanation = {
            "market": (cm.question[:120] if cm else ""),
            "location": city_name or (cm.station_id if cm else ""),
            "contract_type": "temperature_bucket",
            "bucket": bucket_label,
            "forecast_summary": f"Forecast high {mu:.1f}F (sigma {sigma:.1f}F, lead {lead_hours:.0f}h)" if mu else "no forecast",
            "model_probability": round(model_prob, 4),
            "market_price": round(market_price, 4),
            "rejection_reason": reason,
        }
        if sigma_trace:
            explanation["sigma_trace"] = sigma_trace

        return WeatherSignal(
            condition_id=cm.condition_id,
            station_id=cm.station_id,
            target_date=cm.target_date,
            bucket_label=bucket_label,
            token_id="",
            forecast_high_f=round(mu, 1) if mu else 0,
            sigma=round(sigma, 2) if sigma else 0,
            lead_hours=round(lead_hours, 1) if lead_hours else 0,
            model_prob=round(model_prob, 6),
            market_price=round(market_price, 6),
            edge_bps=0,
            confidence=0,
            recommended_size=0,
            is_tradable=False,
            rejection_reason=reason,
            liquidity_score=round(liquidity_score, 1),
            quality_score=0.0,
            explanation=explanation,
        )


    def _build_thesis(self, mu, sigma, bucket, prob, market_price, edge_bps) -> str:
        """Build human-readable thesis for why a contract is mispriced."""
        label = bucket.label
        direction = "above" if (bucket.lower_bound and not bucket.upper_bound) else "below" if (bucket.upper_bound and not bucket.lower_bound) else "in"

        # Distance from forecast to bucket
        if bucket.lower_bound is not None and bucket.upper_bound is not None:
            mid = (bucket.lower_bound + bucket.upper_bound) / 2.0
            dist = abs(mu - mid)
            dist_sigma = dist / sigma if sigma > 0 else 0
        elif bucket.lower_bound is not None:
            dist = mu - bucket.lower_bound
            dist_sigma = dist / sigma if sigma > 0 else 0
        elif bucket.upper_bound is not None:
            dist = bucket.upper_bound - mu
            dist_sigma = dist / sigma if sigma > 0 else 0
        else:
            dist_sigma = 0

        parts = []
        if prob > market_price:
            parts.append(f"Model says {label} has {prob:.0%} probability but market prices it at {market_price:.0%}")
            parts.append(f"{edge_bps:.0f}bps edge")
        if dist_sigma < 1.0:
            parts.append(f"forecast ({mu:.0f}F) is within {dist_sigma:.1f} sigma of bucket center")
        elif dist_sigma > 2.0:
            parts.append(f"forecast ({mu:.0f}F) is {dist_sigma:.1f} sigma away, tail probability play")

        return "; ".join(parts) if parts else f"Edge {edge_bps:.0f}bps on {label}"

    # ---- Stage 5: Execution ----

    async def _execute_signal(self, signal: WeatherSignal):
        if not self._risk_engine or not self._execution_engine:
            logger.warning("No execution context; skipping weather signal")
            return

        # Asymmetric signals use a separate strategy_id for independent PnL tracking
        strategy_tag = "weather_asymmetric" if signal.is_asymmetric else self.strategy_id

        order = OrderRecord(
            token_id=signal.token_id,
            side=OrderSide.BUY,
            price=signal.market_price,
            size=signal.recommended_size,
            strategy_id=strategy_tag,
        )

        ok, reason = self._risk_engine.check_order(order)
        if not ok:
            signal.is_tradable = False
            signal.rejection_reason = f"risk: {reason}"
            self._m["opportunities_rejected"] += 1
            self._m["rejection_reasons"]["risk"] = self._m["rejection_reasons"].get("risk", 0) + 1
            return

        execution = WeatherExecution(
            signal_id=signal.id,
            condition_id=signal.condition_id,
            station_id=signal.station_id,
            target_date=signal.target_date,
            bucket_label=signal.bucket_label,
            order_id=order.id,
            target_edge_bps=signal.edge_bps,
            size=signal.recommended_size,
        )

        self._active_executions[execution.id] = execution
        self._order_to_execution[order.id] = execution.id
        cooldown_key = f"{signal.condition_id}:{signal.token_id}"
        self._cooldown[cooldown_key] = time.time()
        self._m["signals_executed"] += 1
        self._m["active_executions"] = len(self._active_executions)
        if signal.is_asymmetric:
            self._m["asymmetric"]["signals_executed"] += 1

        # Emit signal event for Telegram / analytics
        strategy_label = "WEATHER-ASYM" if signal.is_asymmetric else "WEATHER"
        expected_payoff = round((1.0 / signal.market_price - 1) * 100, 1) if signal.is_asymmetric and signal.market_price > 0 else None
        await self._bus.emit(Event(
            type=EventType.SIGNAL,
            source=strategy_tag,
            data={
                "strategy": strategy_label,
                "asset": signal.station_id,
                "strike": signal.bucket_label,
                "fair_price": signal.model_prob,
                "market_price": signal.market_price,
                "edge_bps": signal.edge_bps,
                "side": "BUY",
                "forecast_high": signal.forecast_high_f,
                "sigma": signal.sigma,
                "lead_hours": signal.lead_hours,
                "is_asymmetric": signal.is_asymmetric,
                "expected_payoff_pct": expected_payoff,
            },
        ))

        logger.info(
            f"[WEATHER] Executing: {signal.station_id} {signal.bucket_label} "
            f"price={signal.market_price:.4f} size={signal.recommended_size} "
            f"edge={signal.edge_bps:.0f}bps"
        )

        try:
            await self._execution_engine.submit_order(order)
        except Exception as e:
            logger.error(f"Weather execution error: {e}")
            execution.status = WeatherSignalStatus.REJECTED
            self._finalize_execution(execution)

    # ---- Fill Tracking ----

    async def _on_order_update(self, event: Event):
        if event.source != "paper_adapter":
            return

        order_id = event.data.get("order_id")
        if not order_id:
            return

        exec_id = self._order_to_execution.get(order_id)
        if not exec_id:
            return

        execution = self._active_executions.get(exec_id)
        if not execution:
            return

        status = event.data.get("status")
        fill_price = event.data.get("fill_price")

        if status == "filled":
            execution.status = WeatherSignalStatus.FILLED
            execution.entry_price = fill_price
            execution.filled_at = utc_now()
            self._m["signals_filled"] += 1
            self._m["last_execution_time"] = utc_now()
            logger.info(
                f"[WEATHER] FILLED: {execution.station_id} {execution.bucket_label} "
                f"fill={fill_price:.4f} edge={execution.target_edge_bps:.0f}bps"
            )
            self._finalize_execution(execution)

        elif status in ("rejected", "cancelled"):
            execution.status = WeatherSignalStatus.REJECTED
            logger.warning(f"[WEATHER] Order {order_id[:8]} {status}")
            self._finalize_execution(execution)

    def _finalize_execution(self, execution: WeatherExecution):
        self._active_executions.pop(execution.id, None)
        self._completed_executions.append(execution)
        if len(self._completed_executions) > 200:
            self._completed_executions = self._completed_executions[-200:]
        self._order_to_execution.pop(execution.order_id, None)
        self._m["active_executions"] = len(self._active_executions)
        self._m["completed_executions"] = len(self._completed_executions)

    # ---- Position Lifecycle Management ----

    async def _evaluate_position_lifecycle(self):
        """Evaluate all open standard weather positions for exit candidacy.

        Asymmetric positions are NEVER evaluated — they always hold to resolution.
        Evaluates: profit multiple, current edge, edge decay, time inefficiency.
        """
        mode = self.config.lifecycle_mode
        if mode == "off":
            self._lifecycle_evals.clear()
            return

        self._m["lifecycle"]["mode"] = mode
        now = datetime.now(timezone.utc)
        new_evals: Dict[str, PositionLifecycleEval] = {}
        candidates = 0
        shadow_exits_this_scan = 0

        # Build opened_at map from trades
        opened_at_map: Dict[str, datetime] = {}
        for t in self._state.trades:
            if t.side.value == "buy" and t.token_id not in opened_at_map:
                try:
                    opened_at_map[t.token_id] = datetime.fromisoformat(
                        t.timestamp.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

        # Build entry-edge map from completed executions + active executions
        entry_edge_map: Dict[str, float] = {}  # token_id → edge_bps at entry
        for ex in list(self._completed_executions) + list(self._active_executions.values()):
            for sig in self._signals:
                if sig.id == ex.signal_id and sig.token_id:
                    if sig.token_id not in entry_edge_map:
                        entry_edge_map[sig.token_id] = ex.target_edge_bps
                    break

        for pos in self._state.positions.values():
            strategy_id = getattr(pos, 'strategy_id', '') or ''

            # NEVER evaluate asymmetric positions for exit
            if strategy_id == 'weather_asymmetric':
                continue

            # Evaluate standard weather positions (explicit or legacy without strategy_id)
            from engine.risk import classify_strategy
            bucket = classify_strategy(pos)
            if strategy_id and strategy_id != 'weather_trader':
                continue
            if not strategy_id and bucket != 'weather':
                continue

            token_id = pos.token_id
            market = self._state.get_market(token_id)
            current_price = (market.mid_price if market and market.mid_price else pos.current_price) or 0
            avg_cost = pos.avg_cost or 0

            if avg_cost <= 0 or current_price <= 0:
                continue

            # ---- Compute metrics ----
            profit_multiple = round(current_price / avg_cost, 4)

            # Entry edge
            edge_at_entry = entry_edge_map.get(token_id, 0.0)

            # Current edge: reprice using current model if we have classification context
            current_model_prob = 0.0
            current_edge_bps = 0.0
            weather_ctx = None
            for ex in list(self._completed_executions[-50:]) + list(self._active_executions.values()):
                for sig in self._signals:
                    if sig.id == ex.signal_id and sig.token_id == token_id:
                        weather_ctx = {
                            'station_id': sig.station_id,
                            'target_date': sig.target_date,
                            'condition_id': sig.condition_id,
                        }
                        break
                if weather_ctx:
                    break

            # Try to reprice from current classified market data
            if weather_ctx:
                cid = weather_ctx.get('condition_id', '')
                cm = self._classified.get(cid)
                if cm:
                    forecast = self._feed.get_cached_forecast(cm.station_id, cm.target_date)
                    if forecast:
                        mu = forecast.forecast_high_f
                        mtype = getattr(cm, 'market_type', WeatherMarketType.TEMPERATURE)
                        mtype_str = mtype.value if hasattr(mtype, 'value') else str(mtype)
                        if mtype == WeatherMarketType.PRECIPITATION and forecast.forecast_precip_in is not None:
                            mu = forecast.forecast_precip_in
                        elif mtype == WeatherMarketType.SNOWFALL and forecast.forecast_snow_in is not None:
                            mu = forecast.forecast_snow_in
                        elif mtype == WeatherMarketType.WIND and forecast.forecast_wind_mph is not None:
                            mu = forecast.forecast_wind_mph

                        # Compute sigma
                        try:
                            target = date_type.fromisoformat(cm.target_date)
                            month = target.month
                        except (ValueError, TypeError):
                            month = now.month

                        oc_mult = self.config.sigma_overconfidence_multiplier
                        if mtype == WeatherMarketType.TEMPERATURE:
                            station = STATION_REGISTRY.get(cm.station_id)
                            station_type = station.station_type if station else StationType.INLAND
                            calibration = self._calibrations.get(cm.station_id)
                            sigma, _ = calibrate_sigma(
                                forecast.lead_hours, month, station_type, calibration,
                                overconfidence_multiplier=oc_mult,
                            )
                            probs = compute_all_bucket_probabilities(cm.buckets, mu, sigma)
                        else:
                            sigma, _ = get_amount_sigma(mtype_str, forecast.lead_hours, overconfidence_multiplier=oc_mult)
                            probs = [
                                compute_amount_bucket_probability(b, mu, sigma, mtype_str)
                                for b in cm.buckets
                            ]

                        # Find the bucket matching this token
                        for i, bucket in enumerate(cm.buckets):
                            if bucket.token_id == token_id:
                                current_model_prob = probs[i] if i < len(probs) else 0.0
                                current_edge_bps = compute_edge_bps(current_model_prob, current_price)
                                break

            # Edge decay
            edge_decay_pct = 0.0
            if edge_at_entry > 0 and current_edge_bps < edge_at_entry:
                edge_decay_pct = round((edge_at_entry - current_edge_bps) / edge_at_entry, 4)

            # Time held
            time_held_hours = 0.0
            opened_dt = opened_at_map.get(token_id)
            if opened_dt:
                time_held_hours = round((now - opened_dt).total_seconds() / 3600, 2)

            # Hours to resolution
            hours_to_res = None
            if market and market.end_date:
                try:
                    end_dt = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
                    ttr = (end_dt - now).total_seconds()
                    hours_to_res = round(ttr / 3600, 1) if ttr > 0 else 0.0
                except (ValueError, TypeError):
                    pass

            # ---- Apply exit rules ----
            is_exit = False
            exit_reason = None
            exit_detail = ""

            # Rule 1: Profit capture
            if profit_multiple >= self.config.profit_capture_threshold:
                is_exit = True
                exit_reason = ExitReason.PROFIT_CAPTURE.value
                exit_detail = f"Price multiple {profit_multiple:.2f}x >= {self.config.profit_capture_threshold:.1f}x threshold"

            # Rule 2: Negative edge flip
            elif current_edge_bps <= self.config.max_negative_edge_bps and current_model_prob > 0:
                is_exit = True
                exit_reason = ExitReason.NEGATIVE_EDGE.value
                exit_detail = f"Current edge {current_edge_bps:.0f}bps <= {self.config.max_negative_edge_bps:.0f}bps floor"

            # Rule 3: Edge decay
            elif edge_at_entry > 0 and edge_decay_pct >= self.config.edge_decay_exit_pct:
                is_exit = True
                exit_reason = ExitReason.EDGE_DECAY.value
                exit_detail = f"Edge decayed {edge_decay_pct:.0%} (entry={edge_at_entry:.0f}bps, now={current_edge_bps:.0f}bps)"

            # Rule 4: Time inefficiency
            elif (time_held_hours >= self.config.time_inefficiency_hours
                  and current_edge_bps < self.config.time_inefficiency_min_edge_bps
                  and current_model_prob > 0):
                is_exit = True
                exit_reason = ExitReason.TIME_INEFFICIENCY.value
                exit_detail = (
                    f"Held {time_held_hours:.1f}h with only {current_edge_bps:.0f}bps edge "
                    f"(threshold: {self.config.time_inefficiency_hours:.0f}h / {self.config.time_inefficiency_min_edge_bps:.0f}bps)"
                )

            eval_result = PositionLifecycleEval(
                token_id=token_id,
                strategy_id=strategy_id,
                is_exit_candidate=is_exit,
                exit_reason=exit_reason,
                exit_reason_detail=exit_detail,
                profit_multiple=profit_multiple,
                edge_at_entry=edge_at_entry,
                current_edge_bps=round(current_edge_bps, 2),
                edge_decay_pct=edge_decay_pct,
                current_model_prob=round(current_model_prob, 6),
                time_held_hours=time_held_hours,
                hours_to_resolution=hours_to_res,
                lifecycle_mode=mode,
            )
            new_evals[token_id] = eval_result

            if is_exit:
                candidates += 1
                logger.info(
                    f"[LIFECYCLE] Exit candidate: {token_id[:12]}.. "
                    f"reason={exit_reason} profit={profit_multiple:.2f}x "
                    f"edge={current_edge_bps:.0f}bps decay={edge_decay_pct:.0%} "
                    f"held={time_held_hours:.1f}h mode={mode}"
                )

                # Record first-flagged snapshot (only once per position)
                if token_id not in self._exit_candidate_snapshots:
                    self._exit_candidate_snapshots[token_id] = {
                        "first_flagged_at": utc_now(),
                        "flagged_price": current_price,
                        "avg_cost": avg_cost,
                        "size": pos.size,
                        "reason": exit_reason,
                        "profit_multiple_at_flag": profit_multiple,
                        "market_question": getattr(pos, 'market_question', ''),
                    }

                # Shadow exit: log but don't sell
                if mode == "shadow_exit":
                    shadow_entry = {
                        "token_id": token_id,
                        "reason": exit_reason,
                        "detail": exit_detail,
                        "profit_multiple": profit_multiple,
                        "current_edge_bps": round(current_edge_bps, 2),
                        "time_held_hours": time_held_hours,
                        "would_sell_at": current_price,
                        "avg_cost": avg_cost,
                        "size": pos.size,
                        "market_question": getattr(pos, 'market_question', ''),
                        "timestamp": utc_now(),
                    }
                    self._lifecycle_shadow_exits.append(shadow_entry)
                    if len(self._lifecycle_shadow_exits) > 100:
                        self._lifecycle_shadow_exits = self._lifecycle_shadow_exits[-100:]
                    shadow_exits_this_scan += 1
                    logger.info(f"[LIFECYCLE-SHADOW] Would exit: {token_id[:12]}.. at {current_price:.4f} — {exit_detail}")

                # Auto exit: actually sell (standard weather only)
                elif mode == "auto_exit":
                    await self._auto_exit_position(pos, exit_reason, exit_detail)
                    self._m["lifecycle"]["auto_exits"] += 1

        self._lifecycle_evals = new_evals
        self._m["lifecycle"]["positions_evaluated"] = len(new_evals)
        self._m["lifecycle"]["exit_candidates"] = candidates
        self._m["lifecycle"]["shadow_exits"] += shadow_exits_this_scan
        self._m["lifecycle"]["last_eval_time"] = utc_now()

        # Clean up snapshots for positions that no longer exist
        active_tokens = set(new_evals.keys())
        stale = [t for t in self._exit_candidate_snapshots if t not in active_tokens]
        for t in stale:
            del self._exit_candidate_snapshots[t]

    async def _auto_exit_position(self, pos, exit_reason: str, exit_detail: str):
        """Execute a sell order to exit a standard weather position."""
        if not self._risk_engine or not self._execution_engine:
            logger.warning("[LIFECYCLE] No execution context; skipping auto-exit")
            return

        market = self._state.get_market(pos.token_id)
        sell_price = (market.mid_price if market and market.mid_price else pos.current_price) or 0
        if sell_price <= 0:
            return

        order = OrderRecord(
            token_id=pos.token_id,
            side=OrderSide.SELL,
            price=sell_price,
            size=pos.size,
            strategy_id="weather_trader",
        )

        ok, reason = self._risk_engine.check_order(order)
        if not ok:
            logger.warning(f"[LIFECYCLE] Auto-exit blocked by risk: {reason}")
            return

        logger.info(
            f"[LIFECYCLE-AUTO] Selling {pos.token_id[:12]}.. "
            f"size={pos.size} price={sell_price:.4f} reason={exit_reason}: {exit_detail}"
        )

        await self._bus.emit(Event(
            type=EventType.SIGNAL,
            source="weather_trader",
            data={
                "strategy": "WEATHER-LIFECYCLE",
                "asset": pos.token_id[:12],
                "side": "SELL",
                "reason": exit_reason,
                "detail": exit_detail,
            },
        ))

        try:
            await self._execution_engine.submit_order(order)
        except Exception as e:
            logger.error(f"[LIFECYCLE] Auto-exit execution error: {e}")

    def get_lifecycle_evals(self) -> Dict[str, dict]:
        """Return current lifecycle evaluations keyed by token_id."""
        return {tid: ev.model_dump() for tid, ev in self._lifecycle_evals.items()}

    def get_lifecycle_shadow_exits(self, limit: int = 50) -> List[dict]:
        """Return recent shadow exit log entries."""
        return self._lifecycle_shadow_exits[-limit:]

    def get_lifecycle_dashboard(self) -> dict:
        """Compute lifecycle dashboard data for threshold validation."""
        evals = self._lifecycle_evals
        candidates = {tid: ev for tid, ev in evals.items() if ev.is_exit_candidate}

        # ---- Summary cards ----
        if candidates:
            avg_profit_mult = round(sum(e.profit_multiple for e in candidates.values()) / len(candidates), 4)
            avg_current_edge = round(sum(e.current_edge_bps for e in candidates.values()) / len(candidates), 2)
            avg_edge_decay = round(sum(e.edge_decay_pct for e in candidates.values()) / len(candidates), 4)
            avg_time_held = round(sum(e.time_held_hours for e in candidates.values()) / len(candidates), 1)
        else:
            avg_profit_mult = avg_current_edge = avg_edge_decay = avg_time_held = 0.0

        summary = {
            "total_positions_evaluated": len(evals),
            "total_exit_candidates": len(candidates),
            "avg_profit_multiple": avg_profit_mult,
            "avg_current_edge_bps": avg_current_edge,
            "avg_edge_decay_pct": avg_edge_decay,
            "avg_time_held_hours": avg_time_held,
        }

        # ---- Exit reason distribution ----
        reason_dist = {}
        for ev in candidates.values():
            r = ev.exit_reason or "unknown"
            if r not in reason_dist:
                reason_dist[r] = {"count": 0, "avg_profit_mult": 0, "avg_edge": 0, "tokens": []}
            reason_dist[r]["count"] += 1
            reason_dist[r]["tokens"].append(ev.token_id[:12])
        # Compute averages per reason
        for r, data in reason_dist.items():
            bucket_evs = [ev for ev in candidates.values() if (ev.exit_reason or "unknown") == r]
            if bucket_evs:
                data["avg_profit_mult"] = round(sum(e.profit_multiple for e in bucket_evs) / len(bucket_evs), 4)
                data["avg_edge"] = round(sum(e.current_edge_bps for e in bucket_evs) / len(bucket_evs), 2)

        # ---- Time bucket breakdown ----
        time_buckets = {"<6h": {"total": 0, "exit_candidates": 0, "avg_profit_mult": 0},
                        "6-24h": {"total": 0, "exit_candidates": 0, "avg_profit_mult": 0},
                        ">24h": {"total": 0, "exit_candidates": 0, "avg_profit_mult": 0},
                        "unknown": {"total": 0, "exit_candidates": 0, "avg_profit_mult": 0}}
        for ev in evals.values():
            h = ev.hours_to_resolution
            if h is None:
                b = "unknown"
            elif h <= 6:
                b = "<6h"
            elif h <= 24:
                b = "6-24h"
            else:
                b = ">24h"
            time_buckets[b]["total"] += 1
            if ev.is_exit_candidate:
                time_buckets[b]["exit_candidates"] += 1
        # Compute avg profit mult per time bucket
        for bk in time_buckets:
            bucket_evs = [ev for ev in evals.values()
                          if self._classify_time_bucket(ev.hours_to_resolution) == bk]
            if bucket_evs:
                time_buckets[bk]["avg_profit_mult"] = round(
                    sum(e.profit_multiple for e in bucket_evs) / len(bucket_evs), 4)

        # ---- Would Have Sold vs Held comparison ----
        sold_vs_held = []
        for tid, snap in self._exit_candidate_snapshots.items():
            ev = evals.get(tid)
            if not ev:
                continue
            pos = self._state.positions.get(tid)
            if not pos:
                continue
            market = self._state.get_market(tid)
            current_price = (market.mid_price if market and market.mid_price else pos.current_price) or 0
            avg_cost = snap["avg_cost"]
            size = snap["size"]
            flagged_price = snap["flagged_price"]

            # Simulated exit PnL (if we had sold at flag time)
            sim_exit_pnl = round((flagged_price - avg_cost) * size, 4) if avg_cost > 0 else 0
            # Current held PnL
            held_pnl = round((current_price - avg_cost) * size, 4) if avg_cost > 0 else 0
            # Delta: positive = holding was better, negative = should have sold
            delta = round(held_pnl - sim_exit_pnl, 4)

            sold_vs_held.append({
                "token_id": tid[:16],
                "market_question": snap.get("market_question", "")[:60],
                "reason": snap["reason"],
                "first_flagged_at": snap["first_flagged_at"],
                "flagged_price": round(flagged_price, 4),
                "current_price": round(current_price, 4),
                "avg_cost": round(avg_cost, 4),
                "size": size,
                "sim_exit_pnl": sim_exit_pnl,
                "held_pnl": held_pnl,
                "delta": delta,
                "delta_direction": "hold_better" if delta > 0 else "sell_better" if delta < 0 else "neutral",
                "profit_mult_at_flag": snap.get("profit_multiple_at_flag", 0),
                "profit_mult_now": ev.profit_multiple,
            })

        # Aggregate sold-vs-held by reason
        reason_comparison = {}
        for entry in sold_vs_held:
            r = entry["reason"]
            if r not in reason_comparison:
                reason_comparison[r] = {"count": 0, "total_sim_exit_pnl": 0, "total_held_pnl": 0, "total_delta": 0}
            reason_comparison[r]["count"] += 1
            reason_comparison[r]["total_sim_exit_pnl"] = round(reason_comparison[r]["total_sim_exit_pnl"] + entry["sim_exit_pnl"], 4)
            reason_comparison[r]["total_held_pnl"] = round(reason_comparison[r]["total_held_pnl"] + entry["held_pnl"], 4)
            reason_comparison[r]["total_delta"] = round(reason_comparison[r]["total_delta"] + entry["delta"], 4)
        for r, data in reason_comparison.items():
            data["verdict"] = "hold_better" if data["total_delta"] > 0 else "sell_better" if data["total_delta"] < 0 else "neutral"

        # ---- All positions profit distribution (for context) ----
        profit_distribution = {"<0.5x": 0, "0.5-0.8x": 0, "0.8-1.0x": 0, "1.0-1.5x": 0, "1.5-2.0x": 0, ">2.0x": 0}
        for ev in evals.values():
            pm = ev.profit_multiple
            if pm < 0.5:
                profit_distribution["<0.5x"] += 1
            elif pm < 0.8:
                profit_distribution["0.5-0.8x"] += 1
            elif pm < 1.0:
                profit_distribution["0.8-1.0x"] += 1
            elif pm < 1.5:
                profit_distribution["1.0-1.5x"] += 1
            elif pm < 2.0:
                profit_distribution["1.5-2.0x"] += 1
            else:
                profit_distribution[">2.0x"] += 1

        return {
            "summary": summary,
            "reason_distribution": reason_dist,
            "time_buckets": time_buckets,
            "shadow_exits": self._lifecycle_shadow_exits[-30:],
            "sold_vs_held": sold_vs_held,
            "sold_vs_held_by_reason": reason_comparison,
            "profit_distribution": profit_distribution,
            "config": {
                "lifecycle_mode": self.config.lifecycle_mode,
                "profit_capture_threshold": self.config.profit_capture_threshold,
                "max_negative_edge_bps": self.config.max_negative_edge_bps,
                "edge_decay_exit_pct": self.config.edge_decay_exit_pct,
                "time_inefficiency_hours": self.config.time_inefficiency_hours,
                "time_inefficiency_min_edge_bps": self.config.time_inefficiency_min_edge_bps,
            },
        }

    @staticmethod
    def _classify_time_bucket(hours_to_resolution) -> str:
        if hours_to_resolution is None:
            return "unknown"
        if hours_to_resolution <= 6:
            return "<6h"
        if hours_to_resolution <= 24:
            return "6-24h"
        return ">24h"

    # ---- Forecast Accuracy Recording ----

    async def _record_forecast_accuracy(self, signals: List[WeatherSignal]):
        """Record forecast entries for accuracy tracking (idempotent per station+date)."""
        if not self._accuracy_service:
            return

        recorded = set()
        for sig in signals:
            key = f"{sig.station_id}:{sig.target_date}"
            if key in recorded or sig.forecast_high_f == 0:
                continue
            recorded.add(key)

            # Determine calibration source
            cal_source = self._calibration_sources.get(sig.station_id, "default_sigma_table")

            record = ForecastAccuracyRecord(
                station_id=sig.station_id,
                city=self._get_city(sig.station_id),
                target_date=sig.target_date,
                forecast_high_f=sig.forecast_high_f,
                sigma_used=sig.sigma,
                lead_hours=sig.lead_hours,
                calibration_source=cal_source,
                bucket_count=len(self._classified.get(sig.condition_id, WeatherMarketClassification(
                    condition_id="", station_id="", city="", target_date="",
                    resolution_type="", buckets=[], question="",
                )).buckets),
            )
            try:
                await self._accuracy_service.record_forecast(record)
            except Exception as e:
                logger.warning(f"Failed to record forecast accuracy: {e}")

    def _get_city(self, station_id: str) -> str:
        station = STATION_REGISTRY.get(station_id)
        return station.city if station else station_id

    def _get_calibration_source_summary(self) -> Dict[str, int]:
        """Count stations per calibration source."""
        summary: Dict[str, int] = {}
        for source in self._calibration_sources.values():
            summary[source] = summary.get(source, 0) + 1
        return summary

    def _get_primary_calibration_source(self) -> str:
        """Human-readable label for the dominant calibration source."""
        summary = self._get_calibration_source_summary()
        if summary.get("rolling_live", 0) > 0:
            return "rolling_live"
        if summary.get("historical_bootstrap", 0) > 0:
            return "historical_bootstrap"
        return "default_sigma_table"

    def _get_calibration_note(self) -> str:
        summary = self._get_calibration_source_summary()
        parts = []
        for src, count in sorted(summary.items()):
            parts.append(f"{src}: {count}")
        return ", ".join(parts) if parts else "Using default NWS MOS sigma table"

    # ---- API Data Accessors ----

    def get_signals(self, limit: int = 50) -> List[dict]:
        return [s.model_dump() for s in self._signals[:limit]]

    def get_active_executions(self) -> List[dict]:
        return [e.model_dump() for e in self._active_executions.values()]

    def get_completed_executions(self, limit: int = 50) -> List[dict]:
        return [e.model_dump() for e in self._completed_executions[-limit:]]

    def get_health(self) -> dict:
        # Determine execution mode from state
        exec_mode = "paper"
        if self._state and hasattr(self._state, 'trading_mode'):
            exec_mode = self._state.trading_mode.value

        return {
            **self._m,
            "config": self.config.model_dump(),
            "running": self._running,
            "execution_mode": exec_mode,
            "is_shadow": exec_mode == "shadow",
            "shadow_overrides_applied": any(
                getattr(self.config, k, None) == v
                for k, v in SHADOW_CONFIG_OVERRIDES.items()
            ),
            "sigma_pipeline": {
                "overconfidence_multiplier": self.config.sigma_overconfidence_multiplier,
                "calibration_max_adjustment_pct": self.config.calibration_max_adjustment_pct,
                "calibration_min_samples": self.config.calibration_min_samples_per_segment,
                "overconfidence_active": self.config.sigma_overconfidence_multiplier != 1.0,
                "status": (
                    "widened_temporary" if self.config.sigma_overconfidence_multiplier > 1.0
                    else "narrowed_temporary" if self.config.sigma_overconfidence_multiplier < 1.0
                    else "neutral"
                ),
                "auto_tune": {
                    "enabled": self.config.auto_tune_enabled,
                    "step_size": self.config.auto_tune_step_size,
                    "min_multiplier": self.config.auto_tune_min_multiplier,
                    "max_multiplier": self.config.auto_tune_max_multiplier,
                    "target_coverage": self.config.auto_tune_target_coverage,
                    "min_samples": self.config.auto_tune_min_samples,
                    "mode": (
                        "auto" if self.config.auto_tune_enabled
                        else "manual"
                    ),
                },
            },
            "feed_health": self._feed.health,
            "clob_ws_health": self._clob_ws.health if self._clob_ws else {"connected": False, "note": "not_configured"},
            "alert_stats": self._alert_service.get_stats() if self._alert_service else {"enabled": False},
            "liquidity_scores_cached": len(self._liquidity_scores),
            "liquidity_too_low_rejections": self._m.get("rejection_reasons", {}).get("liquidity_too_low", 0),
            "stations": list(STATION_REGISTRY.keys()),
            "classified_markets": len(self._classified),
            "calibration_status": {
                "using_defaults": len(self._calibrations) == 0,
                "calibrated_stations": list(self._calibrations.keys()),
                "total_stations": len(STATION_REGISTRY),
                "sources": dict(self._calibration_sources),
                "source_summary": self._get_calibration_source_summary(),
                "calibration_source": self._get_primary_calibration_source(),
                "note": self._get_calibration_note(),
            },
            "classifications": {
                cid: {
                    "station": cm.station_id,
                    "date": cm.target_date,
                    "buckets": len(cm.buckets),
                }
                for cid, cm in self._classified.items()
            },
            "lifecycle": {
                "mode": self.config.lifecycle_mode,
                "config": {
                    "profit_capture_threshold": self.config.profit_capture_threshold,
                    "max_negative_edge_bps": self.config.max_negative_edge_bps,
                    "edge_decay_exit_pct": self.config.edge_decay_exit_pct,
                    "time_inefficiency_hours": self.config.time_inefficiency_hours,
                    "time_inefficiency_min_edge_bps": self.config.time_inefficiency_min_edge_bps,
                },
                "positions_evaluated": self._m["lifecycle"]["positions_evaluated"],
                "exit_candidates": self._m["lifecycle"]["exit_candidates"],
                "shadow_exits_total": self._m["lifecycle"]["shadow_exits"],
                "auto_exits_total": self._m["lifecycle"]["auto_exits"],
                "last_eval_time": self._m["lifecycle"]["last_eval_time"],
            },
        }

    def get_forecasts(self) -> dict:
        """Current forecast cache snapshot."""
        forecasts = {}
        for cm in self._classified.values():
            key = f"{cm.station_id}:{cm.target_date}"
            cached = self._feed.get_cached_forecast(cm.station_id, cm.target_date)
            if cached:
                forecasts[key] = cached.model_dump()
            else:
                forecasts[key] = None
        return forecasts

    def get_stations(self) -> List[dict]:
        return [s.model_dump() for s in STATION_REGISTRY.values()]

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            strategy_id=self.strategy_id,
            name=self.name,
            enabled=self._running,
            status=StrategyStatusEnum.ACTIVE if self._running else StrategyStatusEnum.STOPPED,
            parameters=self.config.model_dump(),
        )
