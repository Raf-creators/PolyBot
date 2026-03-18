"""
Iteration 61: Global System Snapshot v2 Tests
Tests the refactored _build_state_snapshot() that provides a balanced, full-system
snapshot across ALL strategies (not just weather-biased).

New v2 structure:
{
  freshness: { snapshot_at, version, server_start_time, ... },
  portfolio: {
    capital_allocation: { strategy → { capital_deployed, pct_of_total, position_count, unrealized_pnl } },
    pnl_by_strategy: { strategy → { realized_pnl, trade_count, win_rate } },
    concentration_risk: { largest_position, top_3_pct, hhi }
  },
  strategies: {
    weather: { positions, scan_health, lifecycle, entry_quality, config },
    weather_asymmetric: { positions, scan_health, config },
    crypto: { positions, scan_health, execution_stats, volatility, config },
    arb: { positions, scan_health, execution_stats, diagnostics, config }
  }
}

All positions include: invested, current_value, profit_multiple, unrealized_pnl
Crypto positions have: strategy_meta { asset, time_window }
Arb positions have: strategy_meta { market_type }
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
DEBUG_KEY = "test-snapshot-key-preview"


class TestDebugSnapshotV2Structure:
    """Tests for the new v2 snapshot structure at /api/debug/ui-snapshot"""

    def test_ui_snapshot_returns_200(self):
        """GET /api/debug/ui-snapshot returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: /api/debug/ui-snapshot returns 200")

    def test_snapshot_has_toplevel_keys(self):
        """Snapshot has top-level keys: freshness, portfolio, strategies"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        
        assert "freshness" in data, "Missing 'freshness' top-level key"
        assert "portfolio" in data, "Missing 'portfolio' top-level key"
        assert "strategies" in data, "Missing 'strategies' top-level key"
        
        # Verify old v1 keys are NOT present
        assert "positions" not in data, "Old v1 'positions' key should be removed"
        assert "position_counts" not in data, "Old v1 'position_counts' key should be removed"
        assert "lifecycle" not in data, "Old v1 top-level 'lifecycle' key should be removed"
        assert "entry_quality" not in data, "Old v1 top-level 'entry_quality' key should be removed"
        assert "pnl_summary" not in data, "Old v1 'pnl_summary' key should be removed"
        assert "strategy_health" not in data, "Old v1 'strategy_health' key should be removed"
        assert "weather_config" not in data, "Old v1 'weather_config' key should be removed"
        
        print("PASS: Snapshot has correct v2 top-level keys (freshness, portfolio, strategies)")


class TestFreshnessSection:
    """Tests for the freshness metadata section"""

    def test_freshness_has_required_fields(self):
        """freshness section has all required fields"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        freshness = data.get("freshness", {})
        
        required_fields = [
            "snapshot_at", "snapshot_version", "server_start_time",
            "uptime_seconds", "engine_status", "trading_mode",
            "markets_tracked", "git_commit"
        ]
        for field in required_fields:
            assert field in freshness, f"Missing freshness.{field}"
        
        # Verify version is 2.0
        assert freshness["snapshot_version"] == "2.0", f"Expected version 2.0, got {freshness['snapshot_version']}"
        
        print(f"PASS: freshness has all required fields, version={freshness['snapshot_version']}")


class TestPortfolioSection:
    """Tests for the portfolio aggregation section"""

    def test_portfolio_has_capital_allocation(self):
        """portfolio.capital_allocation contains strategy bucket data"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        portfolio = data.get("portfolio", {})
        
        assert "capital_allocation" in portfolio, "Missing portfolio.capital_allocation"
        allocation = portfolio["capital_allocation"]
        
        # Each strategy bucket should have these fields
        for bucket_name, bucket_data in allocation.items():
            assert "capital_deployed" in bucket_data, f"Missing capital_deployed in {bucket_name}"
            assert "pct_of_total" in bucket_data, f"Missing pct_of_total in {bucket_name}"
            assert "position_count" in bucket_data, f"Missing position_count in {bucket_name}"
            assert "unrealized_pnl" in bucket_data, f"Missing unrealized_pnl in {bucket_name}"
        
        print(f"PASS: portfolio.capital_allocation has entries for {len(allocation)} strategy buckets")

    def test_portfolio_has_pnl_by_strategy(self):
        """portfolio.pnl_by_strategy contains PnL data per strategy"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        portfolio = data.get("portfolio", {})
        
        assert "pnl_by_strategy" in portfolio, "Missing portfolio.pnl_by_strategy"
        pnl_by_strat = portfolio["pnl_by_strategy"]
        
        # Each strategy should have these fields
        for strat_id, strat_data in pnl_by_strat.items():
            assert "realized_pnl" in strat_data, f"Missing realized_pnl in {strat_id}"
            assert "trade_count" in strat_data, f"Missing trade_count in {strat_id}"
            assert "win_rate" in strat_data, f"Missing win_rate in {strat_id}"
        
        print(f"PASS: portfolio.pnl_by_strategy has entries for {len(pnl_by_strat)} strategies")

    def test_portfolio_has_concentration_risk(self):
        """portfolio.concentration_risk contains HHI and position concentration"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        portfolio = data.get("portfolio", {})
        
        assert "concentration_risk" in portfolio, "Missing portfolio.concentration_risk"
        conc = portfolio["concentration_risk"]
        
        # Should have these keys
        assert "top_3_pct" in conc, "Missing top_3_pct"
        assert "hhi" in conc, "Missing hhi (Herfindahl-Hirschman Index)"
        
        # If positions exist, largest_position should be present
        if portfolio.get("open_positions", 0) > 0:
            assert "largest_position" in conc, "Missing largest_position when positions exist"
            largest = conc["largest_position"]
            assert "token_id" in largest, "Missing largest_position.token_id"
            assert "invested" in largest, "Missing largest_position.invested"
            assert "pct_of_total" in largest, "Missing largest_position.pct_of_total"
        
        print(f"PASS: portfolio.concentration_risk has HHI={conc.get('hhi')}, top_3_pct={conc.get('top_3_pct')}")


class TestStrategiesSection:
    """Tests for the per-strategy sections"""

    def test_strategies_has_all_four_sections(self):
        """strategies has weather, weather_asymmetric, crypto, arb sections"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        strategies = data.get("strategies", {})
        
        required_sections = ["weather", "weather_asymmetric", "crypto", "arb"]
        for section in required_sections:
            assert section in strategies, f"Missing strategies.{section}"
        
        print(f"PASS: strategies has all 4 required sections: {list(strategies.keys())}")

    def test_weather_section_structure(self):
        """strategies.weather has positions, scan_health, lifecycle, entry_quality, config"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        weather = data.get("strategies", {}).get("weather", {})
        
        required_keys = ["positions", "scan_health", "lifecycle", "entry_quality", "config"]
        for key in required_keys:
            assert key in weather, f"Missing weather.{key}"
        
        # Verify scan_health fields
        scan = weather["scan_health"]
        assert "total_scans" in scan, "Missing scan_health.total_scans"
        assert "signals_generated" in scan, "Missing scan_health.signals_generated"
        
        # Verify lifecycle fields
        lc = weather["lifecycle"]
        assert "mode" in lc, "Missing lifecycle.mode"
        assert "thresholds" in lc, "Missing lifecycle.thresholds"
        assert "exit_candidates" in lc, "Missing lifecycle.exit_candidates"
        
        # Verify entry_quality fields
        eq = weather["entry_quality"]
        assert "config" in eq, "Missing entry_quality.config"
        assert "rejections" in eq, "Missing entry_quality.rejections"
        
        print(f"PASS: weather section has all required sub-sections (positions={weather.get('position_count', 0)})")

    def test_weather_asymmetric_section_structure(self):
        """strategies.weather_asymmetric has positions, scan_health, config"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        wasym = data.get("strategies", {}).get("weather_asymmetric", {})
        
        required_keys = ["positions", "scan_health", "config"]
        for key in required_keys:
            assert key in wasym, f"Missing weather_asymmetric.{key}"
        
        print(f"PASS: weather_asymmetric section has required structure (positions={wasym.get('position_count', 0)})")

    def test_crypto_section_structure(self):
        """strategies.crypto has positions, scan_health, execution_stats, volatility, config"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        crypto = data.get("strategies", {}).get("crypto", {})
        
        required_keys = ["positions", "scan_health", "execution_stats", "volatility", "config"]
        for key in required_keys:
            assert key in crypto, f"Missing crypto.{key}"
        
        # Verify scan_health fields
        scan = crypto["scan_health"]
        assert "total_scans" in scan, "Missing crypto.scan_health.total_scans"
        assert "signals_generated" in scan, "Missing crypto.scan_health.signals_generated"
        
        # Verify execution_stats fields
        exec_stats = crypto["execution_stats"]
        assert "active_executions" in exec_stats, "Missing crypto.execution_stats.active_executions"
        assert "pnl_realized" in exec_stats, "Missing crypto.execution_stats.pnl_realized"
        
        # Verify volatility fields
        vol = crypto["volatility"]
        assert "btc_vol_samples" in vol, "Missing crypto.volatility.btc_vol_samples"
        assert "eth_vol_samples" in vol, "Missing crypto.volatility.eth_vol_samples"
        
        print(f"PASS: crypto section has required structure (positions={crypto.get('position_count', 0)})")

    def test_arb_section_structure(self):
        """strategies.arb has positions, scan_health, execution_stats, diagnostics, config"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        arb = data.get("strategies", {}).get("arb", {})
        
        required_keys = ["positions", "scan_health", "execution_stats", "diagnostics", "config"]
        for key in required_keys:
            assert key in arb, f"Missing arb.{key}"
        
        # Verify scan_health fields
        scan = arb["scan_health"]
        assert "total_scans" in scan, "Missing arb.scan_health.total_scans"
        assert "signals_generated" in scan, "Missing arb.scan_health.signals_generated"
        
        # Verify execution_stats fields
        exec_stats = arb["execution_stats"]
        assert "active_executions" in exec_stats, "Missing arb.execution_stats.active_executions"
        assert "executed_count" in exec_stats, "Missing arb.execution_stats.executed_count"
        
        print(f"PASS: arb section has required structure (positions={arb.get('position_count', 0)})")


class TestPositionFields:
    """Tests for position-level fields across all strategies"""

    def test_all_positions_have_required_fields(self):
        """All positions across all strategies have invested, current_value, profit_multiple"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        strategies = data.get("strategies", {})
        
        required_fields = ["invested", "current_value", "profit_multiple", "unrealized_pnl"]
        
        total_positions = 0
        for strat_name, strat_data in strategies.items():
            positions = strat_data.get("positions", [])
            for pos in positions:
                total_positions += 1
                for field in required_fields:
                    assert field in pos, f"Position {pos.get('token_id', '?')} in {strat_name} missing {field}"
        
        print(f"PASS: All {total_positions} positions have required fields (invested, current_value, profit_multiple)")

    def test_crypto_positions_have_strategy_meta(self):
        """Crypto positions have strategy_meta with asset and time_window"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        crypto = data.get("strategies", {}).get("crypto", {})
        positions = crypto.get("positions", [])
        
        if not positions:
            pytest.skip("No crypto positions to test")
        
        for pos in positions:
            assert "strategy_meta" in pos, f"Crypto position {pos.get('token_id', '?')} missing strategy_meta"
            meta = pos["strategy_meta"]
            assert "asset" in meta, f"Crypto position missing strategy_meta.asset"
            assert "time_window" in meta, f"Crypto position missing strategy_meta.time_window"
            assert meta["asset"] in ["BTC", "ETH"], f"Invalid asset: {meta['asset']}"
        
        print(f"PASS: All {len(positions)} crypto positions have strategy_meta (asset, time_window)")

    def test_arb_positions_have_strategy_meta(self):
        """Arb positions have strategy_meta"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        arb = data.get("strategies", {}).get("arb", {})
        positions = arb.get("positions", [])
        
        if not positions:
            pytest.skip("No arb positions to test")
        
        for pos in positions:
            assert "strategy_meta" in pos, f"Arb position {pos.get('token_id', '?')} missing strategy_meta"
        
        print(f"PASS: All {len(positions)} arb positions have strategy_meta")

    def test_weather_positions_have_lifecycle(self):
        """Weather positions still have lifecycle enrichment"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        weather = data.get("strategies", {}).get("weather", {})
        positions = weather.get("positions", [])
        
        if not positions:
            pytest.skip("No weather positions to test")
        
        # At least some positions should have lifecycle data
        with_lifecycle = [p for p in positions if p.get("lifecycle")]
        
        # Check lifecycle fields on positions that have it
        for pos in with_lifecycle:
            lc = pos["lifecycle"]
            assert "is_exit_candidate" in lc, "Missing lifecycle.is_exit_candidate"
            assert "exit_reason" in lc, "Missing lifecycle.exit_reason"
            assert "profit_multiple" in lc, "Missing lifecycle.profit_multiple"
            assert "book_rank" in lc, "Missing lifecycle.book_rank"
        
        print(f"PASS: {len(with_lifecycle)}/{len(positions)} weather positions have lifecycle enrichment")


class TestStateSnapshotAuth:
    """Tests for the authenticated /api/debug/state-snapshot endpoint"""

    def test_state_snapshot_requires_key(self):
        """GET /api/debug/state-snapshot returns 403 without key"""
        response = requests.get(f"{BASE_URL}/api/debug/state-snapshot", timeout=10)
        assert response.status_code == 403, f"Expected 403 without key, got {response.status_code}"
        print("PASS: /api/debug/state-snapshot returns 403 without key")

    def test_state_snapshot_returns_200_with_header(self):
        """GET /api/debug/state-snapshot returns 200 with X-Debug-Snapshot-Key header"""
        headers = {"X-Debug-Snapshot-Key": DEBUG_KEY}
        response = requests.get(f"{BASE_URL}/api/debug/state-snapshot", headers=headers, timeout=30)
        assert response.status_code == 200, f"Expected 200 with key header, got {response.status_code}"
        
        # Verify it returns the same v2 structure
        data = response.json()
        assert "freshness" in data, "state-snapshot missing freshness"
        assert "portfolio" in data, "state-snapshot missing portfolio"
        assert "strategies" in data, "state-snapshot missing strategies"
        
        print("PASS: /api/debug/state-snapshot returns 200 with correct header")

    def test_state_snapshot_returns_200_with_query_param(self):
        """GET /api/debug/state-snapshot?key=... returns 200"""
        response = requests.get(f"{BASE_URL}/api/debug/state-snapshot?key={DEBUG_KEY}", timeout=30)
        assert response.status_code == 200, f"Expected 200 with query param, got {response.status_code}"
        print("PASS: /api/debug/state-snapshot returns 200 with query param fallback")


class TestPositionCounts:
    """Tests to verify position counts match across different sections"""

    def test_position_counts_match(self):
        """Total positions in portfolio matches sum of strategy positions"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        
        portfolio = data.get("portfolio", {})
        strategies = data.get("strategies", {})
        
        portfolio_count = portfolio.get("open_positions", 0)
        
        strategy_count = 0
        for strat_name, strat_data in strategies.items():
            strategy_count += strat_data.get("position_count", 0)
        
        assert portfolio_count == strategy_count, \
            f"Position count mismatch: portfolio={portfolio_count}, strategies total={strategy_count}"
        
        print(f"PASS: Position counts match: portfolio={portfolio_count}, strategies total={strategy_count}")

    def test_capital_allocation_position_counts(self):
        """Capital allocation position counts match strategy section counts"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        
        allocation = data.get("portfolio", {}).get("capital_allocation", {})
        strategies = data.get("strategies", {})
        
        for strat_name, strat_data in strategies.items():
            expected_count = strat_data.get("position_count", 0)
            alloc_count = allocation.get(strat_name, {}).get("position_count", 0)
            
            # Only check if there are positions in either
            if expected_count > 0 or alloc_count > 0:
                assert expected_count == alloc_count, \
                    f"{strat_name} position count mismatch: strategy={expected_count}, allocation={alloc_count}"
        
        print("PASS: Capital allocation position counts match strategy section counts")


class TestSnapshotBalanceVerification:
    """Tests to verify the snapshot is balanced across strategies"""

    def test_snapshot_not_weather_biased(self):
        """Verify snapshot is not weather-biased (has equal depth for all strategies)"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=30)
        data = response.json()
        strategies = data.get("strategies", {})
        
        # Each strategy should have at minimum: positions, scan_health, config
        min_keys = {"positions", "scan_health", "config"}
        
        for strat_name, strat_data in strategies.items():
            strat_keys = set(strat_data.keys())
            missing = min_keys - strat_keys
            assert not missing, f"{strat_name} missing base keys: {missing}"
        
        # Weather and crypto/arb should have similar depth
        weather_depth = len(strategies.get("weather", {}).keys())
        crypto_depth = len(strategies.get("crypto", {}).keys())
        arb_depth = len(strategies.get("arb", {}).keys())
        
        # All should have at least 4 keys
        assert weather_depth >= 4, f"Weather depth too shallow: {weather_depth}"
        assert crypto_depth >= 4, f"Crypto depth too shallow: {crypto_depth}"
        assert arb_depth >= 4, f"Arb depth too shallow: {arb_depth}"
        
        print(f"PASS: Snapshot balanced - weather={weather_depth}keys, crypto={crypto_depth}keys, arb={arb_depth}keys")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
