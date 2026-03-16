"""
Test: Crypto Sniper Market Discovery Pipeline Fix
Tests the targeted slug-construction approach for discovering short-lived crypto updown markets.

Key features verified:
1. GET /api/health/discovery - crypto metrics
2. GET /api/strategies/sniper/health - classification and evaluation
3. GET /api/strategies/sniper/signals - signals endpoint works
4. Slug pattern validation
5. Discovery refresh verification
"""

import pytest
import requests
import os
import re
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


@pytest.fixture(scope="module", autouse=True)
def ensure_engine_started():
    """Ensure engine is started before running tests"""
    # Check current status
    resp = requests.get(f"{BASE_URL}/api/health")
    if resp.status_code == 200 and resp.json().get("engine") == "stopped":
        # Start the engine
        start_resp = requests.post(f"{BASE_URL}/api/engine/start")
        if start_resp.status_code == 200:
            print("Engine started successfully")
            # Wait for discovery to run
            time.sleep(10)
        else:
            print(f"Warning: Could not start engine: {start_resp.status_code}")
    else:
        print(f"Engine status: {resp.json().get('engine', 'unknown')}")
    yield

class TestCryptoSniperDiscovery:
    """Test crypto sniper market discovery pipeline fix"""

    def test_health_discovery_crypto_markets_discovered(self):
        """Verify crypto_markets_discovered > 0 (core fix verification)"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        crypto_discovered = data.get("crypto_markets_discovered", 0)
        assert crypto_discovered > 0, f"crypto_markets_discovered should be > 0, got {crypto_discovered}"
        print(f"✅ crypto_markets_discovered = {crypto_discovered}")

    def test_health_discovery_crypto_slugs_hit(self):
        """Verify crypto_slugs_hit > 0 (slug queries returning results)"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200
        
        data = response.json()
        slugs_hit = data.get("crypto_slugs_hit", 0)
        assert slugs_hit > 0, f"crypto_slugs_hit should be > 0, got {slugs_hit}"
        print(f"✅ crypto_slugs_hit = {slugs_hit}")

    def test_health_discovery_crypto_active_slugs_contain_btc_eth(self):
        """Verify crypto_active_slugs contains btc-updown and eth-updown slugs"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200
        
        data = response.json()
        active_slugs = data.get("crypto_active_slugs", [])
        assert len(active_slugs) > 0, "crypto_active_slugs should not be empty"
        
        btc_slugs = [s for s in active_slugs if s.startswith("btc-updown-")]
        eth_slugs = [s for s in active_slugs if s.startswith("eth-updown-")]
        
        assert len(btc_slugs) > 0, "Should have at least one btc-updown slug"
        assert len(eth_slugs) > 0, "Should have at least one eth-updown slug"
        print(f"✅ BTC slugs: {len(btc_slugs)}, ETH slugs: {len(eth_slugs)}")

    def test_health_discovery_no_1h_markets(self):
        """Verify 1h window markets don't currently exist (confirmed not on Polymarket)"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200
        
        data = response.json()
        active_slugs = data.get("crypto_active_slugs", [])
        
        # 1h slugs should NOT be present since they don't exist on Polymarket
        has_1h = [s for s in active_slugs if "-1h-" in s]
        assert len(has_1h) == 0, f"1h markets should not exist, found: {has_1h}"
        print("✅ No 1h markets found (correct - not available on Polymarket)")

    def test_health_discovery_slug_pattern_valid(self):
        """Verify all crypto_active_slugs match pattern {asset}-updown-{window}-{unix_ts}"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200
        
        data = response.json()
        active_slugs = data.get("crypto_active_slugs", [])
        
        # Pattern: {asset}-updown-{window}-{unix_timestamp}
        # asset: btc or eth
        # window: 5m, 15m, 1h, 4h
        # unix_ts: 10+ digit timestamp
        pattern = re.compile(r'^(btc|eth)-updown-(5m|15m|1h|4h)-(\d{10,})$')
        
        invalid_slugs = []
        for slug in active_slugs:
            if not pattern.match(slug):
                invalid_slugs.append(slug)
        
        assert len(invalid_slugs) == 0, f"Invalid slug patterns found: {invalid_slugs}"
        print(f"✅ All {len(active_slugs)} slugs match valid pattern")

    def test_sniper_health_markets_classified(self):
        """Verify markets_classified > 0"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        
        data = response.json()
        markets_classified = data.get("markets_classified", 0)
        assert markets_classified > 0, f"markets_classified should be > 0, got {markets_classified}"
        print(f"✅ markets_classified = {markets_classified}")

    def test_sniper_health_markets_evaluated(self):
        """Verify markets_evaluated > 0"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        
        data = response.json()
        markets_evaluated = data.get("markets_evaluated", 0)
        assert markets_evaluated > 0, f"markets_evaluated should be > 0, got {markets_evaluated}"
        print(f"✅ markets_evaluated = {markets_evaluated}")

    def test_sniper_health_running(self):
        """Verify sniper strategy is running"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        
        data = response.json()
        running = data.get("running", False)
        assert running is True, "Sniper strategy should be running"
        print("✅ Sniper running = True")

    def test_sniper_signals_endpoint_works(self):
        """Verify /api/strategies/sniper/signals returns correctly"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert response.status_code == 200
        
        data = response.json()
        # Should have structure with tradable/rejected arrays
        assert "tradable" in data, "Response should have 'tradable' key"
        assert "rejected" in data, "Response should have 'rejected' key"
        assert isinstance(data["tradable"], list), "'tradable' should be a list"
        assert isinstance(data["rejected"], list), "'rejected' should be a list"
        print(f"✅ Signals endpoint works - tradable: {len(data['tradable'])}, rejected: {len(data['rejected'])}")

    def test_discovery_btc_eth_counts(self):
        """Verify BTC and ETH market counts are tracked"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200
        
        data = response.json()
        btc_count = data.get("crypto_updown_btc", 0)
        eth_count = data.get("crypto_updown_eth", 0)
        
        assert btc_count > 0, f"crypto_updown_btc should be > 0, got {btc_count}"
        assert eth_count > 0, f"crypto_updown_eth should be > 0, got {eth_count}"
        
        # Total should match
        total = data.get("crypto_markets_discovered", 0)
        assert btc_count + eth_count == total, f"BTC({btc_count}) + ETH({eth_count}) should equal total({total})"
        print(f"✅ BTC: {btc_count}, ETH: {eth_count}, Total: {total}")

    def test_discovery_no_fetch_errors(self):
        """Verify no crypto fetch errors"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200
        
        data = response.json()
        errors = data.get("crypto_fetch_errors", -1)
        assert errors == 0, f"crypto_fetch_errors should be 0, got {errors}"
        print("✅ crypto_fetch_errors = 0")

    def test_discovery_timestamps_present(self):
        """Verify last_crypto_fetch timestamp is present and recent"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200
        
        data = response.json()
        last_crypto_fetch = data.get("last_crypto_fetch")
        assert last_crypto_fetch is not None, "last_crypto_fetch should not be None"
        assert len(last_crypto_fetch) > 0, "last_crypto_fetch should not be empty"
        print(f"✅ last_crypto_fetch = {last_crypto_fetch}")

    def test_discovery_slugs_queried_matches_expected(self):
        """Verify correct number of slugs were queried (8 combos * 4 lookahead = 32)"""
        response = requests.get(f"{BASE_URL}/api/health/discovery")
        assert response.status_code == 200
        
        data = response.json()
        slugs_queried = data.get("crypto_slugs_queried", 0)
        
        # CRYPTO_UPDOWN_COMBOS has 8 entries (btc/eth x 4 windows)
        # LOOKAHEAD = 3, so each combo queries current + 3 = 4 slugs
        expected = 8 * 4  # 32
        assert slugs_queried == expected, f"crypto_slugs_queried should be {expected}, got {slugs_queried}"
        print(f"✅ crypto_slugs_queried = {slugs_queried} (expected {expected})")


class TestDiscoveryRefresh:
    """Test that discovery refreshes correctly"""

    def test_discovery_refresh_changes_timestamp(self):
        """Verify last_crypto_fetch changes after 20s (discovery runs every 15s)"""
        # First call
        resp1 = requests.get(f"{BASE_URL}/api/health/discovery")
        assert resp1.status_code == 200
        ts1 = resp1.json().get("last_crypto_fetch")
        print(f"First call: last_crypto_fetch = {ts1}")
        
        # Wait 20 seconds for discovery loop to run
        print("Waiting 20 seconds for discovery refresh...")
        time.sleep(20)
        
        # Second call
        resp2 = requests.get(f"{BASE_URL}/api/health/discovery")
        assert resp2.status_code == 200
        ts2 = resp2.json().get("last_crypto_fetch")
        print(f"Second call: last_crypto_fetch = {ts2}")
        
        # Timestamps should be different (discovery refreshed)
        assert ts1 != ts2, f"Timestamp should have changed after 20s. ts1={ts1}, ts2={ts2}"
        print(f"✅ Discovery refreshed: {ts1} → {ts2}")


class TestSniperHealthMetrics:
    """Test sniper health metrics in detail"""

    def test_sniper_health_has_required_fields(self):
        """Verify sniper health response has all expected fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        
        data = response.json()
        required_fields = [
            "total_scans", "last_scan_time", "markets_classified",
            "markets_evaluated", "signals_generated", "signals_rejected",
            "running", "config", "price_buffer_sizes"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        print(f"✅ All required fields present")

    def test_sniper_vol_samples_warming_up(self):
        """Verify volatility buffers are accumulating samples"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        
        data = response.json()
        buffer_sizes = data.get("price_buffer_sizes", {})
        btc_samples = buffer_sizes.get("BTC", 0)
        eth_samples = buffer_sizes.get("ETH", 0)
        
        # Should have some samples (buffer warms up over time)
        assert btc_samples > 0, f"BTC buffer should have samples, got {btc_samples}"
        assert eth_samples > 0, f"ETH buffer should have samples, got {eth_samples}"
        print(f"✅ Vol buffer BTC: {btc_samples}, ETH: {eth_samples}")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
