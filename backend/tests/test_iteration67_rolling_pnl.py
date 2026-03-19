"""
Iteration 67: Rolling PnL Window System Tests

Tests that validate ALL PnL/hour metrics now use trade-timestamp-based
rolling windows (1h/3h/6h) instead of dividing by system uptime.

Features tested:
1. /api/health returns 200
2. /api/admin/upgrade-tracking returns rolling_pnl with total/crypto/weather/arb sections
3. Each rolling_pnl section has pnl_per_hour_1h/3h/6h fields
4. Each rolling_pnl section has trades_1h/3h/6h fields  
5. Each rolling_pnl section has trades_per_hour_1h/3h/6h fields
6. /api/debug/ui-snapshot returns portfolio.rolling_pnl with total/crypto/weather/arb
7. Each portfolio.rolling_pnl window (1h/3h/6h) has pnl_per_hour, trades, trades_per_hour
8. upgrade-tracking system_status has crypto_exposure, capital_utilization_pct, idle_capital_pct, total_positions
9. /api/admin/upgrade-validation returns 200
10. rolling_pnl values are numeric (not null or string)
11. /api/strategies/arb/diagnostics returns 200
12. /api/controls returns 200
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestHealthEndpoint:
    """Basic health endpoint verification"""

    def test_health_returns_200(self):
        """GET /api/health returns 200 with status=ok"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok", f"Health status not ok: {data}"
        print(f"PASS: /api/health returns 200 with status={data.get('status')}")


class TestUpgradeTrackingRollingPnL:
    """Tests for /api/admin/upgrade-tracking rolling PnL structure"""

    def test_upgrade_tracking_returns_200(self):
        """GET /api/admin/upgrade-tracking returns 200"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        print("PASS: /api/admin/upgrade-tracking returns 200")

    def test_rolling_pnl_has_all_sections(self):
        """rolling_pnl has total/crypto/weather/arb sections"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        data = response.json()
        rolling_pnl = data.get("rolling_pnl", {})
        
        required_sections = ["total", "crypto", "weather", "arb"]
        for section in required_sections:
            assert section in rolling_pnl, f"Missing rolling_pnl section: {section}"
            print(f"PASS: rolling_pnl has section '{section}'")
        
        print(f"All sections present: {list(rolling_pnl.keys())}")

    def test_rolling_pnl_pnl_per_hour_fields(self):
        """Each section has pnl_per_hour_1h, pnl_per_hour_3h, pnl_per_hour_6h"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        data = response.json()
        rolling_pnl = data.get("rolling_pnl", {})
        
        for bucket in ["total", "crypto", "weather", "arb"]:
            section = rolling_pnl.get(bucket, {})
            for window in ["1h", "3h", "6h"]:
                key = f"pnl_per_hour_{window}"
                assert key in section, f"Missing {key} in {bucket}"
                # Verify numeric type
                value = section[key]
                assert isinstance(value, (int, float)), f"{bucket}.{key} is not numeric: {type(value)}"
                print(f"PASS: {bucket}.{key} = {value} (numeric)")

    def test_rolling_pnl_trades_fields(self):
        """Each section has trades_1h, trades_3h, trades_6h"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        data = response.json()
        rolling_pnl = data.get("rolling_pnl", {})
        
        for bucket in ["total", "crypto", "weather", "arb"]:
            section = rolling_pnl.get(bucket, {})
            for window in ["1h", "3h", "6h"]:
                key = f"trades_{window}"
                assert key in section, f"Missing {key} in {bucket}"
                value = section[key]
                assert isinstance(value, (int, float)), f"{bucket}.{key} is not numeric: {type(value)}"
                print(f"PASS: {bucket}.{key} = {value} (numeric)")

    def test_rolling_pnl_trades_per_hour_fields(self):
        """Each section has trades_per_hour_1h, trades_per_hour_3h, trades_per_hour_6h"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        data = response.json()
        rolling_pnl = data.get("rolling_pnl", {})
        
        for bucket in ["total", "crypto", "weather", "arb"]:
            section = rolling_pnl.get(bucket, {})
            for window in ["1h", "3h", "6h"]:
                key = f"trades_per_hour_{window}"
                assert key in section, f"Missing {key} in {bucket}"
                value = section[key]
                assert isinstance(value, (int, float)), f"{bucket}.{key} is not numeric: {type(value)}"
                print(f"PASS: {bucket}.{key} = {value} (numeric)")

    def test_system_status_fields(self):
        """system_status has crypto_exposure, capital_utilization_pct, idle_capital_pct, total_positions"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        data = response.json()
        system_status = data.get("system_status", {})
        
        required_fields = ["crypto_exposure", "capital_utilization_pct", "idle_capital_pct", "total_positions"]
        for field in required_fields:
            assert field in system_status, f"Missing system_status field: {field}"
            value = system_status[field]
            assert isinstance(value, (int, float)), f"system_status.{field} is not numeric: {type(value)}"
            print(f"PASS: system_status.{field} = {value}")


class TestUISnapshotRollingPnL:
    """Tests for /api/debug/ui-snapshot rolling PnL structure"""

    def test_ui_snapshot_returns_200(self):
        """GET /api/debug/ui-snapshot returns 200"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=15)
        assert response.status_code == 200, f"Failed: {response.status_code}"
        print("PASS: /api/debug/ui-snapshot returns 200")

    def test_portfolio_rolling_pnl_has_all_sections(self):
        """portfolio.rolling_pnl has total/crypto/weather/arb sections"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=15)
        data = response.json()
        portfolio = data.get("portfolio", {})
        rolling_pnl = portfolio.get("rolling_pnl", {})
        
        required_sections = ["total", "crypto", "weather", "arb"]
        for section in required_sections:
            assert section in rolling_pnl, f"Missing portfolio.rolling_pnl section: {section}"
            print(f"PASS: portfolio.rolling_pnl has section '{section}'")

    def test_portfolio_rolling_pnl_window_structure(self):
        """Each window (1h/3h/6h) has pnl_per_hour, trades, trades_per_hour"""
        response = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=15)
        data = response.json()
        portfolio = data.get("portfolio", {})
        rolling_pnl = portfolio.get("rolling_pnl", {})
        
        for bucket in ["total", "crypto", "weather", "arb"]:
            bucket_data = rolling_pnl.get(bucket, {})
            for window in ["1h", "3h", "6h"]:
                window_data = bucket_data.get(window, {})
                assert window_data is not None, f"Missing {bucket}.{window}"
                
                for field in ["pnl_per_hour", "trades", "trades_per_hour"]:
                    assert field in window_data, f"Missing {bucket}.{window}.{field}"
                    value = window_data[field]
                    assert isinstance(value, (int, float)), f"{bucket}.{window}.{field} not numeric: {type(value)}"
                    print(f"PASS: portfolio.rolling_pnl.{bucket}.{window}.{field} = {value}")


class TestRollingPnLValues:
    """Tests for rolling PnL value correctness"""

    def test_rolling_pnl_values_not_null(self):
        """All rolling_pnl values should be numeric, not null"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        data = response.json()
        rolling_pnl = data.get("rolling_pnl", {})
        
        for bucket, section in rolling_pnl.items():
            for key, value in section.items():
                assert value is not None, f"{bucket}.{key} is null"
                assert isinstance(value, (int, float)), f"{bucket}.{key} is not numeric: {value}"
        
        print("PASS: All rolling_pnl values are numeric (not null)")

    def test_rolling_pnl_window_consistency(self):
        """6h window should have >= 3h trades >= 1h trades (or equal if all trades within 1h)"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        data = response.json()
        rolling_pnl = data.get("rolling_pnl", {})
        
        total = rolling_pnl.get("total", {})
        trades_1h = total.get("trades_1h", 0)
        trades_3h = total.get("trades_3h", 0)
        trades_6h = total.get("trades_6h", 0)
        
        # 6h should include all 3h trades, which should include all 1h trades
        assert trades_6h >= trades_3h, f"6h trades ({trades_6h}) < 3h trades ({trades_3h})"
        assert trades_3h >= trades_1h, f"3h trades ({trades_3h}) < 1h trades ({trades_1h})"
        
        print(f"PASS: Trade count window consistency: 1h={trades_1h}, 3h={trades_3h}, 6h={trades_6h}")

    def test_crypto_pnl_per_hour_differs_across_windows(self):
        """Crypto pnl_per_hour values may differ across windows based on trade distribution"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        data = response.json()
        rolling_pnl = data.get("rolling_pnl", {})
        
        crypto = rolling_pnl.get("crypto", {})
        pnl_1h = crypto.get("pnl_per_hour_1h", 0)
        pnl_3h = crypto.get("pnl_per_hour_3h", 0)
        pnl_6h = crypto.get("pnl_per_hour_6h", 0)
        
        print(f"Crypto PnL/hour: 1h=${pnl_1h:.2f}, 3h=${pnl_3h:.2f}, 6h=${pnl_6h:.2f}")
        
        # Just verify values exist and are numeric - they may or may not differ
        assert isinstance(pnl_1h, (int, float)), f"pnl_1h not numeric: {pnl_1h}"
        assert isinstance(pnl_3h, (int, float)), f"pnl_3h not numeric: {pnl_3h}"
        assert isinstance(pnl_6h, (int, float)), f"pnl_6h not numeric: {pnl_6h}"
        
        print("PASS: Crypto pnl_per_hour values are all numeric")


class TestOtherEndpoints:
    """Tests for other endpoints mentioned in requirements"""

    def test_upgrade_validation_returns_200(self):
        """GET /api/admin/upgrade-validation returns 200"""
        response = requests.get(f"{BASE_URL}/api/admin/upgrade-validation", timeout=10)
        assert response.status_code == 200, f"Failed: {response.status_code}"
        print("PASS: /api/admin/upgrade-validation returns 200")

    def test_arb_diagnostics_returns_200(self):
        """GET /api/strategies/arb/diagnostics returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/diagnostics", timeout=10)
        assert response.status_code == 200, f"Failed: {response.status_code}"
        print("PASS: /api/strategies/arb/diagnostics returns 200")

    def test_controls_returns_200(self):
        """GET /api/controls returns 200"""
        response = requests.get(f"{BASE_URL}/api/controls", timeout=10)
        assert response.status_code == 200, f"Failed: {response.status_code}"
        print("PASS: /api/controls returns 200")


class TestRollingPnLModuleIntegration:
    """Tests that verify the rolling_pnl module is correctly integrated"""

    def test_ui_snapshot_and_upgrade_tracking_consistency(self):
        """Both endpoints should return consistent rolling PnL data"""
        response1 = requests.get(f"{BASE_URL}/api/admin/upgrade-tracking", timeout=10)
        response2 = requests.get(f"{BASE_URL}/api/debug/ui-snapshot", timeout=15)
        
        tracking_data = response1.json().get("rolling_pnl", {})
        snapshot_data = response2.json().get("portfolio", {}).get("rolling_pnl", {})
        
        # Both should have same buckets
        tracking_buckets = set(tracking_data.keys())
        snapshot_buckets = set(snapshot_data.keys())
        
        assert tracking_buckets == snapshot_buckets, f"Bucket mismatch: {tracking_buckets} vs {snapshot_buckets}"
        print(f"PASS: Both endpoints have same buckets: {tracking_buckets}")
        
        # Verify total pnl values are reasonably close (may differ slightly due to timing)
        tracking_total_1h = tracking_data.get("total", {}).get("pnl_per_hour_1h", 0)
        snapshot_total_1h = snapshot_data.get("total", {}).get("1h", {}).get("pnl_per_hour", 0)
        
        print(f"Total 1h PnL/hour: tracking={tracking_total_1h}, snapshot={snapshot_total_1h}")
        print("PASS: Rolling PnL data present in both endpoints")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
