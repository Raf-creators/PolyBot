#!/usr/bin/env python3
"""
Comprehensive backend API tests for Polymarket Edge OS Phase 2
Tests all Phase 2 requirements with market data, price feeds, risk engine, paper execution
"""
import requests
import asyncio
import websockets
import json
import sys
import time
from datetime import datetime

class PolymarketEngineTest:
    def __init__(self, base_url="https://arbitrage-scanner-9.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def run_test(self, name, method, endpoint, expected_status, data=None, timeout=10):
        """Run a single API test with detailed logging"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        print(f"   URL: {method} {url}")
        
        try:
            start_time = time.time()
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=timeout)
            
            duration = time.time() - start_time
            
            # Check status code
            success = response.status_code == expected_status
            
            result = {
                'test_name': name,
                'method': method,
                'endpoint': endpoint,
                'expected_status': expected_status,
                'actual_status': response.status_code,
                'duration_ms': round(duration * 1000, 2),
                'success': success,
                'response_size': len(response.text) if response.text else 0
            }

            if success:
                self.tests_passed += 1
                print(f"   ✅ PASS - Status: {response.status_code} ({duration*1000:.0f}ms)")
                
                # Parse and analyze response for key tests
                try:
                    resp_data = response.json()
                    result['response_data'] = resp_data
                    
                    # Add specific validations based on endpoint
                    if endpoint == 'api/':
                        if resp_data.get('name') == 'Polymarket Edge OS':
                            print(f"      ✓ Correct service name")
                        if resp_data.get('status') == 'online':
                            print(f"      ✓ Status online")
                            
                    elif endpoint == 'api/health':
                        print(f"      Engine: {resp_data.get('engine', 'N/A')}")
                        print(f"      Mode: {resp_data.get('mode', 'N/A')}")
                        
                    elif endpoint == 'api/status':
                        stats = resp_data.get('stats', {})
                        print(f"      Markets tracked: {stats.get('markets_tracked', 0)}")
                        print(f"      Components: {len(resp_data.get('components', []))}")
                        spot_prices = stats.get('spot_prices', {})
                        if spot_prices:
                            print(f"      Spot prices: BTC=${spot_prices.get('BTC', 'N/A')}, ETH=${spot_prices.get('ETH', 'N/A')}")
                        health = stats.get('health', {})
                        print(f"      Health: market_stale={health.get('market_data_stale')}, binance={health.get('binance_connected')}")
                        
                    elif endpoint == 'api/markets':
                        print(f"      Markets returned: {len(resp_data) if isinstance(resp_data, list) else 0}")
                        if isinstance(resp_data, list) and resp_data:
                            top_market = resp_data[0]
                            print(f"      Top volume: {top_market.get('volume_24h', 0):.0f}")
                            
                    elif endpoint == 'api/markets/summary':
                        print(f"      Total markets: {resp_data.get('total_markets', 0)}")
                        top_markets = resp_data.get('top_by_volume', [])
                        print(f"      Top markets list: {len(top_markets)}")
                        
                    elif 'trades' in endpoint or 'positions' in endpoint or 'orders' in endpoint:
                        count = len(resp_data) if isinstance(resp_data, list) else 0
                        print(f"      Records returned: {count}")
                        
                except (ValueError, TypeError):
                    print(f"      Non-JSON response")
            else:
                print(f"   ❌ FAIL - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"      Error: {error_data}")
                    result['error_data'] = error_data
                except:
                    print(f"      Raw response: {response.text[:200]}...")
                    result['error_text'] = response.text[:200]

            self.test_results.append(result)
            return success, response.json() if success and response.text else {}

        except requests.exceptions.Timeout:
            print(f"   ❌ TIMEOUT - Request took longer than {timeout}s")
            self.test_results.append({**result, 'success': False, 'error': 'timeout'})
            return False, {}
        except Exception as e:
            print(f"   ❌ ERROR - {str(e)}")
            self.test_results.append({**result, 'success': False, 'error': str(e)})
            return False, {}

    async def test_websocket(self):
        """Test WebSocket streaming endpoint"""
        print(f"\n🔍 Test {self.tests_run + 1}: WebSocket streaming")
        self.tests_run += 1
        
        ws_url = f"wss://{self.base_url.split('://')[-1]}/api/ws"
        print(f"   URL: {ws_url}")
        
        try:
            async with websockets.connect(ws_url, ping_interval=20) as websocket:
                print(f"   ✅ WebSocket connected")
                
                # Wait for a message (should get state snapshots every 2 seconds)
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    print(f"   ✅ Received state snapshot")
                    print(f"      Status: {data.get('status', 'N/A')}")
                    print(f"      Mode: {data.get('mode', 'N/A')}")
                    self.tests_passed += 1
                    return True
                except asyncio.TimeoutError:
                    print(f"   ❌ No message received within 5 seconds")
                    return False
        except Exception as e:
            print(f"   ❌ WebSocket connection failed: {e}")
            return False

    def run_comprehensive_test(self):
        """Execute all Phase 2 tests in sequence"""
        print("🚀 Starting Polymarket Edge OS Phase 2 Backend Tests")
        print("=" * 60)
        
        # Phase 1: Basic Health Checks
        print("\n📋 PHASE 1: Basic Health & Status")
        self.run_test("Root endpoint", "GET", "api/", 200)
        self.run_test("Health check", "GET", "api/health", 200)
        
        # Phase 2: Engine Control
        print("\n📋 PHASE 2: Engine Lifecycle")
        success, _ = self.run_test("Start engine", "POST", "api/engine/start", 200)
        
        if success:
            print("\n⏱️  Waiting 5 seconds for engine components to initialize...")
            time.sleep(5)
            
            # Phase 3: Live Data Verification
            print("\n📋 PHASE 3: Live Data After Engine Start")
            self.run_test("Status with live data", "GET", "api/status", 200)
            self.run_test("Markets list", "GET", "api/markets", 200)
            self.run_test("Markets summary", "GET", "api/markets/summary", 200)
            self.run_test("Health feeds", "GET", "api/health/feeds", 200)
            
            # Phase 4: Trading Pipeline
            print("\n📋 PHASE 4: Paper Trading Pipeline")
            paper_success, _ = self.run_test("Submit paper order", "POST", "api/test/paper-order", 200)
            
            if paper_success:
                print("\n⏱️  Waiting 2 seconds for order processing...")
                time.sleep(2)
                
                self.run_test("Get trades", "GET", "api/trades", 200)
                self.run_test("Get positions", "GET", "api/positions", 200) 
                self.run_test("Get orders", "GET", "api/orders", 200)
            
            # Phase 5: Risk Controls
            print("\n📋 PHASE 5: Risk Management")
            
            # Test config update with risk limits
            risk_config = {
                "risk": {
                    "max_order_size": 1.0,
                    "max_position_size": 5.0,
                    "kill_switch_active": False
                }
            }
            self.run_test("Update risk config", "PUT", "api/config", 200, risk_config)
            
            # Test kill switch
            self.run_test("Activate kill switch", "POST", "api/risk/kill-switch/activate", 200)
            
            # Try to submit order with kill switch active (should fail)
            self.run_test("Order with kill switch active", "POST", "api/test/paper-order", 400)
            
            # Deactivate kill switch
            self.run_test("Deactivate kill switch", "POST", "api/risk/kill-switch/deactivate", 200)
            
            # Phase 6: WebSocket Streaming
            print("\n📋 PHASE 6: WebSocket Streaming")
            # Run WebSocket test
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            ws_success = loop.run_until_complete(self.test_websocket())
            if not ws_success:
                self.tests_run += 1  # WebSocket test was already counted in test_websocket
            
            # Phase 7: Engine Shutdown
            print("\n📋 PHASE 7: Engine Shutdown")
            self.run_test("Stop engine", "POST", "api/engine/stop", 200)
            
        else:
            print("\n⚠️  Engine start failed, skipping dependent tests")

        # Final Results
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        # Show failed tests
        failed_tests = [r for r in self.test_results if not r['success']]
        if failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for test in failed_tests:
                error_msg = test.get('error', f"HTTP {test.get('actual_status', 'N/A')}")
                print(f"   • {test['test_name']}: {error_msg}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = PolymarketEngineTest()
    success = tester.run_comprehensive_test()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())