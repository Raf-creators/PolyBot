"""
Phase 5A: Crypto Sniper Strategy Backend Tests
Tests for BTC/ETH crypto market sniper strategy endpoints and pricing module
"""

import pytest
import requests
import os
import sys
import time

# Add backend to path for unit tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# ======================= PRICING MODULE UNIT TESTS =======================

class TestSniperPricingModule:
    """Unit tests for sniper_pricing.py functions"""
    
    def test_normal_cdf_at_zero(self):
        """normal_cdf(0) should return ~0.5 (standard normal at mean)"""
        from engine.strategies.sniper_pricing import normal_cdf
        result = normal_cdf(0)
        assert abs(result - 0.5) < 0.001, f"Expected ~0.5, got {result}"
        print(f"PASS: normal_cdf(0) = {result}")
    
    def test_normal_cdf_positive(self):
        """normal_cdf(2) should return ~0.977"""
        from engine.strategies.sniper_pricing import normal_cdf
        result = normal_cdf(2)
        assert 0.97 < result < 0.98, f"Expected ~0.977, got {result}"
        print(f"PASS: normal_cdf(2) = {result}")
    
    def test_normal_cdf_negative(self):
        """normal_cdf(-2) should return ~0.023"""
        from engine.strategies.sniper_pricing import normal_cdf
        result = normal_cdf(-2)
        assert 0.02 < result < 0.03, f"Expected ~0.023, got {result}"
        print(f"PASS: normal_cdf(-2) = {result}")
    
    def test_fair_probability_atm(self):
        """ATM (spot=strike) with above direction should return ~0.5"""
        from engine.strategies.sniper_pricing import compute_fair_probability
        result = compute_fair_probability(
            spot=100, strike=100, vol=0.5, tte_seconds=300, direction='above'
        )
        assert 0.4 < result < 0.6, f"Expected ~0.5 for ATM, got {result}"
        print(f"PASS: ATM fair_prob = {result}")
    
    def test_fair_probability_itm(self):
        """ITM (spot > strike) with above direction should return >0.7"""
        from engine.strategies.sniper_pricing import compute_fair_probability
        result = compute_fair_probability(
            spot=110, strike=100, vol=0.5, tte_seconds=300, direction='above'
        )
        assert result > 0.7, f"Expected >0.7 for ITM, got {result}"
        print(f"PASS: ITM fair_prob = {result}")
    
    def test_fair_probability_otm(self):
        """OTM (spot < strike) with above direction should return <0.35"""
        from engine.strategies.sniper_pricing import compute_fair_probability
        result = compute_fair_probability(
            spot=90, strike=100, vol=0.5, tte_seconds=300, direction='above'
        )
        assert result < 0.35, f"Expected <0.35 for OTM, got {result}"
        print(f"PASS: OTM fair_prob = {result}")
    
    def test_fair_probability_below_direction(self):
        """Below direction inverts probability"""
        from engine.strategies.sniper_pricing import compute_fair_probability
        above = compute_fair_probability(
            spot=110, strike=100, vol=0.5, tte_seconds=300, direction='above'
        )
        below = compute_fair_probability(
            spot=110, strike=100, vol=0.5, tte_seconds=300, direction='below'
        )
        # above + below should be ~1.0
        assert abs((above + below) - 1.0) < 0.01, f"above={above}, below={below}"
        print(f"PASS: above={above:.4f}, below={below:.4f}, sum={above+below:.4f}")
    
    def test_edge_bps_calculation(self):
        """compute_edge_bps(0.6, 0.4) should return 2000.0 bps"""
        from engine.strategies.sniper_pricing import compute_edge_bps
        result = compute_edge_bps(0.6, 0.4)
        assert result == 2000.0, f"Expected 2000.0, got {result}"
        print(f"PASS: edge_bps = {result}")
    
    def test_edge_bps_negative(self):
        """compute_edge_bps(0.4, 0.6) should return -2000.0 bps"""
        from engine.strategies.sniper_pricing import compute_edge_bps
        result = compute_edge_bps(0.4, 0.6)
        assert result == -2000.0, f"Expected -2000.0, got {result}"
        print(f"PASS: negative edge_bps = {result}")
    
    def test_realized_volatility_insufficient_samples(self):
        """compute_realized_volatility should return None with < min_samples"""
        from engine.strategies.sniper_pricing import compute_realized_volatility
        from collections import deque
        prices = deque([(i, 100 + i*0.1) for i in range(5)], maxlen=100)
        result = compute_realized_volatility(prices, min_samples=30)
        assert result is None, f"Expected None, got {result}"
        print(f"PASS: insufficient samples returns None")
    
    def test_realized_volatility_sufficient_samples(self):
        """compute_realized_volatility should return positive value with enough samples"""
        from engine.strategies.sniper_pricing import compute_realized_volatility
        from collections import deque
        import random
        random.seed(42)
        prices = deque([(i*5, 100 + random.gauss(0, 1)) for i in range(40)], maxlen=100)
        result = compute_realized_volatility(prices, min_samples=30)
        assert result is not None and result > 0, f"Expected positive value, got {result}"
        print(f"PASS: sufficient samples vol = {result}")
    
    def test_momentum_calculation(self):
        """compute_momentum returns fractional return"""
        from engine.strategies.sniper_pricing import compute_momentum
        from collections import deque
        prices = deque([(i, 100 + i*0.5) for i in range(100)], maxlen=200)
        result = compute_momentum(prices, lookback_seconds=50)
        assert result > 0, f"Expected positive momentum, got {result}"
        print(f"PASS: momentum = {result}")
    
    def test_signal_confidence_high_liquidity(self):
        """compute_signal_confidence with good params returns >0.5"""
        from engine.strategies.sniper_pricing import compute_signal_confidence
        result = compute_signal_confidence(
            liquidity=6000, data_age_seconds=10, spread=0.01,
            vol_quality=1.0, tte_seconds=300, min_tte=30, max_tte=900
        )
        assert result > 0.5, f"Expected >0.5, got {result}"
        print(f"PASS: high confidence = {result}")


# ======================= MARKET CLASSIFICATION TESTS =======================

class TestMarketClassification:
    """Unit tests for crypto_sniper.classify_market_question"""
    
    def test_parse_btc_above(self):
        """Parse 'Will BTC be above $97,000 at 12:15 UTC?'"""
        from engine.strategies.crypto_sniper import classify_market_question
        q = 'Will BTC be above $97,000 at 12:15 UTC?'
        result, reason = classify_market_question(q, 'cid1', 'yes1', 'no1')
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.direction == "above"
        assert result.strike == 97000.0
        print(f"PASS: Parsed BTC above - asset={result.asset}, dir={result.direction}, strike={result.strike}")
    
    def test_parse_eth_below(self):
        """Parse 'Will ETH be below $3,500 at 14:30 UTC?'"""
        from engine.strategies.crypto_sniper import classify_market_question
        q = 'Will ETH be below $3,500 at 14:30 UTC?'
        result, reason = classify_market_question(q, 'cid2', 'yes2', 'no2')
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "ETH"
        assert result.direction == "below"
        assert result.strike == 3500.0
        print(f"PASS: Parsed ETH below - asset={result.asset}, dir={result.direction}, strike={result.strike}")
    
    def test_parse_bitcoin_variant(self):
        """Parse 'Bitcoin above $100,000 at 18:00 UTC?'"""
        from engine.strategies.crypto_sniper import classify_market_question
        q = 'Bitcoin above $100,000 at 18:00 UTC?'
        result, reason = classify_market_question(q, 'cid3', 'yes3', 'no3')
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.asset == "BTC"
        assert result.direction == "above"
        assert result.strike == 100000.0
        print(f"PASS: Bitcoin variant parsed correctly")
    
    def test_reject_non_crypto(self):
        """Non-crypto question returns no_regex_match"""
        from engine.strategies.crypto_sniper import classify_market_question
        q = 'Will Donald Trump win the election?'
        result, reason = classify_market_question(q, 'cid4', 'yes4', 'no4')
        assert result is None
        assert reason == "no_regex_match"
        print(f"PASS: Non-crypto rejected with reason: {reason}")
    
    def test_parse_price_without_comma(self):
        """Parse 'Will BTC be above $95000 at 15:00 UTC?'"""
        from engine.strategies.crypto_sniper import classify_market_question
        q = 'Will BTC be above $95000 at 15:00 UTC?'
        result, reason = classify_market_question(q, 'cid5', 'yes5', 'no5')
        assert result is not None, f"Expected classification, got rejection: {reason}"
        assert result.strike == 95000.0
        print(f"PASS: Price without comma parsed - strike={result.strike}")


# ======================= SNIPER API ENDPOINT TESTS =======================

class TestSniperHealthEndpoint:
    """Tests for GET /api/strategies/sniper/health"""
    
    def test_health_returns_200(self):
        """Sniper health endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        print(f"PASS: GET /api/strategies/sniper/health returned 200")
    
    def test_health_contains_config(self):
        """Health response contains config with min_edge_bps"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        assert "config" in data
        assert "min_edge_bps" in data["config"]
        assert data["config"]["min_edge_bps"] == 200.0
        print(f"PASS: Health contains config with min_edge_bps={data['config']['min_edge_bps']}")
    
    def test_health_contains_running_state(self):
        """Health response contains running boolean"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        assert "running" in data
        assert isinstance(data["running"], bool)
        print(f"PASS: Health contains running={data['running']}")
    
    def test_health_contains_price_buffers(self):
        """Health response contains price_buffer_sizes for BTC and ETH"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        assert "price_buffer_sizes" in data
        assert "BTC" in data["price_buffer_sizes"]
        assert "ETH" in data["price_buffer_sizes"]
        print(f"PASS: Price buffers - BTC={data['price_buffer_sizes']['BTC']}, ETH={data['price_buffer_sizes']['ETH']}")
    
    def test_health_contains_metrics(self):
        """Health response contains key metrics"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        data = response.json()
        expected_keys = ["total_scans", "signals_generated", "signals_rejected", "signals_executed"]
        for key in expected_keys:
            assert key in data, f"Missing metric: {key}"
        print(f"PASS: Health contains metrics - scans={data['total_scans']}, generated={data['signals_generated']}")


class TestSniperSignalsEndpoint:
    """Tests for GET /api/strategies/sniper/signals"""
    
    def test_signals_returns_200(self):
        """Signals endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert response.status_code == 200
        print(f"PASS: GET /api/strategies/sniper/signals returned 200")
    
    def test_signals_structure(self):
        """Signals response has tradable, rejected, total_tradable, total_rejected"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        assert "total_tradable" in data
        assert "total_rejected" in data
        print(f"PASS: Signals structure - tradable={data['total_tradable']}, rejected={data['total_rejected']}")
    
    def test_signals_limit_param(self):
        """Signals endpoint respects limit parameter"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals?limit=5")
        data = response.json()
        assert len(data["tradable"]) <= 5
        assert len(data["rejected"]) <= 5
        print(f"PASS: Limit param works - tradable={len(data['tradable'])}, rejected={len(data['rejected'])}")
    
    def test_signal_fields_if_present(self):
        """If signals exist, they have required fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        data = response.json()
        if data["tradable"]:
            sig = data["tradable"][0]
            required_fields = ["id", "condition_id", "asset", "direction", "strike", "spot_price",
                              "market_price", "fair_price", "edge_bps", "side", "token_id", "is_tradable"]
            for field in required_fields:
                assert field in sig, f"Missing field: {field}"
            print(f"PASS: Tradable signal has all fields - asset={sig['asset']}, edge={sig['edge_bps']}bps")
        else:
            print("INFO: No tradable signals to check structure")


class TestSniperExecutionsEndpoint:
    """Tests for GET /api/strategies/sniper/executions"""
    
    def test_executions_returns_200(self):
        """Executions endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/executions")
        assert response.status_code == 200
        print(f"PASS: GET /api/strategies/sniper/executions returned 200")
    
    def test_executions_structure(self):
        """Executions response has active and completed lists"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/executions")
        data = response.json()
        assert "active" in data
        assert "completed" in data
        assert isinstance(data["active"], list)
        assert isinstance(data["completed"], list)
        print(f"PASS: Executions structure - active={len(data['active'])}, completed={len(data['completed'])}")
    
    def test_completed_execution_fields_if_present(self):
        """If completed executions exist, they have required fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/executions")
        data = response.json()
        if data["completed"]:
            ex = data["completed"][0]
            required_fields = ["id", "signal_id", "condition_id", "asset", "side",
                              "order_id", "status", "target_edge_bps", "size"]
            for field in required_fields:
                assert field in ex, f"Missing field: {field}"
            print(f"PASS: Completed execution has all fields - status={ex['status']}, asset={ex['asset']}")
        else:
            print("INFO: No completed executions to check structure")


# ======================= INJECT CRYPTO MARKET TESTS =======================

class TestInjectCryptoMarket:
    """Tests for POST /api/test/inject-crypto-market"""
    
    def test_inject_requires_running_engine(self):
        """Inject endpoint requires engine to be running"""
        # First check if engine is running
        status_response = requests.get(f"{BASE_URL}/api/health")
        engine_status = status_response.json().get("engine", "stopped")
        
        if engine_status == "stopped":
            # Try to inject - should fail
            response = requests.post(f"{BASE_URL}/api/test/inject-crypto-market")
            assert response.status_code == 400
            assert "Engine must be running" in response.json().get("detail", "")
            print("PASS: Inject blocked when engine stopped")
        else:
            print(f"INFO: Engine is {engine_status}, skipping stopped test")


# ======================= CORE ENDPOINTS (REGRESSION) =======================

class TestCoreEndpointsRegression:
    """Verify existing core endpoints still work with sniper added"""
    
    def test_status_returns_200(self):
        """GET /api/status returns 200"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        print("PASS: GET /api/status returned 200")
    
    def test_status_shows_crypto_sniper(self):
        """Status shows crypto_sniper in strategies list"""
        response = requests.get(f"{BASE_URL}/api/status")
        data = response.json()
        assert "strategies" in data
        # strategies is a list of strategy objects
        strategies = data["strategies"]
        assert isinstance(strategies, list), f"Expected list, got {type(strategies)}"
        strategy_ids = [s.get("strategy_id") for s in strategies]
        assert "crypto_sniper" in strategy_ids, f"crypto_sniper not in strategies: {strategy_ids}"
        print(f"PASS: Status shows crypto_sniper in strategies list")
    
    def test_config_returns_200(self):
        """GET /api/config returns 200"""
        response = requests.get(f"{BASE_URL}/api/config")
        assert response.status_code == 200
        print("PASS: GET /api/config returned 200")
    
    def test_config_shows_crypto_sniper(self):
        """Config shows crypto_sniper strategy"""
        response = requests.get(f"{BASE_URL}/api/config")
        data = response.json()
        assert "strategies" in data
        assert "crypto_sniper" in data["strategies"]
        print("PASS: Config shows crypto_sniper strategy")
    
    def test_health_returns_200(self):
        """GET /api/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("PASS: GET /api/health returned healthy")


# ======================= ARB ENDPOINTS (REGRESSION) =======================

class TestArbEndpointsRegression:
    """Verify existing arb endpoints still work"""
    
    def test_arb_opportunities_returns_200(self):
        """GET /api/strategies/arb/opportunities returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/opportunities")
        assert response.status_code == 200
        data = response.json()
        assert "tradable" in data
        assert "rejected" in data
        print("PASS: GET /api/strategies/arb/opportunities returned 200")
    
    def test_arb_health_returns_200(self):
        """GET /api/strategies/arb/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/health")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/arb/health returned 200")
    
    def test_arb_executions_returns_200(self):
        """GET /api/strategies/arb/executions returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/arb/executions")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "completed" in data
        print("PASS: GET /api/strategies/arb/executions returned 200")


# ======================= ENGINE CONTROL TESTS =======================

class TestEngineWithSniper:
    """Test engine start/stop with both strategies registered"""
    
    def test_engine_start_registers_both_strategies(self):
        """Engine start shows both ArbScanner and CryptoSniper"""
        # Check current state
        health_response = requests.get(f"{BASE_URL}/api/health")
        initial_status = health_response.json().get("engine", "stopped")
        
        if initial_status == "running":
            # Stop first
            requests.post(f"{BASE_URL}/api/engine/stop")
            time.sleep(1)
        
        # Start engine
        response = requests.post(f"{BASE_URL}/api/engine/start")
        assert response.status_code == 200
        print("PASS: Engine started")
        
        # Verify status shows both strategies
        time.sleep(1)
        status_response = requests.get(f"{BASE_URL}/api/status")
        data = status_response.json()
        
        # strategies is a list
        strategies = data.get("strategies", [])
        strategy_ids = [s.get("strategy_id") for s in strategies]
        assert "arb_scanner" in strategy_ids, f"arb_scanner not found in {strategy_ids}"
        assert "crypto_sniper" in strategy_ids, f"crypto_sniper not found in {strategy_ids}"
        print(f"PASS: Both strategies registered: {strategy_ids}")
    
    def test_engine_status_shows_running(self):
        """After start, engine status is running"""
        health_response = requests.get(f"{BASE_URL}/api/health")
        data = health_response.json()
        assert data["engine"] == "running"
        print("PASS: Engine status is running")


# ======================= FULL PIPELINE TEST =======================

class TestFullPipeline:
    """Test inject -> classify -> signal -> execute pipeline"""
    
    def test_inject_and_check_signals(self):
        """Inject a crypto market and verify signals are generated"""
        # Ensure engine is running
        health = requests.get(f"{BASE_URL}/api/health").json()
        if health.get("engine") != "running":
            requests.post(f"{BASE_URL}/api/engine/start")
            time.sleep(2)
        
        # Check price buffer has samples (need 30 for volatility)
        sniper_health = requests.get(f"{BASE_URL}/api/strategies/sniper/health").json()
        btc_samples = sniper_health.get("price_buffer_sizes", {}).get("BTC", 0)
        print(f"INFO: BTC price buffer has {btc_samples} samples")
        
        if btc_samples < 30:
            print(f"SKIP: Need at least 30 samples for volatility, have {btc_samples}")
            pytest.skip("Insufficient volatility data - need 30+ samples")
        
        # Inject crypto market
        inject_response = requests.post(f"{BASE_URL}/api/test/inject-crypto-market")
        assert inject_response.status_code == 200
        inject_data = inject_response.json()
        
        assert inject_data.get("status") == "injected"
        assert "condition_id" in inject_data
        assert "question" in inject_data
        print(f"PASS: Injected market - {inject_data['question']}")
        
        # Wait for classification refresh
        print("INFO: Waiting 35s for classification refresh...")
        time.sleep(35)
        
        # Check signals
        signals_response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        signals_data = signals_response.json()
        
        # Look for our injected market
        condition_id = inject_data["condition_id"]
        found_signal = None
        for sig in signals_data.get("tradable", []) + signals_data.get("rejected", []):
            if sig.get("condition_id") == condition_id:
                found_signal = sig
                break
        
        assert found_signal is not None, f"Injected market {condition_id} not found in signals"
        print(f"PASS: Found signal for injected market - tradable={found_signal.get('is_tradable')}, edge={found_signal.get('edge_bps')}bps")
        
        # Check executions if signal was tradable
        if found_signal.get("is_tradable"):
            exec_response = requests.get(f"{BASE_URL}/api/strategies/sniper/executions")
            exec_data = exec_response.json()
            
            # Look for execution
            found_exec = None
            for ex in exec_data.get("active", []) + exec_data.get("completed", []):
                if ex.get("condition_id") == condition_id:
                    found_exec = ex
                    break
            
            if found_exec:
                print(f"PASS: Found execution - status={found_exec.get('status')}, side={found_exec.get('side')}")
            else:
                print("INFO: No execution found yet (may need more time)")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
