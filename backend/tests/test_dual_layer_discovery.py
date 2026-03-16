"""
Test suite for dual-layer market discovery feature (iteration 30).

Tests:
1. GET /api/health/discovery - returns discovery stats
2. GET /api/status - includes discovery in stats.health.discovery
3. Discovery stats structure validation
4. Regression tests for all health endpoints
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestDiscoveryHealthEndpoint:
    """Tests for GET /api/health/discovery endpoint."""
    
    def test_discovery_endpoint_returns_200(self):
        """Discovery endpoint should return 200."""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/health/discovery returns 200")
    
    def test_discovery_stats_structure(self):
        """Discovery stats should have correct structure."""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        required_fields = [
            "broad_markets_loaded",
            "crypto_markets_discovered",
            "crypto_events_scanned",
            "crypto_updown_btc",
            "crypto_updown_eth",
            "crypto_other",
            "last_broad_fetch",
            "last_crypto_fetch",
            "crypto_fetch_errors",
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"PASS: Discovery stats has all required fields: {list(data.keys())}")
    
    def test_broad_markets_loaded_500(self):
        """Broad discovery should load 500 markets."""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert data["broad_markets_loaded"] == 500, f"Expected 500, got {data['broad_markets_loaded']}"
        print(f"PASS: broad_markets_loaded = {data['broad_markets_loaded']}")
    
    def test_crypto_events_scanned_3000(self):
        """Crypto discovery should scan 3000 events."""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert data["crypto_events_scanned"] == 3000, f"Expected 3000, got {data['crypto_events_scanned']}"
        print(f"PASS: crypto_events_scanned = {data['crypto_events_scanned']}")
    
    def test_no_crypto_fetch_errors(self):
        """There should be no crypto fetch errors."""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert data["crypto_fetch_errors"] == 0, f"Expected 0 errors, got {data['crypto_fetch_errors']}"
        print(f"PASS: crypto_fetch_errors = {data['crypto_fetch_errors']}")
    
    def test_timestamps_present(self):
        """last_broad_fetch and last_crypto_fetch should be present."""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert data["last_broad_fetch"] is not None, "last_broad_fetch should not be None"
        assert data["last_crypto_fetch"] is not None, "last_crypto_fetch should not be None"
        print(f"PASS: Timestamps present - broad: {data['last_broad_fetch']}, crypto: {data['last_crypto_fetch']}")
    
    def test_crypto_markets_discovered_zero_expected(self):
        """Currently all crypto updown markets are expired, so 0 is expected."""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        # 0 is correct because all updown markets are expired
        assert data["crypto_markets_discovered"] == 0, f"Expected 0 (all expired), got {data['crypto_markets_discovered']}"
        print(f"PASS: crypto_markets_discovered = {data['crypto_markets_discovered']} (all expired, correct)")


class TestDiscoveryInStatus:
    """Tests for discovery stats in /api/status response."""
    
    def test_status_contains_discovery(self):
        """GET /api/status should include discovery in stats.health."""
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "stats" in data, "Missing 'stats' in response"
        assert "health" in data["stats"], "Missing 'health' in stats"
        assert "discovery" in data["stats"]["health"], "Missing 'discovery' in stats.health"
        
        discovery = data["stats"]["health"]["discovery"]
        print(f"PASS: Discovery injected into /api/status: {list(discovery.keys())}")
    
    def test_status_discovery_matches_endpoint(self):
        """Discovery in /api/status should match /api/health/discovery."""
        status_response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        discovery_response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=10)
        
        assert status_response.status_code == 200
        assert discovery_response.status_code == 200
        
        status_discovery = status_response.json()["stats"]["health"]["discovery"]
        direct_discovery = discovery_response.json()
        
        # Key fields should match
        assert status_discovery["broad_markets_loaded"] == direct_discovery["broad_markets_loaded"]
        assert status_discovery["crypto_events_scanned"] == direct_discovery["crypto_events_scanned"]
        assert status_discovery["crypto_fetch_errors"] == direct_discovery["crypto_fetch_errors"]
        
        print("PASS: Discovery stats in /api/status match /api/health/discovery")


class TestSniperHealthWithDiscovery:
    """Tests for sniper health with dual-layer discovery."""
    
    def test_sniper_health_returns_200(self):
        """Sniper health should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=10)
        assert response.status_code == 200
        print("PASS: GET /api/strategies/sniper/health returns 200")
    
    def test_sniper_has_markets_classified(self):
        """Sniper should have at least 1 market classified (BTC $1M)."""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert data["markets_classified"] >= 1, f"Expected >=1, got {data['markets_classified']}"
        print(f"PASS: markets_classified = {data['markets_classified']}")


class TestArbHealthWithDiscovery:
    """Tests for arb scanner health with dual-layer discovery."""
    
    def test_arb_health_returns_200(self):
        """Arb health should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health", timeout=10)
        assert response.status_code == 200
        print("PASS: GET /api/strategies/arb/health returns 200")
    
    def test_arb_pairs_scanned_500(self):
        """Arb should scan 500 pairs from broad discovery."""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert data["pairs_scanned"] == 500, f"Expected 500, got {data['pairs_scanned']}"
        print(f"PASS: pairs_scanned = {data['pairs_scanned']}")


class TestRegressionEndpoints:
    """Regression tests for existing health endpoints."""
    
    def test_health_returns_200(self):
        """GET /api/health should return 200."""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("PASS: GET /api/health returns 200 with status=healthy")
    
    def test_status_returns_200(self):
        """GET /api/status should return 200."""
        response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert response.status_code == 200
        print("PASS: GET /api/status returns 200")
    
    def test_weather_health_returns_200(self):
        """GET /api/strategies/weather/health should return 200."""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health", timeout=10)
        assert response.status_code == 200
        print("PASS: GET /api/strategies/weather/health returns 200")
    
    def test_global_analytics_returns_200(self):
        """GET /api/analytics/global should return 200."""
        response = requests.get(f"{BASE_URL}/api/analytics/global", timeout=10)
        assert response.status_code == 200
        print("PASS: GET /api/analytics/global returns 200")
    
    def test_auto_resolver_running(self):
        """GET /api/health/auto-resolver should show running=true."""
        response = requests.get(f"{BASE_URL}/api/health/auto-resolver", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("running") == True, f"Expected running=true, got {data.get('running')}"
        print("PASS: GET /api/health/auto-resolver shows running=true")


if __name__ == "__main__":
    # Run tests manually
    import sys
    pytest.main([__file__, "-v", "--tb=short", "-x"])
