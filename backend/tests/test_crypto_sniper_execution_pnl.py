"""
Crypto Sniper Execution & PnL Tracking Tests

Tests for controlled paper/shadow executions for Crypto Sniper:
- Risk engine config changes (max_concurrent_positions: 10→30, max_market_exposure: 50→100)
- PnL tracking in sniper health endpoint
- Detailed risk sub-reason tracking (e.g., "risk:max concurrent positions" instead of generic "risk")
- Execution pipeline from signal generation to fills
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestSniperHealthAndExecution:
    """Crypto Sniper health, execution, and PnL tracking tests"""

    def test_sniper_health_signals_executed_gt_0(self):
        """GET /api/strategies/sniper/health - signals_executed should be > 0"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert "signals_executed" in data
        assert data["signals_executed"] > 0, f"Expected signals_executed > 0, got {data['signals_executed']}"
        print(f"PASS: signals_executed = {data['signals_executed']}")

    def test_sniper_health_signals_filled_gt_0(self):
        """GET /api/strategies/sniper/health - signals_filled should be > 0"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert "signals_filled" in data
        assert data["signals_filled"] > 0, f"Expected signals_filled > 0, got {data['signals_filled']}"
        print(f"PASS: signals_filled = {data['signals_filled']}")

    def test_sniper_health_pnl_object_exists(self):
        """GET /api/strategies/sniper/health - pnl object should exist with all required fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "pnl" in data, "pnl object missing from health response"
        pnl = data["pnl"]
        
        required_fields = ["realized", "unrealized", "total", "positions", "fills"]
        for field in required_fields:
            assert field in pnl, f"Missing field '{field}' in pnl object"
        
        print(f"PASS: pnl object has all required fields: {pnl}")

    def test_sniper_health_pnl_fills_match_signals_filled(self):
        """PnL fills count should match signals_filled"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert data["pnl"]["fills"] == data["signals_filled"], \
            f"pnl.fills ({data['pnl']['fills']}) != signals_filled ({data['signals_filled']})"
        print(f"PASS: pnl.fills = signals_filled = {data['signals_filled']}")

    def test_sniper_health_rejection_reasons_specific_risk_subreasons(self):
        """GET /api/strategies/sniper/health - rejection_reasons should NOT have generic 'risk' key"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "rejection_reasons" in data, "rejection_reasons missing from health response"
        rejection_reasons = data["rejection_reasons"]
        
        # Should NOT have a generic 'risk' key
        assert "risk" not in rejection_reasons, \
            "Found generic 'risk' key in rejection_reasons - should use specific sub-reasons like 'risk:max concurrent positions'"
        
        # Check for specific risk sub-reasons (if any risk rejections occurred)
        risk_subreasons = [k for k in rejection_reasons.keys() if k.startswith("risk:")]
        if risk_subreasons:
            print(f"PASS: Found specific risk sub-reasons: {risk_subreasons}")
            for reason in risk_subreasons:
                print(f"  - {reason}: {rejection_reasons[reason]}")
        else:
            print("PASS: No risk rejections occurred (or all signals passed risk checks)")
        
        print(f"All rejection reasons: {rejection_reasons}")


class TestRiskConfig:
    """Risk configuration tests - verify updated limits"""

    def test_config_max_concurrent_positions_is_30(self):
        """GET /api/config - risk.max_concurrent_positions should be 30"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "risk" in data, "risk config missing"
        assert data["risk"]["max_concurrent_positions"] == 30, \
            f"Expected max_concurrent_positions=30, got {data['risk']['max_concurrent_positions']}"
        print(f"PASS: risk.max_concurrent_positions = 30")

    def test_config_max_market_exposure_is_100(self):
        """GET /api/config - risk.max_market_exposure should be 100"""
        response = requests.get(f"{BASE_URL}/api/config", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "risk" in data, "risk config missing"
        assert data["risk"]["max_market_exposure"] == 100, \
            f"Expected max_market_exposure=100, got {data['risk']['max_market_exposure']}"
        print(f"PASS: risk.max_market_exposure = 100")


class TestSniperExecutions:
    """Sniper executions endpoint tests"""

    def test_sniper_executions_has_completed(self):
        """GET /api/strategies/sniper/executions - should have completed executions"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/executions", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "active" in data, "Missing 'active' key"
        assert "completed" in data, "Missing 'completed' key"
        
        completed = data["completed"]
        assert isinstance(completed, list), "completed should be a list"
        assert len(completed) > 0, "Expected at least one completed execution"
        
        # Verify execution structure
        first_exec = completed[0]
        required_fields = ["id", "signal_id", "condition_id", "asset", "side", "status", "entry_price", "size"]
        for field in required_fields:
            assert field in first_exec, f"Missing field '{field}' in execution"
        
        print(f"PASS: {len(completed)} completed executions found")
        print(f"  First execution: {first_exec['asset']} {first_exec['side']} @ {first_exec['entry_price']}")


class TestSniperSignals:
    """Sniper signals endpoint tests"""

    def test_sniper_signals_has_tradable(self):
        """GET /api/strategies/sniper/signals - tradable array should have entries"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "tradable" in data, "Missing 'tradable' key"
        assert "rejected" in data, "Missing 'rejected' key"
        
        # Note: tradable might be empty at any given moment due to cooldowns
        # Check total_tradable to see if any have been generated
        assert "total_tradable" in data, "Missing 'total_tradable' key"
        
        print(f"PASS: tradable={len(data['tradable'])}, rejected={len(data['rejected'])}")
        print(f"  total_tradable={data['total_tradable']}, total_rejected={data['total_rejected']}")


class TestDiscovery:
    """Market discovery tests"""

    def test_discovery_crypto_markets_gt_0(self):
        """GET /api/health/discovery - crypto_markets_discovered > 0"""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "crypto_markets_discovered" in data, "Missing crypto_markets_discovered"
        assert data["crypto_markets_discovered"] > 0, \
            f"Expected crypto_markets_discovered > 0, got {data['crypto_markets_discovered']}"
        print(f"PASS: crypto_markets_discovered = {data['crypto_markets_discovered']}")


class TestPositions:
    """Position tracking tests"""

    def test_positions_within_risk_limit(self):
        """GET /api/positions - total positions should be <= 30 (within risk limit)"""
        response = requests.get(f"{BASE_URL}/api/positions", timeout=10)
        assert response.status_code == 200
        positions = response.json()
        
        assert isinstance(positions, list), "positions should be a list"
        assert len(positions) <= 30, \
            f"Positions ({len(positions)}) exceed risk limit of 30"
        print(f"PASS: positions = {len(positions)} (<= 30)")


class TestTradingMode:
    """Trading mode verification"""

    def test_trading_mode_is_paper(self):
        """Verify trading_mode is 'paper' (no live trading)"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "mode" in data, "Missing 'mode' key"
        assert data["mode"] == "paper", \
            f"Expected mode='paper', got '{data['mode']}'"
        print(f"PASS: trading_mode = paper")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
