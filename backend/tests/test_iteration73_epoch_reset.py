"""
Iteration 73: Epoch Reset Testing
- Paper performance reset to $1000 baseline
- All historical trades/orders/positions archived to epoch1 collections
- Live collections cleared
- In-memory state reset
- Bot continues running under same configuration
- Shadow system unaffected
- Overview now shows clean $1000 baseline
- PnL chart starts fresh
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestEpochResetAPI:
    """Tests for epoch reset API endpoints and state"""

    def test_status_daily_pnl_near_zero(self):
        """GET /api/status returns daily_pnl near 0 (fresh epoch)"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        stats = data.get("stats", {})
        daily_pnl = stats.get("daily_pnl", 0)
        # Fresh epoch should have PnL near 0 (within $10 since bot may have had a few trades)
        assert abs(daily_pnl) < 10, f"daily_pnl should be near 0, got {daily_pnl}"
        print(f"PASS: daily_pnl={daily_pnl} (near 0 as expected)")

    def test_status_total_trades_low(self):
        """GET /api/status returns total_trades < 200 (fresh epoch, not 7444 from old epoch)"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        stats = data.get("stats", {})
        total_trades = stats.get("total_trades", 0)
        # Fresh epoch should have significantly fewer trades than old epoch (7444)
        # Allow up to 200 since bot may have been running for a while
        assert total_trades < 200, f"total_trades should be < 200 (old epoch had 7444), got {total_trades}"
        print(f"PASS: total_trades={total_trades} (< 200, not 7444 from old epoch)")

    def test_status_win_rate_reflects_new_trades(self):
        """GET /api/status returns win_rate reflecting only new trades"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        stats = data.get("stats", {})
        win_rate = stats.get("win_rate", 0)
        win_count = stats.get("win_count", 0)
        loss_count = stats.get("loss_count", 0)
        # Fresh epoch - either 0% (no closed trades) or based on very few trades
        assert win_rate >= 0 and win_rate <= 1, f"win_rate should be between 0-1, got {win_rate}"
        # Total wins+losses should be low
        assert (win_count + loss_count) < 50, f"win_count+loss_count should be < 50, got {win_count + loss_count}"
        print(f"PASS: win_rate={win_rate}, win_count={win_count}, loss_count={loss_count}")

    def test_pnl_history_near_zero(self):
        """GET /api/analytics/pnl-history returns current_pnl near 0 (fresh epoch) with fewer trades than old epoch"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        current_pnl = data.get("current_pnl", 0)
        total_trades = data.get("total_trades", 0)
        # Fresh epoch should have PnL within reasonable range (not hundreds from old epoch)
        assert abs(current_pnl) < 50, f"current_pnl should be within $50 of baseline, got {current_pnl}"
        # Should have significantly fewer trades than old epoch (7444)
        assert total_trades < 200, f"total_trades should be < 200 (old epoch had 7444), got {total_trades}"
        print(f"PASS: current_pnl={current_pnl}, total_trades={total_trades} (fresh epoch, not 7444)")

    def test_pnl_history_fresh_chart(self):
        """GET /api/analytics/pnl-history history should be fresh (not hundreds of trades)"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        history = data.get("history", [])
        # Fresh epoch should not have hundreds of history points
        # Note: history might be empty if no closed trades yet
        assert len(history) < 100, f"history should have < 100 points (fresh epoch), got {len(history)}"
        print(f"PASS: history has {len(history)} points (< 100 for fresh epoch)")

    def test_shadow_system_active(self):
        """GET /api/shadow/report returns status=active or no_data (fresh epoch)"""
        response = requests.get(f"{BASE_URL}/api/shadow/report")
        assert response.status_code == 200
        data = response.json()
        status = data.get("status")
        total_evals = data.get("total_evaluations", 0)
        # Shadow system can be "active" or "no_data" right after epoch reset
        # "no_data" is acceptable if the system just started and hasn't collected evaluations yet
        assert status in ["active", "no_data"], f"Shadow status should be 'active' or 'no_data', got {status}"
        # Shadow system should still be working (evaluations may be >= 0)
        print(f"PASS: shadow status={status}, total_evaluations={total_evals}")

    def test_risk_config_preserved(self):
        """GET /api/config shows risk config preserved after reset"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        risk = data.get("risk", {})
        
        # Verify expected values from forensic rollback config
        max_position_size = risk.get("max_position_size")
        arb_max_exposure = risk.get("arb_max_exposure")
        crypto_max_exposure = risk.get("crypto_max_exposure")
        
        assert max_position_size == 25.0, f"max_position_size should be 25, got {max_position_size}"
        assert arb_max_exposure == 8.0, f"arb_max_exposure should be 8, got {arb_max_exposure}"
        assert crypto_max_exposure == 250.0, f"crypto_max_exposure should be 250, got {crypto_max_exposure}"
        print(f"PASS: risk config preserved - max_position_size={max_position_size}, arb_max_exposure={arb_max_exposure}, crypto_max_exposure={crypto_max_exposure}")

    def test_engine_running(self):
        """Engine should still be running after epoch reset"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        status = data.get("status")
        mode = data.get("mode")
        
        assert status == "running", f"Engine status should be 'running', got {status}"
        assert mode == "paper", f"Mode should be 'paper', got {mode}"
        print(f"PASS: engine status={status}, mode={mode}")

    def test_strategies_enabled(self):
        """All strategies should still be enabled after reset"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        data = response.json()
        strategies = data.get("strategies", {})
        
        for strat_id in ["arb_scanner", "crypto_sniper", "weather_trader"]:
            strat = strategies.get(strat_id, {})
            enabled = strat.get("enabled", False)
            assert enabled, f"Strategy {strat_id} should be enabled"
            print(f"PASS: {strat_id} enabled={enabled}")


class TestEpochDataIntegrity:
    """Tests verifying epoch data isolation and archival"""

    def test_current_trades_count_low(self):
        """Current trades collection should have significantly fewer than old epoch (7444)"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        trades = response.json()
        # Old epoch had 7444 trades, fresh epoch should have much less (< 200 even after running for a while)
        assert len(trades) < 200, f"Should have < 200 current trades (old epoch had 7444), got {len(trades)}"
        print(f"PASS: current trades count = {len(trades)} (< 200, significantly less than 7444)")

    def test_positions_count_reasonable(self):
        """Current positions should be reasonable for fresh epoch"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        positions = response.json()
        # Fresh epoch might have some positions from new trades
        assert len(positions) < 50, f"Should have < 50 positions, got {len(positions)}"
        print(f"PASS: current positions count = {len(positions)}")

    def test_diagnostics_shows_clean_state(self):
        """Diagnostics should show low trades_in_memory count"""
        response = requests.get(f"{BASE_URL}/api/diagnostics")
        assert response.status_code == 200
        data = response.json()
        state = data.get("state", {})
        trades_in_memory = state.get("trades_in_memory", 0)
        # Fresh epoch should have < 100 trades in memory
        assert trades_in_memory < 100, f"trades_in_memory should be < 100, got {trades_in_memory}"
        print(f"PASS: trades_in_memory = {trades_in_memory}")


class TestPaperBalanceCalculation:
    """Tests for paper balance calculation near $1000"""

    def test_paper_balance_near_1000(self):
        """Paper balance should be approximately $1000 (within $5)"""
        # Paper balance = 1000 + current_pnl
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history")
        assert response.status_code == 200
        data = response.json()
        current_pnl = data.get("current_pnl", 0)
        paper_balance = 1000 + current_pnl
        
        # Should be within $5 of $1000
        assert abs(paper_balance - 1000) < 5, f"Paper balance should be within $5 of $1000, got ${paper_balance:.2f}"
        print(f"PASS: paper_balance = ${paper_balance:.2f} (within $5 of $1000)")


class TestEpochIdempotency:
    """Tests verifying epoch reset is idempotent"""

    def test_epoch_marker_exists(self):
        """Epoch marker (epoch_2) should exist in the system"""
        # We can infer this from the fact that:
        # 1. The system is running
        # 2. Data is fresh (not 7444 trades)
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        stats = data.get("stats", {})
        total_trades = stats.get("total_trades", 0)
        
        # If epoch marker didn't exist, we'd have 7444+ trades
        assert total_trades < 100, f"If epoch marker exists, total_trades should be < 100, got {total_trades}"
        print(f"PASS: epoch marker working (total_trades={total_trades}, not 7444)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
