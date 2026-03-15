"""Weather Alert Service — detects significant market changes and dispatches alerts.

Triggers:
  - Large price moves on tracked weather tokens
  - Significant edge changes between scans
  - Market becoming tradable / no longer tradable
  - Large spread-sum deviations

Debounce:
  - Per alert_key (type:station:date:bucket) cooldown window
  - Configurable via WeatherConfig.weather_alert_cooldown_seconds

Channels:
  - In-memory alert feed (served via API)
  - Telegram (if TelegramNotifier is enabled)
"""

import logging
import time
from typing import Dict, List, Optional

from engine.strategies.weather_models import (
    WeatherAlert, WeatherAlertType, WeatherConfig,
)
from models import utc_now

logger = logging.getLogger(__name__)

MAX_ALERTS = 200  # in-memory ring buffer size


class WeatherAlertService:
    def __init__(self):
        self._alerts: List[WeatherAlert] = []
        self._telegram = None
        self._config: Optional[WeatherConfig] = None

        # Debounce: key → last_alert_timestamp
        self._cooldowns: Dict[str, float] = {}

        # Previous-scan state for change detection
        self._prev_prices: Dict[str, float] = {}      # token_id → last known price
        self._prev_edges: Dict[str, float] = {}        # token_id → last computed edge
        self._prev_tradable: Dict[str, bool] = {}      # token_id → was tradable?

        # Stats
        self._total_generated = 0
        self._total_debounced = 0
        self._total_telegram_sent = 0

    def set_telegram(self, notifier):
        self._telegram = notifier

    def set_config(self, config: WeatherConfig):
        self._config = config

    @property
    def enabled(self) -> bool:
        return bool(self._config and self._config.weather_alerts_enabled)

    # ---- Core Alert Ingestion ----

    def check_and_alert(
        self,
        station_id: str,
        city: str,
        target_date: str,
        bucket_label: str,
        token_id: str,
        model_prob: float,
        market_price: float,
        edge_bps: float,
        confidence: float,
        is_tradable: bool,
    ):
        """Evaluate current state against previous and emit alerts if thresholds exceeded."""
        if not self.enabled or not self._config:
            return

        now = time.time()
        cooldown = self._config.weather_alert_cooldown_seconds

        prev_price = self._prev_prices.get(token_id)
        prev_edge = self._prev_edges.get(token_id)
        prev_trad = self._prev_tradable.get(token_id)

        # Update state for next cycle
        self._prev_prices[token_id] = market_price
        self._prev_edges[token_id] = edge_bps
        self._prev_tradable[token_id] = is_tradable

        # Skip first observation (no previous data to compare)
        if prev_price is None:
            return

        base = dict(
            station_id=station_id, city=city, target_date=target_date,
            bucket_label=bucket_label, token_id=token_id,
            model_prob=round(model_prob, 6), market_price=round(market_price, 6),
            edge_bps=round(edge_bps, 1), confidence=round(confidence, 3),
        )

        # 1) Large price move
        if prev_price > 0:
            price_move_bps = abs(market_price - prev_price) / prev_price * 10000
            if price_move_bps >= self._config.min_weather_alert_price_move_bps:
                direction = "UP" if market_price > prev_price else "DOWN"
                self._emit(
                    WeatherAlert(
                        alert_type=WeatherAlertType.PRICE_MOVE,
                        price_move_bps=round(price_move_bps, 1),
                        detail=f"Price moved {direction} {price_move_bps:.0f}bps ({prev_price:.4f} -> {market_price:.4f})",
                        **base,
                    ),
                    cooldown, now,
                )

        # 2) Edge change
        if prev_edge is not None:
            edge_delta = abs(edge_bps - prev_edge)
            if edge_delta >= self._config.min_weather_alert_edge_bps:
                direction = "widened" if edge_bps > prev_edge else "narrowed"
                self._emit(
                    WeatherAlert(
                        alert_type=WeatherAlertType.EDGE_CHANGE,
                        detail=f"Edge {direction} by {edge_delta:.0f}bps ({prev_edge:.0f} -> {edge_bps:.0f}bps)",
                        **base,
                    ),
                    cooldown, now,
                )

        # 3) Tradability change
        if prev_trad is not None and prev_trad != is_tradable:
            if is_tradable:
                self._emit(
                    WeatherAlert(
                        alert_type=WeatherAlertType.BECAME_TRADABLE,
                        detail=f"Market became TRADABLE (edge={edge_bps:.0f}bps, conf={confidence:.2f})",
                        **base,
                    ),
                    cooldown, now,
                )
            else:
                self._emit(
                    WeatherAlert(
                        alert_type=WeatherAlertType.NO_LONGER_TRADABLE,
                        detail="Market no longer tradable",
                        **base,
                    ),
                    cooldown, now,
                )

    def check_spread_deviation(
        self,
        station_id: str,
        city: str,
        target_date: str,
        spread_deviation: float,
        max_spread_sum: float,
    ):
        """Alert when the spread-sum deviates significantly from 1.0."""
        if not self.enabled or not self._config:
            return
        # Only alert when deviation exceeds 80% of the max threshold
        if spread_deviation < max_spread_sum * 0.8:
            return

        now = time.time()
        alert = WeatherAlert(
            alert_type=WeatherAlertType.SPREAD_DEVIATION,
            station_id=station_id,
            city=city,
            target_date=target_date,
            detail=f"Spread-sum deviation {spread_deviation:.3f} (max {max_spread_sum:.2f})",
        )
        self._emit(alert, self._config.weather_alert_cooldown_seconds, now)

    # ---- Internal ----

    def _emit(self, alert: WeatherAlert, cooldown: float, now: float):
        """Emit an alert if not debounced. Store in-memory and send to Telegram."""
        key = f"{alert.alert_type.value}:{alert.station_id}:{alert.target_date}:{alert.bucket_label}"

        last_sent = self._cooldowns.get(key, 0)
        if now - last_sent < cooldown:
            self._total_debounced += 1
            return

        self._cooldowns[key] = now
        self._total_generated += 1

        # Store in ring buffer
        self._alerts.insert(0, alert)
        if len(self._alerts) > MAX_ALERTS:
            self._alerts = self._alerts[:MAX_ALERTS]

        # Telegram dispatch (fire-and-forget)
        if self._telegram and self._telegram.enabled:
            msg = self._format_telegram(alert)
            self._telegram._fire(msg)
            self._total_telegram_sent += 1

        logger.info(f"[WEATHER ALERT] {alert.alert_type.value}: {alert.detail}")

        # Evict old cooldown entries (>10x cooldown age)
        stale_cutoff = now - (cooldown * 10)
        self._cooldowns = {k: v for k, v in self._cooldowns.items() if v > stale_cutoff}

    # ---- Telegram Formatting ----

    @staticmethod
    def _format_telegram(alert: WeatherAlert) -> str:
        type_labels = {
            WeatherAlertType.PRICE_MOVE: "PRICE MOVE",
            WeatherAlertType.EDGE_CHANGE: "EDGE CHANGE",
            WeatherAlertType.BECAME_TRADABLE: "NOW TRADABLE",
            WeatherAlertType.NO_LONGER_TRADABLE: "NOT TRADABLE",
            WeatherAlertType.SPREAD_DEVIATION: "SPREAD WARN",
        }
        type_label = type_labels.get(alert.alert_type, alert.alert_type.value.upper())

        lines = [f"<b>[WEATHER {type_label}]</b>"]
        lines.append(f"Station: {alert.station_id} ({alert.city})" if alert.city else f"Station: {alert.station_id}")
        lines.append(f"Date: {alert.target_date}")
        if alert.bucket_label:
            lines.append(f"Bucket: {alert.bucket_label}")
        if alert.model_prob > 0:
            lines.append(f"Model: {alert.model_prob:.4f}  Mkt: {alert.market_price:.4f}")
        if alert.edge_bps != 0:
            lines.append(f"Edge: {alert.edge_bps:.0f}bps")
        if alert.confidence > 0:
            lines.append(f"Confidence: {alert.confidence:.2f}")
        if alert.price_move_bps > 0:
            lines.append(f"Price Move: {alert.price_move_bps:.0f}bps")
        lines.append(f"Detail: {alert.detail}")

        return "\n".join(lines)

    # ---- API Data ----

    def get_alerts(self, limit: int = 50) -> List[dict]:
        return [a.model_dump() for a in self._alerts[:limit]]

    def get_stats(self) -> dict:
        return {
            "total_generated": self._total_generated,
            "total_debounced": self._total_debounced,
            "total_telegram_sent": self._total_telegram_sent,
            "active_cooldowns": len(self._cooldowns),
            "alerts_buffered": len(self._alerts),
            "enabled": self.enabled,
        }
