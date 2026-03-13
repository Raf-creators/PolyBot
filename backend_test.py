#!/usr/bin/env python3
"""
Comprehensive backend API tests for Polymarket Edge OS Phase 1
Tests all 18 requirements from the review request
"""
import requests
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

class PolymarketEdgeOSApiTester:
    def __init__(self, base_url: str = "https://edge-trading-hub-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
    def run_test(self, name: str, method: str, endpoint: str, expected_status, 
                 data: Optional[Dict] = None, validate_response: Optional[callable] = None) -> tuple:
        """Run a single API test with validation"""
        url = f"{self.base_url}/api{endpoint}"
        self.tests_run += 1
        
        print(f"\n🔍 Test {self.tests_run}: {name}")
        print(f"   {method} {url}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, timeout=10)
            elif method == 'POST':
                response = self.session.post(url, json=data, timeout=10)
            elif method == 'PUT':
                response = self.session.put(url, json=data, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Handle expected_status as either int or list of valid codes
            if isinstance(expected_status, (list, tuple)):
                success = response.status_code in expected_status
            else:
                success = response.status_code == expected_status
            
            if success:
                try:
                    response_data = response.json() if response.text else {}
                except:
                    response_data = {}
                
                # Additional validation if provided
                if validate_response and success:
                    validation_result = validate_response(response_data)
                    if not validation_result:
                        success = False
                        print(f"   ❌ Response validation failed")
                    else:
                        print(f"   ✅ Passed - Status: {response.status_code}, Response validated")
                else:
                    print(f"   ✅ Passed - Status: {response.status_code}")
                    
                if success:
                    self.tests_passed += 1
                else:
                    self.failed_tests.append(f"{name}: Response validation failed")
                    
                return success, response_data
            else:
                expected_str = f"{expected_status}" if isinstance(expected_status, int) else f"one of {expected_status}"
                print(f"   ❌ Failed - Expected {expected_str}, got {response.status_code}")
                print(f"   Response: {response.text[:200]}...")
                self.failed_tests.append(f"{name}: Expected {expected_str}, got {response.status_code}")
                return False, {}
                
        except Exception as e:
            print(f"   ❌ Failed - Error: {str(e)}")
            self.failed_tests.append(f"{name}: Exception - {str(e)}")
            return False, {}

    def test_basic_endpoints(self):
        """Test basic info and health endpoints"""
        print("\n" + "="*60)
        print("TESTING BASIC ENDPOINTS")
        print("="*60)
        
        # Test 1: GET /api/ returns name, version, status
        success, data = self.run_test(
            "Root endpoint info",
            "GET", "/", 200,
            validate_response=lambda r: all(k in r for k in ["name", "version", "status"])
        )
        
        # Test 2: GET /api/health returns engine status and mode
        success, data = self.run_test(
            "Health check",
            "GET", "/health", 200,
            validate_response=lambda r: all(k in r for k in ["status", "engine", "mode"])
        )
        
        # Test 3: GET /api/status returns full engine state snapshot
        success, data = self.run_test(
            "Engine status snapshot",
            "GET", "/status", 200,
            validate_response=lambda r: all(k in r for k in ["status", "mode", "uptime_seconds", "components", "strategies", "risk", "stats"])
        )

    def test_engine_lifecycle(self):
        """Test engine start/stop lifecycle"""
        print("\n" + "="*60)
        print("TESTING ENGINE LIFECYCLE")
        print("="*60)
        
        # Ensure engine is stopped first
        self.run_test("Stop engine (if running)", "POST", "/engine/stop", [200, 400])
        
        # Test 4: POST /api/engine/start starts the engine
        success, data = self.run_test(
            "Start engine",
            "POST", "/engine/start", 200,
            validate_response=lambda r: r.get("status") == "started"
        )
        
        # Verify engine is running
        success, status_data = self.run_test(
            "Verify engine running",
            "GET", "/status", 200,
            validate_response=lambda r: r.get("status") == "running"
        )
        
        # Test 5: POST /api/engine/start when already running returns 400
        success, data = self.run_test(
            "Start engine when already running",
            "POST", "/engine/start", 400
        )
        
        # Test 6: POST /api/engine/stop stops the engine
        success, data = self.run_test(
            "Stop engine",
            "POST", "/engine/stop", 200,
            validate_response=lambda r: r.get("status") == "stopped"
        )
        
        # Test 7: POST /api/engine/stop when already stopped returns 400
        success, data = self.run_test(
            "Stop engine when already stopped",
            "POST", "/engine/stop", 400
        )

    def test_configuration(self):
        """Test configuration endpoints"""
        print("\n" + "="*60)
        print("TESTING CONFIGURATION")
        print("="*60)
        
        # Test 8: GET /api/config returns trading_mode, risk config, strategies, credentials_present
        success, config_data = self.run_test(
            "Get configuration",
            "GET", "/config", 200,
            validate_response=lambda r: all(k in r for k in ["trading_mode", "risk", "strategies", "credentials_present"])
        )
        
        if success:
            print(f"   Trading mode: {config_data.get('trading_mode')}")
            print(f"   Credentials present: {config_data.get('credentials_present')}")
        
        # Test 9: PUT /api/config updates risk config values
        new_risk_config = {
            "risk": {
                "max_daily_loss": 150.0,
                "max_loss_per_strategy": 75.0,
                "max_position_size": 30.0,
                "max_market_exposure": 60.0,
                "max_concurrent_positions": 15,
                "max_order_size": 15.0,
                "kill_switch_active": False
            }
        }
        success, data = self.run_test(
            "Update risk configuration",
            "PUT", "/config", 200,
            data=new_risk_config,
            validate_response=lambda r: r.get("status") == "updated"
        )
        
        # Test 10: PUT /api/config with trading_mode='live' when no credentials returns 400
        live_mode_config = {"trading_mode": "live"}
        success, data = self.run_test(
            "Set live mode without credentials",
            "PUT", "/config", 400,
            data=live_mode_config
        )

    def test_risk_controls(self):
        """Test risk management endpoints"""
        print("\n" + "="*60)
        print("TESTING RISK CONTROLS")
        print("="*60)
        
        # Test 11: POST /api/risk/kill-switch/activate
        success, data = self.run_test(
            "Activate kill switch",
            "POST", "/risk/kill-switch/activate", 200,
            validate_response=lambda r: r.get("status") == "kill_switch_activated"
        )
        
        # Test 12: POST /api/risk/kill-switch/deactivate
        success, data = self.run_test(
            "Deactivate kill switch",
            "POST", "/risk/kill-switch/deactivate", 200,
            validate_response=lambda r: r.get("status") == "kill_switch_deactivated"
        )

    def test_paper_trading_pipeline(self):
        """Test paper trading end-to-end pipeline"""
        print("\n" + "="*60)
        print("TESTING PAPER TRADING PIPELINE")
        print("="*60)
        
        # Start engine for paper trading tests
        print("Starting engine for paper trading tests...")
        self.run_test("Start engine", "POST", "/engine/start", [200, 400])
        
        # Wait a moment for engine to fully initialize
        time.sleep(1)
        
        # Test 13: POST /api/test/paper-order submits order through full pipeline
        success, order_data = self.run_test(
            "Submit paper order through pipeline",
            "POST", "/test/paper-order", 200,
            validate_response=lambda r: all(k in r for k in ["status", "order_id"]) and r.get("status") == "submitted"
        )
        
        if success:
            order_id = order_data.get("order_id")
            print(f"   Order submitted with ID: {order_id}")
            
            # Give the pipeline time to process the order
            time.sleep(2)
            
            # Test 15: GET /api/trades returns trade records after paper order
            success, trades = self.run_test(
                "Get trades after paper order",
                "GET", "/trades", 200,
                validate_response=lambda r: isinstance(r, list)
            )
            
            if success and len(trades) > 0:
                print(f"   Found {len(trades)} trade record(s)")
                
            # Test 16: GET /api/positions returns position state after paper order
            success, positions = self.run_test(
                "Get positions after paper order",
                "GET", "/positions", 200,
                validate_response=lambda r: isinstance(r, list)
            )
            
            if success:
                print(f"   Found {len(positions)} position(s)")
                
            # Test 17: GET /api/orders returns order records after paper order
            success, orders = self.run_test(
                "Get orders after paper order",
                "GET", "/orders", 200,
                validate_response=lambda r: isinstance(r, list)
            )
            
            if success and len(orders) > 0:
                print(f"   Found {len(orders)} order record(s)")
                order_statuses = [o.get("status") for o in orders]
                print(f"   Order statuses: {set(order_statuses)}")

    def test_kill_switch_blocks_orders(self):
        """Test that kill switch blocks paper orders when active"""
        print("\n" + "="*60)  
        print("TESTING KILL SWITCH BLOCKING")
        print("="*60)
        
        # Activate kill switch
        self.run_test("Activate kill switch", "POST", "/risk/kill-switch/activate", 200)
        
        # Test 14: Kill switch blocks paper orders when active
        success, data = self.run_test(
            "Paper order blocked by kill switch",
            "POST", "/test/paper-order", 400  # Should be blocked
        )
        
        # Deactivate kill switch for clean state
        self.run_test("Deactivate kill switch", "POST", "/risk/kill-switch/deactivate", 200)

    def test_markets_endpoint(self):
        """Test markets endpoint"""
        print("\n" + "="*60)
        print("TESTING MARKETS ENDPOINT")
        print("="*60)
        
        # Test 18: GET /api/markets returns empty list (no markets loaded in Phase 1)
        success, markets = self.run_test(
            "Get markets (should be empty in Phase 1)",
            "GET", "/markets", 200,
            validate_response=lambda r: isinstance(r, list) and len(r) == 0
        )
        
        if success:
            print(f"   Markets list is empty as expected for Phase 1: {markets}")

    def run_all_tests(self):
        """Execute the complete test suite"""
        start_time = time.time()
        
        print("🚀 POLYMARKET EDGE OS PHASE 1 API TEST SUITE")
        print("="*80)
        print(f"Base URL: {self.base_url}")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Run test suites in logical order
            self.test_basic_endpoints()
            self.test_engine_lifecycle()  
            self.test_configuration()
            self.test_risk_controls()
            self.test_paper_trading_pipeline()
            self.test_kill_switch_blocks_orders()
            self.test_markets_endpoint()
            
        except Exception as e:
            print(f"\n💥 Test suite failed with exception: {e}")
            return 1
            
        # Final results
        duration = time.time() - start_time
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print("\n" + "="*80)
        print("📊 FINAL TEST RESULTS")
        print("="*80)
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {len(self.failed_tests)}")
        print(f"Success rate: {success_rate:.1f}%")
        print(f"Duration: {duration:.2f}s")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS ({len(self.failed_tests)}):")
            for i, failure in enumerate(self.failed_tests, 1):
                print(f"   {i}. {failure}")
        else:
            print(f"\n✅ ALL TESTS PASSED!")
            
        return 0 if len(self.failed_tests) == 0 else 1

def main():
    """Main test execution"""
    import os
    
    # Use environment URL if available, fallback to default
    base_url = os.getenv('BACKEND_URL', 'https://edge-trading-hub-1.preview.emergentagent.com')
    
    tester = PolymarketEdgeOSApiTester(base_url)
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())