"""
Test iteration 58: Debug State Snapshot endpoint
/api/debug/state-snapshot

Tests:
- Auth: header vs query param, 403 on missing/wrong key
- Freshness metadata fields
- Position grouping by strategy (weather, crypto, arb)
- Token ID truncation to 12 chars (security)
- Lifecycle data in positions
- Lifecycle summary with config including slot rotation
- Exit candidates detail array
- Entry quality with rejections/passed signals
- PnL summary
- Strategy health (weather, crypto_sniper, arb_scanner)
- Weather config fields
- Security: no secrets exposed
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
DEBUG_KEY = "test-snapshot-key-preview"


class TestStateSnapshotAuth:
    """Authentication tests for the snapshot endpoint"""

    def test_snapshot_returns_403_no_key(self):
        """Returns 403 when no key provided"""
        resp = requests.get(f"{BASE_URL}/api/debug/state-snapshot")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("PASS: Returns 403 when no key provided")

    def test_snapshot_returns_403_wrong_key(self):
        """Returns 403 when wrong key provided"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": "wrong-key-12345"}
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        print("PASS: Returns 403 when wrong key provided")

    def test_snapshot_works_with_header(self):
        """Works with X-Debug-Snapshot-Key header"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "freshness" in data, "Missing freshness in response"
        print("PASS: Works with X-Debug-Snapshot-Key header")

    def test_snapshot_works_with_query_param(self):
        """Works with ?key= query param fallback"""
        resp = requests.get(f"{BASE_URL}/api/debug/state-snapshot?key={DEBUG_KEY}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "freshness" in data, "Missing freshness in response"
        print("PASS: Works with ?key= query param fallback")


class TestSnapshotFreshness:
    """Tests for freshness metadata"""

    def test_freshness_snapshot_at(self):
        """Freshness contains snapshot_at timestamp"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        freshness = data.get("freshness", {})
        assert "snapshot_at" in freshness, "Missing snapshot_at"
        assert freshness["snapshot_at"] is not None, "snapshot_at is null"
        # Verify ISO format
        assert "T" in freshness["snapshot_at"], "snapshot_at not in ISO format"
        print(f"PASS: freshness.snapshot_at = {freshness['snapshot_at']}")

    def test_freshness_snapshot_version(self):
        """Freshness contains snapshot_version = 1.0"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        freshness = data.get("freshness", {})
        assert "snapshot_version" in freshness, "Missing snapshot_version"
        assert freshness["snapshot_version"] == "1.0", f"Unexpected version: {freshness['snapshot_version']}"
        print(f"PASS: freshness.snapshot_version = {freshness['snapshot_version']}")

    def test_freshness_server_start_time(self):
        """Freshness contains server_start_time"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        freshness = data.get("freshness", {})
        assert "server_start_time" in freshness, "Missing server_start_time"
        print(f"PASS: freshness.server_start_time = {freshness.get('server_start_time')}")

    def test_freshness_uptime_seconds(self):
        """Freshness contains uptime_seconds"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        freshness = data.get("freshness", {})
        assert "uptime_seconds" in freshness, "Missing uptime_seconds"
        assert isinstance(freshness["uptime_seconds"], (int, float)), "uptime_seconds not a number"
        print(f"PASS: freshness.uptime_seconds = {freshness['uptime_seconds']}")

    def test_freshness_last_weather_scan_time(self):
        """Freshness contains last_weather_scan_time"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        freshness = data.get("freshness", {})
        assert "last_weather_scan_time" in freshness, "Missing last_weather_scan_time"
        print(f"PASS: freshness.last_weather_scan_time = {freshness.get('last_weather_scan_time')}")

    def test_freshness_weather_total_scans(self):
        """Freshness contains weather_total_scans"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        freshness = data.get("freshness", {})
        assert "weather_total_scans" in freshness, "Missing weather_total_scans"
        assert isinstance(freshness["weather_total_scans"], (int, float)), "weather_total_scans not a number"
        print(f"PASS: freshness.weather_total_scans = {freshness['weather_total_scans']}")

    def test_freshness_git_commit(self):
        """Freshness contains git_commit"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        freshness = data.get("freshness", {})
        assert "git_commit" in freshness, "Missing git_commit"
        print(f"PASS: freshness.git_commit = {freshness.get('git_commit')}")


class TestSnapshotPositions:
    """Tests for positions structure"""

    def test_positions_grouped_by_strategy(self):
        """Positions are grouped by strategy: weather, crypto, arb"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        positions = data.get("positions", {})
        position_counts = data.get("position_counts", {})

        # Check we have the positions dict and position_counts
        assert isinstance(positions, dict), "positions not a dict"
        assert isinstance(position_counts, dict), "position_counts not a dict"

        # Valid strategy keys
        valid_strategies = {"weather", "crypto", "arb", "weather_asymmetric", "other", "unknown"}
        for key in positions.keys():
            assert key in valid_strategies, f"Unexpected strategy key: {key}"

        print(f"PASS: Positions grouped by strategy. Counts: {position_counts}")

    def test_position_token_ids_truncated(self):
        """All token_ids in positions are max 12 characters"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        positions = data.get("positions", {})

        violations = []
        total_checked = 0
        for strategy, pos_list in positions.items():
            for pos in pos_list:
                token_id = pos.get("token_id", "")
                total_checked += 1
                if len(token_id) > 12:
                    violations.append(f"{strategy}: {token_id} ({len(token_id)} chars)")

        assert len(violations) == 0, f"Token IDs exceeding 12 chars: {violations}"
        print(f"PASS: All {total_checked} position token_ids <= 12 chars")

    def test_weather_positions_have_lifecycle(self):
        """Weather positions include lifecycle data"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        positions = data.get("positions", {})

        weather_positions = positions.get("weather", [])
        if len(weather_positions) == 0:
            pytest.skip("No weather positions to check lifecycle")

        # Check at least some have lifecycle
        with_lifecycle = [p for p in weather_positions if "lifecycle" in p and p["lifecycle"]]
        print(f"Weather positions: {len(weather_positions)}, with lifecycle: {len(with_lifecycle)}")

        if len(with_lifecycle) > 0:
            # Verify lifecycle fields
            lc = with_lifecycle[0]["lifecycle"]
            expected_fields = ["is_exit_candidate", "book_rank", "book_score", "book_total"]
            for field in expected_fields:
                assert field in lc, f"Missing lifecycle field: {field}"
            print(f"PASS: Weather positions have lifecycle data (sample: book_rank={lc.get('book_rank')})")
        else:
            print("PASS: Weather positions exist but no lifecycle evals yet (acceptable)")


class TestSnapshotLifecycle:
    """Tests for lifecycle section"""

    def test_lifecycle_mode_and_config(self):
        """Lifecycle contains mode and config with all thresholds including slot rotation"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        lifecycle = data.get("lifecycle", {})

        assert "mode" in lifecycle, "Missing lifecycle.mode"
        assert "config" in lifecycle, "Missing lifecycle.config"

        config = lifecycle["config"]
        expected_config_keys = [
            "profit_capture_threshold",
            "max_negative_edge_bps",
            "edge_decay_exit_pct",
            "time_inefficiency_hours",
            "time_inefficiency_min_edge_bps",
            "slot_rotation_enabled",
            "slot_rotation_bottom_pct",
            "slot_rotation_min_hours_to_res",
            "slot_rotation_max_edge_bps",
            "slot_rotation_max_profit_mult",
        ]
        for key in expected_config_keys:
            assert key in config, f"Missing lifecycle.config.{key}"

        print(f"PASS: Lifecycle mode={lifecycle['mode']}, config has slot rotation settings")

    def test_lifecycle_exit_candidates_detail(self):
        """Lifecycle contains exit_candidates_detail array"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        lifecycle = data.get("lifecycle", {})

        assert "exit_candidates_detail" in lifecycle, "Missing lifecycle.exit_candidates_detail"
        assert isinstance(lifecycle["exit_candidates_detail"], list), "exit_candidates_detail not a list"

        # If there are candidates, check structure
        candidates = lifecycle["exit_candidates_detail"]
        if len(candidates) > 0:
            candidate = candidates[0]
            expected_fields = ["token_id", "exit_reason", "profit_multiple", "book_rank", "book_total"]
            for field in expected_fields:
                assert field in candidate, f"Missing exit_candidates_detail[].{field}"
            # Check token_id truncation
            assert len(candidate["token_id"]) <= 12, "exit candidate token_id not truncated"

        print(f"PASS: Lifecycle exit_candidates_detail has {len(candidates)} candidates")


class TestSnapshotEntryQuality:
    """Tests for entry_quality section"""

    def test_entry_quality_rejections_and_passed(self):
        """Entry quality contains rejections and passed_signals stats"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        entry_quality = data.get("entry_quality", {})

        assert "rejections" in entry_quality, "Missing entry_quality.rejections"
        assert "passed_signals" in entry_quality, "Missing entry_quality.passed_signals"

        rejections = entry_quality["rejections"]
        expected_rejection_keys = ["low_quality", "low_edge_long", "long_hold_penalty"]
        for key in expected_rejection_keys:
            assert key in rejections, f"Missing rejections.{key}"

        passed = entry_quality["passed_signals"]
        expected_passed_keys = ["total", "avg_quality", "avg_edge_bps", "avg_lead_hours"]
        for key in expected_passed_keys:
            assert key in passed, f"Missing passed_signals.{key}"

        print(f"PASS: Entry quality has rejections: {rejections}, passed_signals.total: {passed.get('total')}")


class TestSnapshotPnlSummary:
    """Tests for pnl_summary section"""

    def test_pnl_summary_fields(self):
        """PnL summary contains total_realized, total_unrealized, total, open_positions"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        pnl = data.get("pnl_summary", {})

        expected_keys = ["total_realized", "total_unrealized", "total", "open_positions"]
        for key in expected_keys:
            assert key in pnl, f"Missing pnl_summary.{key}"

        print(f"PASS: PnL summary - realized={pnl['total_realized']}, unrealized={pnl['total_unrealized']}, total={pnl['total']}, open_positions={pnl['open_positions']}")


class TestSnapshotStrategyHealth:
    """Tests for strategy_health section"""

    def test_strategy_health_entries(self):
        """Strategy health contains weather, crypto_sniper, arb_scanner entries"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        health = data.get("strategy_health", {})

        # Check expected strategies are present
        expected = ["weather", "crypto_sniper", "arb_scanner"]
        for strat in expected:
            assert strat in health, f"Missing strategy_health.{strat}"

        # Weather should have detailed info
        weather_health = health.get("weather", {})
        assert "total_scans" in weather_health, "Missing weather.total_scans"
        assert "signals_generated" in weather_health, "Missing weather.signals_generated"

        print(f"PASS: Strategy health has {list(health.keys())}")


class TestSnapshotWeatherConfig:
    """Tests for weather_config section"""

    def test_weather_config_fields(self):
        """Weather config contains full WeatherConfig fields"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        wc = data.get("weather_config", {})

        # Check key config fields are present
        expected_fields = [
            "min_edge_bps",
            "min_confidence",
            "max_weather_positions",
            "lifecycle_mode",
            "profit_capture_threshold",
            "default_size",
            "kelly_scale",
            "slot_rotation_enabled",
        ]
        for field in expected_fields:
            assert field in wc, f"Missing weather_config.{field}"

        print(f"PASS: Weather config has {len(wc)} fields including lifecycle_mode={wc.get('lifecycle_mode')}")


class TestSnapshotSecurity:
    """Security tests: no secrets exposed"""

    def test_no_api_keys_exposed(self):
        """Snapshot does NOT contain any API keys"""
        resp = requests.get(
            f"{BASE_URL}/api/debug/state-snapshot",
            headers={"X-Debug-Snapshot-Key": DEBUG_KEY}
        )
        assert resp.status_code == 200
        text = resp.text.lower()

        # Check for common secret patterns
        secret_patterns = [
            r"api[_-]?key",
            r"api[_-]?secret",
            r"private[_-]?key",
            r"passphrase",
            r"password",
            r"secret[_-]?key",
        ]

        # These patterns should not appear in values
        # (keys like "min_edge_bps" are okay, but actual secret values should not)
        data_str = resp.text

        # Check for known env var prefixes with values
        dangerous_patterns = [
            "POLY_API",
            "POLYMARKET_PRIVATE",
            "POLYMARKET_API",
            "TELEGRAM_BOT_TOKEN",
            "MONGO_URL",
            "mongodb://",
            "mongodb+srv://",
        ]

        violations = []
        for pattern in dangerous_patterns:
            if pattern.lower() in text:
                # Check if it's a key name vs a value
                # If the pattern appears as a JSON value (not key), that's a problem
                if f'"{pattern.lower()}"' not in text and pattern.lower() in text:
                    violations.append(pattern)

        # More strict: search for actual secret formats
        # Wallet addresses (0x...)
        wallet_matches = re.findall(r'0x[a-fA-F0-9]{40,}', data_str)
        if wallet_matches:
            violations.extend([f"wallet_address:{w[:20]}..." for w in wallet_matches[:3]])

        # MongoDB connection strings
        mongo_matches = re.findall(r'mongodb(\+srv)?://[^\s"]+', data_str, re.IGNORECASE)
        if mongo_matches:
            violations.extend([f"mongo_uri" for _ in mongo_matches[:1]])

        assert len(violations) == 0, f"Potential secrets exposed: {violations}"
        print("PASS: No API keys, wallet addresses, or DB connection strings found")


class TestPreviousFeaturesStillWork:
    """Regression tests: previous features still work"""

    def test_lifecycle_mode_endpoint(self):
        """Lifecycle mode endpoint still works"""
        resp = requests.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert resp.status_code == 200
        data = resp.json()
        assert "mode" in data
        print(f"PASS: /api/positions/weather/lifecycle returns mode={data['mode']}")

    def test_simulator_endpoint(self):
        """Threshold simulator still works"""
        resp = requests.post(
            f"{BASE_URL}/api/positions/weather/lifecycle/simulate",
            json={"profit_capture_threshold": 2.0}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "comparison" in data or "per_reason" in data or "live" in data
        print("PASS: /api/positions/weather/lifecycle/simulate returns valid response")

    def test_entry_quality_endpoint(self):
        """Entry quality endpoint still works"""
        resp = requests.get(f"{BASE_URL}/api/strategies/weather/entry-quality")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data or "rejections" in data
        print("PASS: /api/strategies/weather/entry-quality returns valid response")

    def test_positions_by_strategy_endpoint(self):
        """Positions by strategy endpoint still works"""
        resp = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data
        assert "summaries" in data
        print(f"PASS: /api/positions/by-strategy returns positions and summaries")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
