"""Unit tests for WeatherAlertService — debounce, thresholds, alert types."""

import time
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.weather_alert_service import WeatherAlertService
from engine.strategies.weather_models import WeatherConfig, WeatherAlertType


@pytest.fixture
def service():
    svc = WeatherAlertService()
    svc.set_config(WeatherConfig(
        weather_alerts_enabled=True,
        min_weather_alert_edge_bps=200.0,
        min_weather_alert_price_move_bps=300.0,
        weather_alert_cooldown_seconds=5.0,
    ))
    return svc


class TestAlertGeneration:
    def test_no_alert_on_first_observation(self, service):
        """First call sets baseline, should not generate alert."""
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok1",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        assert len(service.get_alerts()) == 0

    def test_price_move_alert(self, service):
        """Large price move should trigger an alert."""
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok1",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        # Now price moves by 4% (400bps > 300bps threshold)
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok1",
            model_prob=0.3, market_price=0.26, edge_bps=400,
            confidence=0.7, is_tradable=True,
        )
        alerts = service.get_alerts()
        assert len(alerts) >= 1
        price_alerts = [a for a in alerts if a["alert_type"] == "price_move"]
        assert len(price_alerts) == 1
        assert price_alerts[0]["station_id"] == "KLGA"

    def test_small_price_move_no_alert(self, service):
        """Small price move should not trigger an alert."""
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok2",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        # Only 0.5% move (50bps < 300bps threshold)
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok2",
            model_prob=0.3, market_price=0.25125, edge_bps=490,
            confidence=0.7, is_tradable=True,
        )
        alerts = service.get_alerts()
        price_alerts = [a for a in alerts if a["alert_type"] == "price_move"]
        assert len(price_alerts) == 0

    def test_edge_change_alert(self, service):
        """Large edge change should trigger an alert."""
        service.check_and_alert(
            station_id="KORD", city="Chicago", target_date="2026-03-21",
            bucket_label="55-56F", token_id="tok3",
            model_prob=0.4, market_price=0.35, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        # Edge changes by 300bps (> 200bps threshold)
        service.check_and_alert(
            station_id="KORD", city="Chicago", target_date="2026-03-21",
            bucket_label="55-56F", token_id="tok3",
            model_prob=0.4, market_price=0.35, edge_bps=200,
            confidence=0.7, is_tradable=True,
        )
        alerts = service.get_alerts()
        edge_alerts = [a for a in alerts if a["alert_type"] == "edge_change"]
        assert len(edge_alerts) == 1
        assert "narrowed" in edge_alerts[0]["detail"]

    def test_became_tradable_alert(self, service):
        """Market becoming tradable should trigger an alert."""
        service.check_and_alert(
            station_id="KATL", city="Atlanta", target_date="2026-03-22",
            bucket_label="60-61F", token_id="tok4",
            model_prob=0.3, market_price=0.28, edge_bps=200,
            confidence=0.7, is_tradable=False,
        )
        service.check_and_alert(
            station_id="KATL", city="Atlanta", target_date="2026-03-22",
            bucket_label="60-61F", token_id="tok4",
            model_prob=0.35, market_price=0.28, edge_bps=700,
            confidence=0.7, is_tradable=True,
        )
        alerts = service.get_alerts()
        trad_alerts = [a for a in alerts if a["alert_type"] == "became_tradable"]
        assert len(trad_alerts) == 1

    def test_no_longer_tradable_alert(self, service):
        """Market becoming non-tradable should trigger an alert."""
        service.check_and_alert(
            station_id="KDFW", city="Dallas", target_date="2026-03-23",
            bucket_label="70-71F", token_id="tok5",
            model_prob=0.35, market_price=0.28, edge_bps=700,
            confidence=0.7, is_tradable=True,
        )
        service.check_and_alert(
            station_id="KDFW", city="Dallas", target_date="2026-03-23",
            bucket_label="70-71F", token_id="tok5",
            model_prob=0.3, market_price=0.29, edge_bps=100,
            confidence=0.3, is_tradable=False,
        )
        alerts = service.get_alerts()
        not_trad = [a for a in alerts if a["alert_type"] == "no_longer_tradable"]
        assert len(not_trad) == 1

    def test_spread_deviation_alert(self, service):
        """Spread-sum deviation near threshold should trigger an alert."""
        # 80% of max_spread_sum (0.30) = 0.24
        service.check_spread_deviation(
            station_id="KMIA", city="Miami", target_date="2026-03-24",
            spread_deviation=0.28, max_spread_sum=0.30,
        )
        alerts = service.get_alerts()
        spread_alerts = [a for a in alerts if a["alert_type"] == "spread_deviation"]
        assert len(spread_alerts) == 1

    def test_spread_deviation_no_alert_low(self, service):
        """Low spread deviation should not trigger."""
        service.check_spread_deviation(
            station_id="KMIA", city="Miami", target_date="2026-03-24",
            spread_deviation=0.10, max_spread_sum=0.30,
        )
        alerts = service.get_alerts()
        assert len(alerts) == 0


class TestDebounce:
    def test_debounce_blocks_rapid_alerts(self, service):
        """Same alert type+market should be debounced within cooldown."""
        # First observation
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok_debounce",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=False,
        )
        # First tradability change
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok_debounce",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        count_1 = len([a for a in service.get_alerts() if a["alert_type"] == "became_tradable"])
        assert count_1 == 1

        # Flip again within cooldown — should be debounced
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok_debounce",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=False,
        )
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok_debounce",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        count_2 = len([a for a in service.get_alerts() if a["alert_type"] == "became_tradable"])
        assert count_2 == 1  # debounced
        assert service._total_debounced >= 1


class TestDisabled:
    def test_no_alerts_when_disabled(self):
        """No alerts when weather_alerts_enabled=False."""
        svc = WeatherAlertService()
        svc.set_config(WeatherConfig(weather_alerts_enabled=False))
        svc.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok_disabled",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        assert len(svc.get_alerts()) == 0

    def test_no_alerts_without_config(self):
        """No alerts when config is not set."""
        svc = WeatherAlertService()
        svc.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok_noconf",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        assert len(svc.get_alerts()) == 0


class TestStats:
    def test_stats_shape(self, service):
        stats = service.get_stats()
        assert "total_generated" in stats
        assert "total_debounced" in stats
        assert "total_telegram_sent" in stats
        assert "active_cooldowns" in stats
        assert "alerts_buffered" in stats
        assert "enabled" in stats
        assert stats["enabled"] is True

    def test_alerts_output_shape(self, service):
        """get_alerts() returns list of dicts with expected keys."""
        # Generate one alert
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok_shape",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=False,
        )
        service.check_and_alert(
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", token_id="tok_shape",
            model_prob=0.3, market_price=0.25, edge_bps=500,
            confidence=0.7, is_tradable=True,
        )
        alerts = service.get_alerts()
        assert len(alerts) >= 1
        a = alerts[0]
        assert "id" in a
        assert "alert_type" in a
        assert "station_id" in a
        assert "target_date" in a
        assert "timestamp" in a
        assert "detail" in a


class TestTelegramFormat:
    def test_format_price_move(self):
        from engine.strategies.weather_models import WeatherAlert
        alert = WeatherAlert(
            alert_type=WeatherAlertType.PRICE_MOVE,
            station_id="KLGA", city="NYC", target_date="2026-03-20",
            bucket_label="43-44F", model_prob=0.3, market_price=0.26,
            edge_bps=400, price_move_bps=400,
            detail="Price moved UP 400bps (0.2500 -> 0.2600)",
        )
        msg = WeatherAlertService._format_telegram(alert)
        assert "[WEATHER PRICE MOVE]" in msg
        assert "KLGA" in msg
        assert "400bps" in msg

    def test_format_became_tradable(self):
        from engine.strategies.weather_models import WeatherAlert
        alert = WeatherAlert(
            alert_type=WeatherAlertType.BECAME_TRADABLE,
            station_id="KORD", city="Chicago", target_date="2026-03-21",
            bucket_label="55-56F", edge_bps=700,
            detail="Market became TRADABLE (edge=700bps, conf=0.75)",
        )
        msg = WeatherAlertService._format_telegram(alert)
        assert "[WEATHER NOW TRADABLE]" in msg
        assert "KORD" in msg
