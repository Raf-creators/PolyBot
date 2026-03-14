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
    SHADOW_CONFIG_OVERRIDES,
)
from engine.strategies.weather_parser import (
    STATION_REGISTRY, classify_weather_market, classify_binary_weather_markets,
)
from engine.strategies.weather_pricing import (
    calibrate_sigma, compute_all_bucket_probabilities,
    compute_edge_bps, compute_weather_confidence,
    kelly_size, get_season,
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

        # Signal + execution tracking
        self._signals: List[WeatherSignal] = []
        self._active_executions: Dict[str, WeatherExecution] = {}
        self._completed_executions: List[WeatherExecution] = []
        self._order_to_execution: Dict[str, str] = {}
        self._cooldown: Dict[str, float] = {}  # key: "condition_id:token_id" → timestamp

        # Forecast accuracy service (injected from server.py)
        self._accuracy_service = None

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
        }

    # ---- Lifecycle ----

    def set_execution_context(self, risk_engine, execution_engine):
        self._risk_engine = risk_engine
        self._execution_engine = execution_engine

    def set_accuracy_service(self, service):
        """Inject forecast accuracy tracking service."""
        self._accuracy_service = service

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

                # Stage 3+4: Evaluate all classified markets
                signals = await self._evaluate_all()

                # Stage 5: Execute eligible signals
                eligible = [s for s in signals if s.is_tradable]
                for sig in eligible:
                    if len(self._active_executions) >= self.config.max_concurrent_signals:
                        break
                    await self._execute_signal(sig)

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
                self._m["gamma_events_discovered"] = len(raw_markets)
        except Exception as e:
            logger.warning(f"Gamma event discovery error: {e}")
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

        station = STATION_REGISTRY.get(cm.station_id)
        station_type = station.station_type if station else StationType.INLAND
        calibration = self._calibrations.get(cm.station_id)
        sigma = calibrate_sigma(lead_hours, month, station_type, calibration)

        if sigma > self.config.max_sigma:
            return [self._reject_signal(cm, forecast, mu, sigma, lead_hours, 0, 0,
                                        f"sigma_too_high ({sigma:.1f}F)",
                                        bucket_label="(all)")]

        # --- Compute bucket probabilities ---
        probs = compute_all_bucket_probabilities(cm.buckets, mu, sigma)

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
            if spread_sum_deviation > self.config.max_spread_sum:
                return [self._reject_signal(cm, forecast, mu, sigma, lead_hours, 0, 0,
                                            f"spread_sum_deviation ({spread_sum_deviation:.3f} > {self.config.max_spread_sum})",
                                            bucket_label="(all)")]

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

            # --- Market freshness ---
            data_age = compute_data_age(snap.updated_at)
            if data_age > self.config.max_stale_market_seconds:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"stale_market ({data_age:.0f}s)", bucket_label=bucket.label))
                continue

            # --- Liquidity ---
            liquidity = snap.liquidity
            if liquidity < self.config.min_liquidity:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"low_liquidity ({liquidity:.0f})", bucket_label=bucket.label))
                continue

            # --- Edge threshold ---
            if edge_bps < self.config.min_edge_bps:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"edge {edge_bps:.0f}bps < {self.config.min_edge_bps:.0f}bps",
                    bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price))
                continue

            # --- Confidence ---
            confidence = compute_weather_confidence(
                liquidity=liquidity,
                market_data_age_seconds=data_age,
                forecast_age_minutes=forecast_age_min or 0,
                lead_hours=lead_hours,
                sigma=sigma,
            )
            if confidence < self.config.min_confidence:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    f"confidence {confidence:.3f} < {self.config.min_confidence}",
                    bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price))
                continue

            # --- Cooldown ---
            if cooldown_key in self._cooldown:
                continue

            # --- Kill switch ---
            if self._state.risk_config.kill_switch_active:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    "kill_switch_active", bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price))
                continue

            # --- Concurrency ---
            if len(self._active_executions) >= self.config.max_concurrent_signals:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    "max_concurrent_signals", bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price))
                continue

            # --- Max buckets per market ---
            if buckets_traded >= self.config.max_buckets_per_market:
                signals.append(self._reject_signal(
                    cm, forecast, mu, sigma, lead_hours, forecast_age_min or 0, data_age,
                    "max_buckets_per_market", bucket_label=bucket.label,
                    model_prob=prob, market_price=market_price))
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
            )
            signals.append(signal)
            buckets_traded += 1
            self._m["signals_generated"] += 1

            logger.info(
                f"[WEATHER] Signal: {cm.station_id} {cm.target_date} "
                f"bucket={bucket.label} mu={mu:.1f}F sigma={sigma:.2f} "
                f"prob={prob:.4f} mkt={market_price:.4f} "
                f"edge={edge_bps:.0f}bps conf={confidence:.3f} size={size}"
            )

        return signals

    def _reject_signal(
        self, cm, forecast, mu, sigma, lead_hours,
        forecast_age_min, data_age, reason,
        bucket_label="", model_prob=0.0, market_price=0.0,
    ) -> WeatherSignal:
        """Create a rejected signal for the log and update metrics."""
        self._m["opportunities_rejected"] += 1
        bucket = reason.split(" ")[0] if reason else "unknown"
        self._m["rejection_reasons"][bucket] = self._m["rejection_reasons"].get(bucket, 0) + 1

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
        )

    # ---- Stage 5: Execution ----

    async def _execute_signal(self, signal: WeatherSignal):
        if not self._risk_engine or not self._execution_engine:
            logger.warning("No execution context; skipping weather signal")
            return

        order = OrderRecord(
            token_id=signal.token_id,
            side=OrderSide.BUY,
            price=signal.market_price,
            size=signal.recommended_size,
            strategy_id=self.strategy_id,
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

        # Emit signal event for Telegram / analytics
        await self._bus.emit(Event(
            type=EventType.SIGNAL,
            source=self.strategy_id,
            data={
                "strategy": "WEATHER",
                "asset": signal.station_id,
                "strike": signal.bucket_label,
                "fair_price": signal.model_prob,
                "market_price": signal.market_price,
                "edge_bps": signal.edge_bps,
                "side": "BUY",
                "forecast_high": signal.forecast_high_f,
                "sigma": signal.sigma,
                "lead_hours": signal.lead_hours,
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
            cal_source = (
                "historical_calibration"
                if sig.station_id in self._calibrations
                else "default_sigma_table"
            )

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

    # ---- API Data Accessors ----

    def get_signals(self, limit: int = 50) -> List[dict]:
        return [s.model_dump() for s in self._signals[:limit]]

    def get_active_executions(self) -> List[dict]:
        return [e.model_dump() for e in self._active_executions.values()]

    def get_completed_executions(self, limit: int = 50) -> List[dict]:
        return [e.model_dump() for e in self._completed_executions[-limit:]]

    def get_health(self) -> dict:
        # Determine execution mode from state
        exec_mode = "unknown"
        if self._state:
            exec_mode = self._state.trading_mode.value if hasattr(self._state, 'trading_mode') else "paper"

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
            "feed_health": self._feed.health,
            "stations": list(STATION_REGISTRY.keys()),
            "classified_markets": len(self._classified),
            "calibration_status": {
                "using_defaults": len(self._calibrations) == 0,
                "calibrated_stations": list(self._calibrations.keys()),
                "total_stations": len(STATION_REGISTRY),
                "note": "Using default NWS MOS sigma table" if not self._calibrations else "Historical calibration loaded",
            },
            "classifications": {
                cid: {
                    "station": cm.station_id,
                    "date": cm.target_date,
                    "buckets": len(cm.buckets),
                }
                for cid, cm in self._classified.items()
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
