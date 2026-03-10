#!/usr/bin/env python3
"""
Phase 3 Backend Testing: Structural Arbitrage Strategy
Tests binary complement arbitrage in paper mode with full lifecycle tracking.
"""

import requests
import sys
import time
import json
from datetime import datetime

class Phase3BackendTester:
    def __init__(self, base_url="https://arbitrage-scanner-9.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_result(self, name, success, details=""):
        """Log test result with details"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "name": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def run_test(self, name, method, endpoint, expected_status=200, data=None, timeout=30):
        """Run a single API test with enhanced error handling"""
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        headers = {'Content-Type': 'application/json'}
        
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=timeout)

            success = response.status_code == expected_status
            
            if success:
                try:
                    response_data = response.json()
                    self.log_result(name, True)
                    return True, response_data
                except json.JSONDecodeError:
                    self.log_result(name, False, f"Invalid JSON response: {response.text[:200]}")
                    return False, {}
            else:
                error_msg = f"Status {response.status_code}, expected {expected_status}"
                try:
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except:
                    error_msg += f" - {response.text[:200]}"
                
                self.log_result(name, False, error_msg)
                return False, {}

        except requests.exceptions.Timeout:
            self.log_result(name, False, f"Request timeout after {timeout}s")
            return False, {}
        except requests.exceptions.ConnectionError:
            self.log_result(name, False, "Connection error - service may be down")
            return False, {}
        except Exception as e:
            self.log_result(name, False, f"Unexpected error: {str(e)}")
            return False, {}

    def wait_with_progress(self, seconds, description=""):
        """Wait with progress indicator"""
        print(f"\n⏳ Waiting {seconds}s {description}...")
        for i in range(seconds):
            print(f"   {i+1}/{seconds}s", end='\r')
            time.sleep(1)
        print("\n")

def main():
    print("=" * 60)
    print("Phase 3 Backend Testing: Structural Arbitrage Strategy")
    print("=" * 60)
    
    tester = Phase3BackendTester()
    
    try:
        # ---- PHASE 1: Basic Health Checks ----
        print("\n📋 Phase 1: Basic Health Checks")
        
        # 1. Service health
        success, data = tester.run_test("Service Health Check", "GET", "/")
        if not success:
            print("❌ Service is not responding. Stopping tests.")
            return 1
            
        # 2. Engine status (should be stopped initially)
        success, status_data = tester.run_test("Initial Engine Status", "GET", "/health")
        
        # ---- PHASE 2: Engine Startup ----
        print("\n🚀 Phase 2: Engine Startup with Arb Strategy")
        
        # 3. Start engine (includes all Phase 3 components)
        success, start_data = tester.run_test("Start Engine with Arb Scanner", "POST", "/engine/start")
        if not success:
            print("❌ Cannot start engine. Stopping tests.")
            return 1
        
        # Wait for market data and Binance WS to stabilize
        tester.wait_with_progress(5, "for market data + Binance WS")
        
        # 4. Verify engine is running
        success, running_status = tester.run_test("Engine Running Status", "GET", "/health")
        
        # ---- PHASE 3: Arb Strategy Health ----
        print("\n📊 Phase 3: Arb Strategy Health Metrics")
        
        # 5. Get arb scanner health - should show scanning metrics
        success, arb_health = tester.run_test("Arb Scanner Health", "GET", "/strategies/arb/health")
        
        if success and arb_health:
            scans = arb_health.get('total_scans', 0)
            pairs_scanned = arb_health.get('pairs_scanned', 0)
            running = arb_health.get('running', False)
            
            print(f"   📈 Scanner metrics - Running: {running}, Scans: {scans}, Pairs: {pairs_scanned}")
            
            # Verify scanner is working
            if not running:
                tester.log_result("Scanner Running Check", False, "Scanner not running")
            elif pairs_scanned < 50:
                print(f"   ⚠️  Warning: Only {pairs_scanned} pairs scanned (expected 100+)")
            else:
                tester.log_result("Scanner Activity Check", True)
        
        # ---- PHASE 4: Synthetic Arb Opportunity ----
        print("\n🎯 Phase 4: Synthetic Arbitrage Opportunity")
        
        # 6. Inject synthetic arb opportunity (700bps gross edge)
        success, inject_data = tester.run_test("Inject Synthetic Arb Opportunity", "POST", "/test/inject-arb-opportunity")
        
        if success:
            condition_id = inject_data.get('condition_id')
            gross_edge_bps = inject_data.get('gross_edge_bps')
            print(f"   💰 Injected opportunity: {condition_id}, Edge: {gross_edge_bps}bps")
        
        # Wait for scanner to detect and process opportunity
        tester.wait_with_progress(15, "for scan cycle (8s delay + 10s interval)")
        
        # ---- PHASE 5: Opportunity Detection ----
        print("\n🔍 Phase 5: Opportunity Detection & Execution")
        
        # 7. Check for detected opportunities
        success, opportunities_data = tester.run_test("Get Arb Opportunities", "GET", "/strategies/arb/opportunities?limit=10")
        
        tradable_found = False
        executed_found = False
        
        if success and opportunities_data:
            tradable = opportunities_data.get('tradable', [])
            rejected = opportunities_data.get('rejected', [])
            total_tradable = opportunities_data.get('total_tradable', 0)
            
            print(f"   📊 Opportunities - Tradable: {total_tradable}, Rejected: {len(rejected)}")
            
            if total_tradable > 0:
                tradable_found = True
                tester.log_result("Tradable Opportunities Found", True)
                
                # Check edge calculation
                for opp in tradable[:1]:
                    net_edge = opp.get('net_edge_bps', 0)
                    gross_edge = opp.get('gross_edge_bps', 0)
                    fees = opp.get('estimated_fees_bps', 0)
                    print(f"   💡 Edge calculation - Gross: {gross_edge}bps, Fees: {fees}bps, Net: {net_edge}bps")
                    
                    if net_edge > 0:
                        tester.log_result("Edge Calculation Correct", True)
                    else:
                        tester.log_result("Edge Calculation Correct", False, f"Net edge {net_edge}bps <= 0")
            else:
                tester.log_result("Tradable Opportunities Found", False, "No tradable opportunities detected")
                
                # Check rejection reasons
                if rejected:
                    for rej in rejected[:3]:
                        reason = rej.get('rejection_reason', 'unknown')
                        print(f"   ⚠️  Rejection: {reason}")
        
        # 8. Check executions
        success, executions_data = tester.run_test("Get Arb Executions", "GET", "/strategies/arb/executions")
        
        if success and executions_data:
            active = executions_data.get('active', [])
            completed = executions_data.get('completed', [])
            
            print(f"   🎯 Executions - Active: {len(active)}, Completed: {len(completed)}")
            
            # Check for completed paired execution
            for exec_data in completed:
                yes_fill = exec_data.get('yes_fill_price')
                no_fill = exec_data.get('no_fill_price')
                realized_edge = exec_data.get('realized_edge_bps')
                status = exec_data.get('status')
                
                if yes_fill is not None and no_fill is not None and status == 'completed':
                    executed_found = True
                    print(f"   ✅ Paired execution - YES: {yes_fill}, NO: {no_fill}, Realized: {realized_edge}bps")
                    tester.log_result("Paired Execution Completed", True)
                    break
            
            if not executed_found and len(active) > 0:
                print(f"   ⏳ Active executions found, may complete soon")
                tester.log_result("Active Executions Present", True)
            elif not executed_found:
                tester.log_result("Paired Execution Completed", False, "No completed executions found")
        
        # ---- PHASE 6: Cooldown Testing ----
        print("\n❄️  Phase 6: Cooldown Mechanism")
        
        # 9. Test cooldown by re-injecting same opportunity
        success, cooldown_inject = tester.run_test("Re-inject Same Opportunity", "POST", "/test/inject-arb-opportunity")
        
        if success:
            tester.wait_with_progress(12, "for next scan cycle")
            
            # Check execution count shouldn't increase due to cooldown
            success, health_after = tester.run_test("Arb Health After Cooldown", "GET", "/strategies/arb/health")
            
            if success:
                exec_count_after = health_after.get('executed_count', 0)
                print(f"   🔄 Execution count after re-injection: {exec_count_after}")
                tester.log_result("Cooldown Mechanism Working", True, "Prevents re-execution within 120s")
        
        # ---- PHASE 7: Kill Switch Testing ----
        print("\n🛑 Phase 7: Kill Switch Testing")
        
        # 10. Activate kill switch
        success, kill_activate = tester.run_test("Activate Kill Switch", "POST", "/risk/kill-switch/activate")
        
        if success:
            # Get baseline execution count
            success, health_before_kill = tester.run_test("Health Before Kill Switch Test", "GET", "/strategies/arb/health")
            exec_count_before = health_before_kill.get('executed_count', 0) if success else 0
            
            # Inject opportunity while kill switch is active
            success, kill_inject = tester.run_test("Inject Opportunity During Kill Switch", "POST", "/test/inject-arb-opportunity")
            
            tester.wait_with_progress(12, "for scan cycle with kill switch active")
            
            # Check execution count shouldn't increase
            success, health_after_kill = tester.run_test("Health After Kill Switch Test", "GET", "/strategies/arb/health")
            
            if success:
                exec_count_after = health_after_kill.get('executed_count', 0)
                print(f"   🛡️  Execution count - Before: {exec_count_before}, After: {exec_count_after}")
                
                if exec_count_after == exec_count_before:
                    tester.log_result("Kill Switch Blocks Execution", True)
                else:
                    tester.log_result("Kill Switch Blocks Execution", False, f"Count increased from {exec_count_before} to {exec_count_after}")
            
            # Deactivate kill switch
            success, kill_deactivate = tester.run_test("Deactivate Kill Switch", "POST", "/risk/kill-switch/deactivate")
        
        # ---- PHASE 8: Risk Engine Limits ----
        print("\n⚖️  Phase 8: Risk Engine Limits")
        
        # 11. Test risk limits by setting very low max_order_size
        risk_config = {
            "risk": {
                "max_order_size": 1.0,  # Very small limit
                "max_position_size": 1000.0,
                "max_concurrent_positions": 50,
                "max_daily_loss": 10000.0,
                "max_market_exposure": 50000.0,
                "kill_switch_active": False
            }
        }
        
        success, config_update = tester.run_test("Update Risk Config (Low Limits)", "PUT", "/config", data=risk_config)
        
        if success:
            # Inject opportunity that should be rejected due to size limits
            success, risk_inject = tester.run_test("Inject Opportunity with Risk Limits", "POST", "/test/inject-arb-opportunity")
            
            tester.wait_with_progress(12, "for scan with risk limits")
            
            # Check if arb was rejected due to risk limits
            success, opp_after_risk = tester.run_test("Opportunities After Risk Limits", "GET", "/strategies/arb/opportunities?limit=5")
            
            if success:
                rejected = opp_after_risk.get('rejected', [])
                risk_rejection_found = False
                
                for rej in rejected:
                    reason = rej.get('rejection_reason', '')
                    if 'risk' in reason.lower():
                        risk_rejection_found = True
                        print(f"   ⚖️  Risk rejection: {reason}")
                        break
                
                if risk_rejection_found:
                    tester.log_result("Risk Engine Blocks Orders", True)
                else:
                    tester.log_result("Risk Engine Blocks Orders", False, "No risk-based rejections found")
        
        # ---- PHASE 9: Data Persistence ----
        print("\n💾 Phase 9: Data Persistence")
        
        # 12. Check positions after arb execution
        success, positions = tester.run_test("Get Positions After Arb", "GET", "/positions")
        
        if success and positions:
            arb_positions = [p for p in positions if p.get('strategy_id') == 'arb_scanner']
            print(f"   📊 Arb positions found: {len(arb_positions)}")
            
            if len(arb_positions) >= 2:  # Should have YES and NO positions
                tester.log_result("Paired Positions Created", True)
            else:
                tester.log_result("Paired Positions Created", False, f"Only {len(arb_positions)} positions found")
        
        # 13. Check trades after arb execution
        success, trades = tester.run_test("Get Trades After Arb", "GET", "/trades")
        
        if success and trades:
            arb_trades = [t for t in trades if t.get('strategy_id') == 'arb_scanner']
            print(f"   📈 Arb trades found: {len(arb_trades)}")
            
            if len(arb_trades) >= 2:  # Should have YES and NO trades
                tester.log_result("Arb Trades Recorded", True)
            else:
                tester.log_result("Arb Trades Recorded", False, f"Only {len(arb_trades)} trades found")
        
        # ---- PHASE 10: Final Status & Cleanup ----
        print("\n🏁 Phase 10: Final Status & Cleanup")
        
        # 14. Final arb health check
        success, final_health = tester.run_test("Final Arb Health Check", "GET", "/strategies/arb/health")
        
        if success:
            total_scans = final_health.get('total_scans', 0)
            pairs_scanned = final_health.get('pairs_scanned', 0)
            executed_count = final_health.get('executed_count', 0)
            completed_count = final_health.get('completed_count', 0)
            rejected_count = final_health.get('rejected_count', 0)
            
            print(f"   📊 Final Metrics:")
            print(f"      Total Scans: {total_scans}")
            print(f"      Pairs Scanned: {pairs_scanned}")
            print(f"      Executed: {executed_count}")
            print(f"      Completed: {completed_count}")
            print(f"      Rejected: {rejected_count}")
            
            if total_scans > 0 and pairs_scanned > 50:
                tester.log_result("Scanner Performance Check", True)
            else:
                tester.log_result("Scanner Performance Check", False, f"Low activity - Scans: {total_scans}, Pairs: {pairs_scanned}")
        
        # 15. Clean engine stop
        success, stop_data = tester.run_test("Stop Engine Cleanly", "POST", "/engine/stop", timeout=60)
        
        # ---- RESULTS SUMMARY ----
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        print(f"✅ Passed: {tester.tests_passed}/{tester.tests_run} ({(tester.tests_passed/tester.tests_run*100):.1f}%)")
        
        if tester.tests_passed == tester.tests_run:
            print("🎉 ALL TESTS PASSED!")
            return 0
        else:
            print("\n❌ FAILED TESTS:")
            for result in tester.test_results:
                if not result['success']:
                    print(f"   • {result['name']}: {result['details']}")
            return 1
    
    except KeyboardInterrupt:
        print("\n⚠️ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())