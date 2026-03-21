"""
Iteration 80: Wave 2 Shadow Strategies + Gabagool Risk Bypass + SOL/XRP Price Feeds

Tests:
1. Smart Exit shadow API endpoints (report, positions, closed)
2. Altcoin (SOL/XRP) shadow API endpoints with per_asset tracking
3. Adaptive Edge shadow API endpoints with gabagool_dynamic section
4. Gabagool live report with threshold=0.96
5. Risk config verification (all Tier 1+2 values)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestHealthAndStatus:
    """Basic health and status checks"""
    
    def test_health_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["engine"] == "running"
        print("PASS: Health endpoint returns 200 with engine running")
    
    def test_status_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["mode"] == "paper"
        print("PASS: Status endpoint returns 200 with running status")


class TestRiskConfigValues:
    """Verify all Tier 1+2 risk config values"""
    
    def test_max_position_size_35(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        risk = response.json()["risk"]
        assert risk["max_position_size"] == 35.0
        print("PASS: max_position_size=35.0")
    
    def test_max_order_size_35(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        risk = response.json()["risk"]
        assert risk["max_order_size"] == 35.0
        print("PASS: max_order_size=35.0")
    
    def test_max_daily_loss_150(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        risk = response.json()["risk"]
        assert risk["max_daily_loss"] == 150.0
        print("PASS: max_daily_loss=150.0")
    
    def test_crypto_max_exposure_150(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        risk = response.json()["risk"]
        assert risk["crypto_max_exposure"] == 150.0
        print("PASS: crypto_max_exposure=150.0")
    
    def test_arb_max_exposure_40(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        risk = response.json()["risk"]
        assert risk["arb_max_exposure"] == 40.0
        print("PASS: arb_max_exposure=40.0")
    
    def test_max_arb_positions_12(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        risk = response.json()["risk"]
        assert risk["max_arb_positions"] == 12
        print("PASS: max_arb_positions=12")


class TestSmartExitShadow:
    """Smart Exit trailing profit capture shadow strategy"""
    
    def test_smart_exit_report_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/experiments/smart_exit/report")
        assert response.status_code == 200
        data = response.json()
        assert "experiment" in data
        assert data["experiment"] == "smart_exit"
        print("PASS: Smart Exit report returns 200")
    
    def test_smart_exit_report_has_trailing_section(self):
        response = requests.get(f"{BASE_URL}/api/experiments/smart_exit/report")
        assert response.status_code == 200
        data = response.json()
        assert "trailing" in data
        trailing = data["trailing"]
        assert "pnl" in trailing
        assert "win_rate" in trailing
        assert "open_positions" in trailing
        print("PASS: Smart Exit report has trailing section with pnl, win_rate, open_positions")
    
    def test_smart_exit_report_has_hold_comparison(self):
        response = requests.get(f"{BASE_URL}/api/experiments/smart_exit/report")
        assert response.status_code == 200
        data = response.json()
        assert "hold_comparison" in data
        hold = data["hold_comparison"]
        assert "pnl" in hold
        assert "win_rate" in hold
        print("PASS: Smart Exit report has hold_comparison section")
    
    def test_smart_exit_report_has_config(self):
        response = requests.get(f"{BASE_URL}/api/experiments/smart_exit/report")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        cfg = data["config"]
        assert "trailing_activation" in cfg
        assert "trailing_floor_pct" in cfg
        print("PASS: Smart Exit report has config with trailing_activation and trailing_floor_pct")
    
    def test_smart_exit_positions_returns_array(self):
        response = requests.get(f"{BASE_URL}/api/experiments/smart_exit/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Smart Exit positions returns array (length={len(data)})")
    
    def test_smart_exit_closed_returns_array(self):
        response = requests.get(f"{BASE_URL}/api/experiments/smart_exit/closed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Smart Exit closed returns array (length={len(data)})")


class TestAltcoinShadow:
    """Altcoin (SOL/XRP) shadow sniper strategy"""
    
    def test_altcoin_report_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/experiments/altcoin/report")
        assert response.status_code == 200
        data = response.json()
        assert "experiment" in data
        assert data["experiment"] == "altcoin_sniper"
        print("PASS: Altcoin report returns 200")
    
    def test_altcoin_report_has_per_asset_tracking(self):
        response = requests.get(f"{BASE_URL}/api/experiments/altcoin/report")
        assert response.status_code == 200
        data = response.json()
        assert "per_asset" in data
        per_asset = data["per_asset"]
        assert "SOL" in per_asset
        assert "XRP" in per_asset
        # Verify SOL tracking fields
        sol = per_asset["SOL"]
        assert "pnl" in sol
        assert "wins" in sol
        assert "losses" in sol
        assert "trades" in sol
        assert "signals" in sol
        # Verify XRP tracking fields
        xrp = per_asset["XRP"]
        assert "pnl" in xrp
        assert "wins" in xrp
        assert "losses" in xrp
        print("PASS: Altcoin report has per_asset tracking for SOL and XRP")
    
    def test_altcoin_report_has_performance(self):
        response = requests.get(f"{BASE_URL}/api/experiments/altcoin/report")
        assert response.status_code == 200
        data = response.json()
        assert "performance" in data
        perf = data["performance"]
        assert "pnl" in perf
        assert "win_rate" in perf
        assert "open_positions" in perf
        print("PASS: Altcoin report has performance section")
    
    def test_altcoin_positions_returns_array(self):
        response = requests.get(f"{BASE_URL}/api/experiments/altcoin/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Altcoin positions returns array (length={len(data)})")
    
    def test_altcoin_closed_returns_array(self):
        response = requests.get(f"{BASE_URL}/api/experiments/altcoin/closed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Altcoin closed returns array (length={len(data)})")


class TestAdaptiveEdgeShadow:
    """Adaptive Edge + Dynamic Gabagool shadow strategy"""
    
    def test_adaptive_report_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/experiments/adaptive/report")
        assert response.status_code == 200
        data = response.json()
        assert "experiment" in data
        assert data["experiment"] == "adaptive_edge"
        print("PASS: Adaptive Edge report returns 200")
    
    def test_adaptive_report_has_adaptive_edge_section(self):
        response = requests.get(f"{BASE_URL}/api/experiments/adaptive/report")
        assert response.status_code == 200
        data = response.json()
        assert "adaptive_edge" in data
        ae = data["adaptive_edge"]
        assert "signals_received" in ae
        assert "current_adaptive_edge" in ae
        assert "would_trade" in ae
        assert "would_skip" in ae
        print(f"PASS: Adaptive Edge has adaptive_edge section (signals_received={ae['signals_received']})")
    
    def test_adaptive_report_has_gabagool_dynamic_section(self):
        response = requests.get(f"{BASE_URL}/api/experiments/adaptive/report")
        assert response.status_code == 200
        data = response.json()
        assert "gabagool_dynamic" in data
        gd = data["gabagool_dynamic"]
        assert "pnl" in gd
        assert "scanned" in gd
        assert "by_window" in gd
        print("PASS: Adaptive Edge has gabagool_dynamic section")
    
    def test_adaptive_report_has_config_with_vol_thresholds(self):
        response = requests.get(f"{BASE_URL}/api/experiments/adaptive/report")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        cfg = data["config"]
        assert "vol_high" in cfg
        assert "vol_low" in cfg
        assert "edge_high_vol" in cfg
        assert "edge_medium_vol" in cfg
        assert "edge_low_vol" in cfg
        assert "gaba_thresholds" in cfg
        print("PASS: Adaptive Edge config has vol thresholds and gaba_thresholds")
    
    def test_adaptive_positions_returns_array(self):
        response = requests.get(f"{BASE_URL}/api/experiments/adaptive/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Adaptive positions returns array (length={len(data)})")
    
    def test_adaptive_closed_returns_array(self):
        response = requests.get(f"{BASE_URL}/api/experiments/adaptive/closed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Adaptive closed returns array (length={len(data)})")


class TestGabagoolLive:
    """Gabagool live arb executor"""
    
    def test_gabagool_report_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/gabagool/report")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert data["strategy"] == "gabagool_live"
        print("PASS: Gabagool report returns 200 with active status")
    
    def test_gabagool_threshold_0_96(self):
        response = requests.get(f"{BASE_URL}/api/gabagool/report")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert data["config"]["threshold"] == 0.96
        print("PASS: Gabagool threshold=0.96")
    
    def test_gabagool_has_metrics(self):
        response = requests.get(f"{BASE_URL}/api/gabagool/report")
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        metrics = data["metrics"]
        assert "total_scans" in metrics
        assert "pairs_found" in metrics
        assert "valid_pairs_last_scan" in metrics
        print(f"PASS: Gabagool has metrics (total_scans={metrics['total_scans']})")
    
    def test_gabagool_has_performance(self):
        response = requests.get(f"{BASE_URL}/api/gabagool/report")
        assert response.status_code == 200
        data = response.json()
        assert "performance" in data
        perf = data["performance"]
        assert "pnl_total" in perf
        assert "open_pairs" in perf
        assert "win_rate" in perf
        print("PASS: Gabagool has performance section")


class TestExperimentsRegistry:
    """Experiments registry for Quant Lab"""
    
    def test_registry_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        data = response.json()
        assert "experiments" in data
        print(f"PASS: Registry returns 200 with {len(data['experiments'])} experiments")
    
    def test_registry_has_wave2_experiments(self):
        response = requests.get(f"{BASE_URL}/api/experiments/registry")
        assert response.status_code == 200
        experiments = response.json()["experiments"]
        exp_ids = [e["id"] for e in experiments]
        # Wave 2 experiments
        assert "smart_exit" in exp_ids, "smart_exit not in registry"
        assert "altcoin" in exp_ids, "altcoin not in registry"
        assert "adaptive" in exp_ids, "adaptive not in registry"
        print("PASS: Registry has all Wave 2 experiments (smart_exit, altcoin, adaptive)")


class TestSpotPrices:
    """Verify SOL/XRP spot prices are being tracked"""
    
    def test_spot_prices_include_sol_xrp(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        spot = data["stats"]["spot_prices"]
        assert "SOL" in spot, "SOL not in spot_prices"
        assert "XRP" in spot, "XRP not in spot_prices"
        assert spot["SOL"] > 0, "SOL price should be > 0"
        assert spot["XRP"] > 0, "XRP price should be > 0"
        print(f"PASS: Spot prices include SOL=${spot['SOL']:.2f} and XRP=${spot['XRP']:.4f}")
    
    def test_sol_xrp_not_stale(self):
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        health = response.json()["stats"]["health"]
        assert health.get("spot_sol_stale") == False, "SOL price is stale"
        assert health.get("spot_xrp_stale") == False, "XRP price is stale"
        print("PASS: SOL and XRP prices are not stale")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
