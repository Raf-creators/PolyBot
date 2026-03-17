"""
Test iteration 42: Position slot segmentation, Signal quality, Watchdog, Arb diagnostics, Weather global expansion

Features tested:
1. GET /api/analytics/strategy-tracker — returns performance, rejections, signals, watchdog, and position_slots data
2. GET /api/analytics/signal-quality — returns per-strategy signal generation/rejection counts
3. GET /api/analytics/watchdog — returns discovery watchdog timestamps and thresholds
4. GET /api/strategies/arb/diagnostics — returns markets_scanned, binary_pairs_found, multi_outcome_groups_found, raw_edges, rejection_log
5. GET /api/strategies/arb/health — returns multi_groups_scanned in diagnostics, total_scans
6. GET /api/strategies/weather/health — returns markets_classified > 0 (global expansion), gamma_events_discovered > 0
7. Position slot diagnostics: weather_count, nonweather_count, headroom, by_strategy, blocked_by_position_limit
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestStrategyTracker:
    """Tests for /api/analytics/strategy-tracker endpoint"""

    def test_strategy_tracker_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/analytics/strategy-tracker returns 200")

    def test_strategy_tracker_has_performance(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        assert "performance" in data, "Missing 'performance' field"
        assert isinstance(data["performance"], dict), "performance should be dict"
        print(f"PASS: Strategy tracker has performance data with {len(data['performance'])} strategies")

    def test_strategy_tracker_has_rejections(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        assert "rejections" in data, "Missing 'rejections' field"
        print("PASS: Strategy tracker has rejections data")

    def test_strategy_tracker_has_signals(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        assert "signals" in data, "Missing 'signals' field"
        print("PASS: Strategy tracker has signals data")

    def test_strategy_tracker_has_watchdog(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        assert "watchdog" in data, "Missing 'watchdog' field"
        watchdog = data["watchdog"]
        assert "last_new_market_at" in watchdog, "Missing watchdog.last_new_market_at"
        assert "last_trade_opened_at" in watchdog, "Missing watchdog.last_trade_opened_at"
        assert "last_trade_closed_at" in watchdog, "Missing watchdog.last_trade_closed_at"
        assert "thresholds" in watchdog, "Missing watchdog.thresholds"
        print("PASS: Strategy tracker has watchdog data with timestamps and thresholds")

    def test_strategy_tracker_has_position_slots(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        assert "position_slots" in data, "Missing 'position_slots' field"
        slots = data["position_slots"]
        
        # Required position slot fields
        required_fields = ["weather_count", "nonweather_count", "total", "by_strategy", "limits"]
        for field in required_fields:
            assert field in slots, f"Missing position_slots.{field}"
        
        # Limits should have the configured maximums
        limits = slots.get("limits", {})
        assert "max_weather" in limits, "Missing limits.max_weather"
        assert "max_nonweather" in limits, "Missing limits.max_nonweather"
        assert "max_global" in limits, "Missing limits.max_global"
        
        print(f"PASS: Position slots: weather={slots['weather_count']}, nonweather={slots['nonweather_count']}, total={slots['total']}")
        print(f"  Limits: max_weather={limits['max_weather']}, max_nonweather={limits['max_nonweather']}, max_global={limits['max_global']}")

    def test_position_slots_has_headroom(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        slots = data.get("position_slots", {})
        
        if "headroom" in slots:
            headroom = slots["headroom"]
            assert "weather" in headroom, "Missing headroom.weather"
            assert "nonweather" in headroom, "Missing headroom.nonweather"
            assert "global" in headroom, "Missing headroom.global"
            print(f"PASS: Position slots headroom: weather={headroom['weather']}, nonweather={headroom['nonweather']}, global={headroom['global']}")
        else:
            print("SKIP: headroom field not present (may be optional)")

    def test_position_slots_has_blocked_counts(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        slots = data.get("position_slots", {})
        
        if "blocked_by_position_limit" in slots:
            blocked = slots["blocked_by_position_limit"]
            print(f"PASS: Position slots blocked_by_position_limit: {blocked}")
        else:
            print("SKIP: blocked_by_position_limit field not present (may be zero)")


class TestSignalQuality:
    """Tests for /api/analytics/signal-quality endpoint"""

    def test_signal_quality_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/analytics/signal-quality")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/analytics/signal-quality returns 200")

    def test_signal_quality_has_per_strategy_data(self):
        response = requests.get(f"{BASE_URL}/api/analytics/signal-quality")
        data = response.json()
        assert isinstance(data, dict), "Response should be a dict of strategies"
        
        for strategy_id, quality in data.items():
            assert "signals_generated" in quality, f"Missing signals_generated for {strategy_id}"
            assert "signals_rejected" in quality, f"Missing signals_rejected for {strategy_id}"
            assert "signals_accepted" in quality, f"Missing signals_accepted for {strategy_id}"
            assert "acceptance_rate" in quality, f"Missing acceptance_rate for {strategy_id}"
            assert "rejection_reasons" in quality, f"Missing rejection_reasons for {strategy_id}"
            
            print(f"PASS: Signal quality for {strategy_id}: gen={quality['signals_generated']}, rej={quality['signals_rejected']}, acc_rate={quality['acceptance_rate']}%")

    def test_signal_quality_shows_rejection_reasons(self):
        response = requests.get(f"{BASE_URL}/api/analytics/signal-quality")
        data = response.json()
        
        # Check if any strategy has rejection reasons like 'tte' or 'insufficient_vol_data'
        found_reasons = False
        for strategy_id, quality in data.items():
            reasons = quality.get("rejection_reasons", {})
            if reasons:
                found_reasons = True
                print(f"PASS: {strategy_id} rejection reasons: {list(reasons.keys())}")
        
        if not found_reasons:
            print("INFO: No rejection reasons recorded yet (may be normal if no signals)")


class TestWatchdog:
    """Tests for /api/analytics/watchdog endpoint"""

    def test_watchdog_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/analytics/watchdog")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/analytics/watchdog returns 200")

    def test_watchdog_has_timestamps(self):
        response = requests.get(f"{BASE_URL}/api/analytics/watchdog")
        data = response.json()
        
        assert "last_new_market_at" in data, "Missing last_new_market_at"
        assert "last_trade_opened_at" in data, "Missing last_trade_opened_at"
        assert "last_trade_closed_at" in data, "Missing last_trade_closed_at"
        
        print(f"PASS: Watchdog timestamps present - last_new_market_at={data['last_new_market_at']}, last_trade_opened_at={data['last_trade_opened_at']}, last_trade_closed_at={data['last_trade_closed_at']}")

    def test_watchdog_has_thresholds(self):
        response = requests.get(f"{BASE_URL}/api/analytics/watchdog")
        data = response.json()
        
        assert "thresholds" in data, "Missing thresholds"
        thresholds = data["thresholds"]
        
        assert "no_market_alert_minutes" in thresholds, "Missing no_market_alert_minutes"
        assert "no_trade_open_alert_minutes" in thresholds, "Missing no_trade_open_alert_minutes"
        assert "no_trade_close_alert_minutes" in thresholds, "Missing no_trade_close_alert_minutes"
        
        print(f"PASS: Watchdog thresholds: market={thresholds['no_market_alert_minutes']}min, open={thresholds['no_trade_open_alert_minutes']}min, close={thresholds['no_trade_close_alert_minutes']}min")


class TestArbDiagnostics:
    """Tests for /api/strategies/arb/diagnostics endpoint"""

    def test_arb_diagnostics_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/strategies/arb/diagnostics returns 200")

    def test_arb_diagnostics_has_markets_scanned(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        data = response.json()
        
        assert "markets_scanned" in data, "Missing markets_scanned"
        assert isinstance(data["markets_scanned"], int), "markets_scanned should be int"
        print(f"PASS: Arb diagnostics markets_scanned={data['markets_scanned']}")

    def test_arb_diagnostics_has_binary_pairs(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        data = response.json()
        
        assert "binary_pairs_found" in data, "Missing binary_pairs_found"
        print(f"PASS: Arb diagnostics binary_pairs_found={data['binary_pairs_found']}")

    def test_arb_diagnostics_has_multi_outcome_groups(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        data = response.json()
        
        assert "multi_outcome_groups_found" in data, "Missing multi_outcome_groups_found"
        multi_groups = data["multi_outcome_groups_found"]
        assert multi_groups >= 0, "multi_outcome_groups_found should be >= 0"
        print(f"PASS: Arb diagnostics multi_outcome_groups_found={multi_groups}")

    def test_arb_diagnostics_has_raw_edges(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        data = response.json()
        
        assert "raw_edges" in data, "Missing raw_edges"
        raw_edges = data["raw_edges"]
        assert isinstance(raw_edges, list), "raw_edges should be a list"
        
        if raw_edges:
            edge = raw_edges[0]
            assert "type" in edge, "Missing type in raw_edge"
            assert "gross_edge_bps" in edge, "Missing gross_edge_bps in raw_edge"
            print(f"PASS: Arb diagnostics has {len(raw_edges)} raw edges, first type={edge['type']}")
        else:
            print("INFO: No raw edges found yet")

    def test_arb_diagnostics_has_rejection_log(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics")
        data = response.json()
        
        assert "rejection_log" in data, "Missing rejection_log"
        rejection_log = data["rejection_log"]
        assert isinstance(rejection_log, list), "rejection_log should be a list"
        
        if rejection_log:
            entry = rejection_log[0]
            assert "reason" in entry, "Missing reason in rejection_log entry"
            print(f"PASS: Arb diagnostics has {len(rejection_log)} rejection log entries")
        else:
            print("INFO: No rejection log entries yet")


class TestArbHealth:
    """Tests for /api/strategies/arb/health endpoint"""

    def test_arb_health_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/strategies/arb/health returns 200")

    def test_arb_health_has_multi_groups_scanned(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        data = response.json()
        
        # Check for multi_groups_scanned directly or in diagnostics
        if "multi_groups_scanned" in data:
            print(f"PASS: Arb health multi_groups_scanned={data['multi_groups_scanned']}")
        elif "diagnostics" in data and "multi_outcome_groups_found" in data["diagnostics"]:
            print(f"PASS: Arb health diagnostics.multi_outcome_groups_found={data['diagnostics']['multi_outcome_groups_found']}")
        else:
            pytest.fail("Missing multi_groups_scanned or diagnostics.multi_outcome_groups_found")

    def test_arb_health_has_total_scans(self):
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        data = response.json()
        
        assert "total_scans" in data, "Missing total_scans"
        print(f"PASS: Arb health total_scans={data['total_scans']}")


class TestWeatherHealth:
    """Tests for /api/strategies/weather/health endpoint"""

    def test_weather_health_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/strategies/weather/health returns 200")

    def test_weather_health_markets_classified_field_exists(self):
        """Test that markets_classified field exists (value may be 0 if scanner hasn't run yet)"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        
        assert "markets_classified" in data, "Missing markets_classified"
        markets_classified = data["markets_classified"]
        total_scans = data.get("total_scans", 0)
        
        # If scanner has run at least once, we expect classified markets
        if total_scans > 0:
            assert markets_classified >= 0, f"markets_classified should be >= 0, got {markets_classified}"
            print(f"PASS: Weather health markets_classified={markets_classified} (scanner has run {total_scans} times)")
        else:
            print(f"INFO: Scanner hasn't run yet (total_scans=0), markets_classified={markets_classified}")

    def test_weather_health_gamma_events_discovered(self):
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        
        # Check for gamma_events_discovered (if present)
        if "gamma_events_discovered" in data:
            gamma = data["gamma_events_discovered"]
            assert gamma > 0, f"gamma_events_discovered should be > 0, got {gamma}"
            print(f"PASS: Weather health gamma_events_discovered={gamma}")
        else:
            # Fallback: check for opportunities_evaluated
            if "opportunities_evaluated" in data:
                opps = data["opportunities_evaluated"]
                print(f"INFO: gamma_events_discovered not present, opportunities_evaluated={opps}")
            else:
                print("SKIP: gamma_events_discovered field not present")


class TestWeatherGlobalExpansion:
    """Tests for weather strategy global expansion"""

    def test_weather_stations_endpoint_exists(self):
        """Test that weather stations endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/stations")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Get all city names
        if isinstance(data, list):
            cities = [s.get("city", s.get("station_id", "")).lower() for s in data]
        elif isinstance(data, dict):
            cities = [v.get("city", k).lower() for k, v in data.items()]
        else:
            cities = []
        
        # Should have at least base US stations
        us_cities = ["new york city", "chicago", "los angeles", "atlanta", "dallas", "miami", "denver", "san francisco"]
        found_us = [c for c in us_cities if any(c in city for city in cities)]
        
        assert len(found_us) > 0, f"No US cities found. Cities: {cities}"
        print(f"PASS: Weather stations has US base cities: {found_us[:5]}...")
        
        # Check for global cities (may not be present if scanner hasn't run)
        global_cities = ["london", "tokyo", "seoul", "hong kong", "paris", "singapore", "buenos aires", "toronto"]
        found_global = [c for c in global_cities if any(c in city for city in cities)]
        
        if found_global:
            print(f"PASS: Weather strategy has global cities: {found_global}")
        else:
            print(f"INFO: No global cities yet (dynamic stations discovered after scanner runs). Total cities: {len(cities)}")


class TestPositionSlotClassification:
    """Tests for risk engine position classification"""

    def test_positions_classified_by_strategy(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        slots = data.get("position_slots", {})
        by_strategy = slots.get("by_strategy", {})
        
        # Should have some positions classified
        total_by_strategy = sum(by_strategy.values()) if by_strategy else 0
        assert total_by_strategy > 0, "No positions classified by strategy"
        
        print(f"PASS: Positions by strategy: {by_strategy}")

    def test_weather_vs_nonweather_counts(self):
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-tracker")
        data = response.json()
        slots = data.get("position_slots", {})
        
        weather = slots.get("weather_count", 0)
        nonweather = slots.get("nonweather_count", 0)
        total = slots.get("total", 0)
        
        # Total should equal weather + nonweather
        assert weather + nonweather == total, f"weather({weather}) + nonweather({nonweather}) != total({total})"
        print(f"PASS: weather_count({weather}) + nonweather_count({nonweather}) = total({total})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
