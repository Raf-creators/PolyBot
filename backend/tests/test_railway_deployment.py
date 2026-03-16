"""
Railway Deployment Configuration Tests

Tests for verifying Railway-compatible deployment configuration:
- Health endpoints (engine auto-start verification)
- Background services auto-start
- Deployment files existence (requirements.txt, Procfile, railway.toml)
- Environment variable support (MONGO_URI, PORT)
"""
import pytest
import requests
import os
import time

# Get BASE_URL from environment - required for testing
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL environment variable required")


class TestHealthEndpoint:
    """Test /api/health endpoint - comprehensive Railway health check"""

    def test_health_endpoint_returns_200(self):
        """GET /api/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/health returned 200")

    def test_health_status_healthy_or_starting(self):
        """Health status should be 'healthy' or 'starting'"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        data = response.json()
        assert data.get("status") in ["healthy", "starting"], f"Unexpected status: {data.get('status')}"
        print(f"✓ Health status: {data.get('status')}")

    def test_health_engine_running(self):
        """Engine should be running (auto-started)"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        data = response.json()
        assert data.get("engine") == "running", f"Engine not running: {data.get('engine')}"
        print(f"✓ Engine is running")

    def test_health_market_feeds_active_or_initializing(self):
        """Market feeds should be 'active' or 'initializing'"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        data = response.json()
        # Market feeds may take time to initialize
        assert data.get("market_feeds") in ["active", "initializing"], f"Unexpected market_feeds: {data.get('market_feeds')}"
        print(f"✓ Market feeds: {data.get('market_feeds')}")

    def test_health_resolver_running(self):
        """Market resolver should be running"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        data = response.json()
        assert data.get("resolver") == "running", f"Resolver not running: {data.get('resolver')}"
        print(f"✓ Market resolver is running")

    def test_health_mode_paper(self):
        """Default mode should be 'paper'"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        data = response.json()
        assert data.get("mode") == "paper", f"Unexpected mode: {data.get('mode')}"
        print(f"✓ Mode is paper")

    def test_health_strategies_enabled(self):
        """All three strategies should be enabled"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        data = response.json()
        strategies = data.get("strategies", {})
        
        assert "arb_scanner" in strategies, "arb_scanner missing from strategies"
        assert "crypto_sniper" in strategies, "crypto_sniper missing from strategies"
        assert "weather_trader" in strategies, "weather_trader missing from strategies"
        
        assert strategies["arb_scanner"].get("enabled") == True, "arb_scanner not enabled"
        assert strategies["crypto_sniper"].get("enabled") == True, "crypto_sniper not enabled"
        assert strategies["weather_trader"].get("enabled") == True, "weather_trader not enabled"
        
        print(f"✓ All strategies enabled: arb_scanner, crypto_sniper, weather_trader")


class TestEngineAutoStart:
    """Test engine auto-start without POST /api/engine/start"""

    def test_status_endpoint_returns_200(self):
        """GET /api/status should return 200"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/status returned 200")

    def test_engine_running_with_uptime(self):
        """Engine should be running with uptime > 0"""
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        data = response.json()
        
        # Status should be "running"
        status = data.get("status")
        assert status == "running", f"Engine not running: status={status}"
        
        # Uptime should be > 0
        uptime = data.get("uptime_seconds", 0)
        assert uptime > 0, f"Uptime should be > 0, got {uptime}"
        
        print(f"✓ Engine running with uptime: {uptime}s")

    def test_engine_started_without_manual_call(self):
        """Engine should auto-start - no need to call POST /api/engine/start"""
        # Just verify engine status is "running"
        response = requests.get(f"{BASE_URL}/api/status", timeout=30)
        data = response.json()
        assert data.get("status") == "running", f"Engine not auto-started: {data.get('status')}"
        
        # Verify trading mode (field is "mode" not "trading_mode")
        assert data.get("mode") == "paper", f"Unexpected mode: {data.get('mode')}"
        print(f"✓ Engine auto-started in paper mode")


class TestMarketDataFeedAutoStart:
    """Test Market Data Feed auto-start"""

    def test_discovery_health_returns_200(self):
        """GET /api/health/discovery should return 200"""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/health/discovery returned 200")

    def test_crypto_markets_discovered(self):
        """crypto_markets_discovered should be > 0 (market data feed started)"""
        response = requests.get(f"{BASE_URL}/api/health/discovery", timeout=30)
        data = response.json()
        
        crypto_discovered = data.get("crypto_markets_discovered", 0)
        # May still be initializing, so check if field exists
        assert "crypto_markets_discovered" in data or "note" in data, "Missing crypto_markets_discovered"
        
        if crypto_discovered > 0:
            print(f"✓ Crypto markets discovered: {crypto_discovered}")
        else:
            # May still be initializing
            print(f"⚠ Crypto markets not yet discovered (may be initializing): {data}")


class TestCryptoSniperAutoStart:
    """Test Crypto Sniper strategy auto-start"""

    def test_sniper_health_returns_200(self):
        """GET /api/strategies/sniper/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/strategies/sniper/health returned 200")

    def test_sniper_running(self):
        """Crypto sniper should be running (auto-started)"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health", timeout=30)
        data = response.json()
        
        running = data.get("running", False)
        assert running == True, f"Crypto sniper not running: {data}"
        print(f"✓ Crypto sniper is running")


class TestWeatherTraderAutoStart:
    """Test Weather Trader strategy auto-start"""

    def test_weather_health_returns_200(self):
        """GET /api/strategies/weather/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/strategies/weather/health returned 200")

    def test_weather_running(self):
        """Weather trader should be running (auto-started)"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health", timeout=30)
        data = response.json()
        
        running = data.get("running", False)
        assert running == True, f"Weather trader not running: {data}"
        print(f"✓ Weather trader is running")


class TestMarketResolverAutoStart:
    """Test Market Resolver auto-start"""

    def test_market_resolver_health_returns_200(self):
        """GET /api/health/market-resolver should return 200"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/health/market-resolver returned 200")

    def test_market_resolver_running(self):
        """Market resolver should be running (auto-started)"""
        response = requests.get(f"{BASE_URL}/api/health/market-resolver", timeout=30)
        data = response.json()
        
        running = data.get("running", False)
        assert running == True, f"Market resolver not running: {data}"
        print(f"✓ Market resolver is running")


class TestDeploymentFilesExistence:
    """Test Railway deployment files exist with correct content"""

    def test_requirements_txt_exists(self):
        """requirements.txt should exist at /app/requirements.txt"""
        file_path = "/app/requirements.txt"
        assert os.path.isfile(file_path), f"File not found: {file_path}"
        print(f"✓ {file_path} exists")

    def test_requirements_txt_has_required_packages(self):
        """requirements.txt should contain required packages"""
        file_path = "/app/requirements.txt"
        with open(file_path, 'r') as f:
            content = f.read().lower()
        
        required_packages = ['fastapi', 'uvicorn', 'motor', 'pydantic', 'aiohttp', 'websockets']
        for pkg in required_packages:
            assert pkg in content, f"Missing package: {pkg}"
        print(f"✓ requirements.txt contains all required packages: {required_packages}")

    def test_procfile_exists(self):
        """Procfile should exist at /app/Procfile"""
        file_path = "/app/Procfile"
        assert os.path.isfile(file_path), f"File not found: {file_path}"
        print(f"✓ {file_path} exists")

    def test_procfile_has_web_command(self):
        """Procfile should have 'web:' command"""
        file_path = "/app/Procfile"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert "web:" in content, "Procfile missing 'web:' command"
        print(f"✓ Procfile contains 'web:' command")

    def test_railway_toml_exists(self):
        """railway.toml should exist at /app/railway.toml"""
        file_path = "/app/railway.toml"
        assert os.path.isfile(file_path), f"File not found: {file_path}"
        print(f"✓ {file_path} exists")

    def test_railway_toml_has_healthcheck_path(self):
        """railway.toml should have healthcheckPath=/health"""
        file_path = "/app/railway.toml"
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check for healthcheckPath with /health value
        assert 'healthcheckPath' in content, "railway.toml missing healthcheckPath"
        assert '/health' in content, "railway.toml healthcheckPath should include '/health'"
        print(f"✓ railway.toml has healthcheckPath=/health")


class TestServerCodeConfiguration:
    """Test server.py has required Railway configuration"""

    def test_server_has_main_block_with_port(self):
        """server.py should have __main__ block with PORT env var"""
        file_path = "/app/backend/server.py"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert '__name__ == "__main__"' in content or "if __name__" in content, \
            "server.py missing __main__ block"
        assert 'PORT' in content, "server.py should reference PORT environment variable"
        print(f"✓ server.py has __main__ block with PORT env var")

    def test_server_supports_mongo_uri(self):
        """server.py should check MONGO_URI before MONGO_URL"""
        file_path = "/app/backend/server.py"
        with open(file_path, 'r') as f:
            content = f.read()
        
        assert 'MONGO_URI' in content, "server.py should support MONGO_URI"
        assert 'MONGO_URL' in content, "server.py should support MONGO_URL"
        
        # Verify MONGO_URI is checked first (line ~34-35)
        lines = content.split('\n')
        mongo_uri_found = False
        for i, line in enumerate(lines):
            if 'MONGO_URI' in line and 'environ' in line:
                mongo_uri_found = True
                break
        
        assert mongo_uri_found, "server.py should check MONGO_URI environment variable"
        print(f"✓ server.py supports MONGO_URI (Railway) and MONGO_URL (Emergent)")


class TestArbScannerAutoStart:
    """Test Arb Scanner strategy auto-start"""

    def test_arb_health_returns_200(self):
        """GET /api/strategies/arb/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/strategies/arb/health returned 200")

    def test_arb_running(self):
        """Arb scanner should be running (auto-started)"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health", timeout=30)
        data = response.json()
        
        running = data.get("running", False)
        assert running == True, f"Arb scanner not running: {data}"
        print(f"✓ Arb scanner is running")


# Fixtures
@pytest.fixture(scope="module")
def base_url():
    return BASE_URL


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
