"""
Iteration 46: Weather V2 Incremental Upgrade Tests

Features tested:
1. Explanation layer on weather signals (forecast_summary, model_probability, edge, confidence, rejection_reason, thesis)
2. Signal Quality Score (quality_score field combining edge, confidence, liquidity)
3. Best signal this scan (best_signal_this_scan in /api/strategies/weather/health)
4. Position breakdown endpoint (/api/positions/weather/breakdown)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestWeatherSignalsExplanationLayer:
    """Test explanation and quality_score fields on weather signals"""
    
    def test_weather_signals_endpoint_returns_200(self):
        """GET /api/strategies/weather/signals returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/strategies/weather/signals returns 200")
    
    def test_weather_signals_structure(self):
        """Response has tradable, rejected, total_tradable, total_rejected"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        data = response.json()
        
        assert "tradable" in data, "Missing tradable field"
        assert "rejected" in data, "Missing rejected field"
        assert "total_tradable" in data, "Missing total_tradable field"
        assert "total_rejected" in data, "Missing total_rejected field"
        print(f"PASS: Signals structure correct - tradable: {data['total_tradable']}, rejected: {data['total_rejected']}")
    
    def test_tradable_signals_have_quality_score(self):
        """Tradable signals include quality_score field"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        data = response.json()
        
        tradable = data.get("tradable", [])
        rejected = data.get("rejected", [])
        all_signals = tradable + rejected
        
        if len(all_signals) > 0:
            signal = all_signals[0]
            assert "quality_score" in signal, f"Missing quality_score in signal. Keys: {signal.keys()}"
            assert isinstance(signal["quality_score"], (int, float)), "quality_score should be numeric"
            print(f"PASS: Signals have quality_score field (first signal: {signal['quality_score']})")
        else:
            # Check if scanner has run
            health_resp = requests.get(f"{BASE_URL}/api/strategies/weather/health")
            health = health_resp.json()
            if health.get("total_scans", 0) == 0:
                print("INFO: Scanner hasn't run yet - no signals to verify quality_score")
            else:
                pytest.skip("No signals after scanner ran - need active weather markets")
    
    def test_tradable_signals_have_explanation(self):
        """Tradable signals include explanation dict with required fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        data = response.json()
        
        tradable = data.get("tradable", [])
        if len(tradable) > 0:
            signal = tradable[0]
            assert "explanation" in signal, f"Missing explanation in tradable signal"
            exp = signal["explanation"]
            assert isinstance(exp, dict), "explanation should be a dict"
            
            # Tradable signals should have thesis
            assert "thesis" in exp, f"Missing thesis in explanation. Keys: {exp.keys()}"
            print(f"PASS: Tradable signal has explanation with thesis: {exp.get('thesis', '')[:80]}...")
        else:
            print("SKIP: No tradable signals to check thesis (signals exist but may be rejected due to thresholds)")
    
    def test_rejected_signals_have_explanation(self):
        """Rejected signals include explanation with rejection_reason and forecast_summary"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        data = response.json()
        
        rejected = data.get("rejected", [])
        if len(rejected) > 0:
            signal = rejected[0]
            assert "explanation" in signal, f"Missing explanation in rejected signal"
            exp = signal["explanation"]
            
            # Check required fields for rejected signals
            assert "rejection_reason" in exp or "rejection_reason" in signal, \
                f"Missing rejection_reason. Signal keys: {signal.keys()}, Explanation keys: {exp.keys()}"
            assert "forecast_summary" in exp, f"Missing forecast_summary in explanation. Keys: {exp.keys()}"
            
            # Also check rejection_reason at signal level
            assert "rejection_reason" in signal, "rejection_reason should also be at signal level"
            
            print(f"PASS: Rejected signal has explanation - reason: {signal.get('rejection_reason', '')[:50]}, forecast: {exp.get('forecast_summary', '')[:50]}")
        else:
            pytest.skip("No rejected signals to verify explanation")
    
    def test_explanation_structure_complete(self):
        """Explanation dict has required fields: market, location, contract_type, bucket"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        data = response.json()
        
        # Check any signal (tradable or rejected)
        all_signals = data.get("tradable", []) + data.get("rejected", [])
        if len(all_signals) > 0:
            signal = all_signals[0]
            exp = signal.get("explanation", {})
            
            required_fields = ["market", "location", "contract_type", "bucket"]
            for field in required_fields:
                assert field in exp, f"Missing {field} in explanation. Keys: {exp.keys()}"
            
            print(f"PASS: Explanation has all required fields: {required_fields}")
            print(f"  market: {exp.get('market', '')[:60]}...")
            print(f"  location: {exp.get('location')}")
            print(f"  contract_type: {exp.get('contract_type')}")
            print(f"  bucket: {exp.get('bucket')}")
        else:
            pytest.skip("No signals to verify explanation structure")


class TestWeatherHealthBestSignal:
    """Test best_signal_this_scan tracking in health endpoint"""
    
    def test_weather_health_returns_200(self):
        """GET /api/strategies/weather/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/weather/health returns 200")
    
    def test_health_has_best_signal_field(self):
        """Health response includes best_signal_this_scan field after scans run"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        
        # Field is only set after first scan loop runs
        total_scans = data.get("total_scans", 0)
        if total_scans > 0:
            # After scans run, best_signal_this_scan should be in _m
            assert "best_signal_this_scan" in data, f"Missing best_signal_this_scan after {total_scans} scans. Keys: {list(data.keys())[:20]}"
            print(f"PASS: best_signal_this_scan field present: {data['best_signal_this_scan']}")
        else:
            # Scanner hasn't completed a scan yet - field won't be present
            print(f"INFO: Scanner has not completed first scan yet (total_scans=0) - best_signal_this_scan not yet populated")
            # Verify the code structure is correct by checking that the running flag is set
            assert "running" in data, "Health should have running field"
            print(f"PASS: Scanner running={data.get('running')} - waiting for first scan to populate best_signal_this_scan")
    
    def test_best_signal_structure_when_present(self):
        """When best_signal_this_scan exists, it has required fields"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        data = response.json()
        
        best = data.get("best_signal_this_scan")
        if best is not None:
            required = ["station", "date", "bucket", "edge_bps", "quality_score"]
            for field in required:
                assert field in best, f"Missing {field} in best_signal_this_scan"
            
            # Optional but expected: thesis
            if "thesis" in best:
                print(f"PASS: best_signal_this_scan has thesis: {best['thesis'][:60]}...")
            
            print(f"PASS: best_signal_this_scan has required fields:")
            print(f"  station: {best['station']}, date: {best['date']}, bucket: {best['bucket']}")
            print(f"  edge_bps: {best['edge_bps']}, quality_score: {best['quality_score']}")
        else:
            print("INFO: No best_signal_this_scan (no tradable signals at current thresholds)")


class TestWeatherPositionBreakdown:
    """Test /api/positions/weather/breakdown endpoint"""
    
    def test_breakdown_endpoint_returns_200(self):
        """GET /api/positions/weather/breakdown returns 200"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/breakdown")
        assert response.status_code == 200
        print("PASS: GET /api/positions/weather/breakdown returns 200")
    
    def test_breakdown_structure(self):
        """Response has required fields: total_open, total_unrealized_pnl, by_resolution_date, etc."""
        response = requests.get(f"{BASE_URL}/api/positions/weather/breakdown")
        data = response.json()
        
        required = [
            "total_open", 
            "total_unrealized_pnl", 
            "by_resolution_date",
            "biggest_winners",
            "biggest_losers",
            "oldest_open",
            "stale_positions",
            "stale_list"
        ]
        
        for field in required:
            assert field in data, f"Missing {field} in breakdown response"
        
        print(f"PASS: Breakdown has all required fields")
        print(f"  total_open: {data['total_open']}")
        print(f"  total_unrealized_pnl: {data['total_unrealized_pnl']}")
        print(f"  stale_positions: {data['stale_positions']}")
    
    def test_by_resolution_date_structure(self):
        """by_resolution_date is a dict with date keys and count/pnl/capital values"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/breakdown")
        data = response.json()
        
        by_res = data.get("by_resolution_date", {})
        assert isinstance(by_res, dict), "by_resolution_date should be a dict"
        
        if len(by_res) > 0:
            date_key = list(by_res.keys())[0]
            entry = by_res[date_key]
            assert "count" in entry, f"Missing count in resolution entry"
            assert "unrealized_pnl" in entry, f"Missing unrealized_pnl in resolution entry"
            assert "capital" in entry, f"Missing capital in resolution entry"
            
            print(f"PASS: by_resolution_date structure correct")
            for date_key, entry in list(by_res.items())[:3]:
                print(f"  {date_key}: {entry['count']} positions, ${entry['capital']} capital, {entry['unrealized_pnl']} pnl")
        else:
            print("INFO: No resolution date breakdown (no open weather positions)")
    
    def test_winners_losers_arrays(self):
        """biggest_winners and biggest_losers are arrays with position data"""
        response = requests.get(f"{BASE_URL}/api/positions/weather/breakdown")
        data = response.json()
        
        assert isinstance(data.get("biggest_winners"), list), "biggest_winners should be list"
        assert isinstance(data.get("biggest_losers"), list), "biggest_losers should be list"
        assert isinstance(data.get("oldest_open"), list), "oldest_open should be list"
        
        winners = data.get("biggest_winners", [])
        if len(winners) > 0:
            pos = winners[0]
            # Check position has required display fields
            assert "unrealized_pnl" in pos, "Winner missing unrealized_pnl"
            print(f"PASS: biggest_winners has {len(winners)} positions")
            print(f"  Top winner: {pos.get('city', pos.get('market_question', '')[:30])} - {pos.get('unrealized_pnl')}")
        
        losers = data.get("biggest_losers", [])
        if len(losers) > 0:
            print(f"PASS: biggest_losers has {len(losers)} positions")


class TestExistingEndpointsStillWork:
    """Verify existing endpoints still function correctly"""
    
    def test_positions_by_strategy_returns_200(self):
        """GET /api/positions/by-strategy returns 200"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        print("PASS: GET /api/positions/by-strategy returns 200")
    
    def test_positions_by_strategy_has_weather(self):
        """Response has weather bucket with positions and summary"""
        response = requests.get(f"{BASE_URL}/api/positions/by-strategy")
        data = response.json()
        
        assert "positions" in data, "Missing positions"
        assert "summaries" in data, "Missing summaries"
        assert "weather" in data["positions"], "Missing weather in positions"
        assert "weather" in data["summaries"], "Missing weather in summaries"
        
        weather_sum = data["summaries"]["weather"]
        assert "open_positions" in weather_sum
        assert "unrealized_pnl" in weather_sum
        assert "realized_pnl" in weather_sum
        
        print(f"PASS: positions/by-strategy has weather data:")
        print(f"  open_positions: {weather_sum['open_positions']}")
        print(f"  unrealized_pnl: {weather_sum['unrealized_pnl']}")
        print(f"  realized_pnl: {weather_sum['realized_pnl']}")
    
    def test_sniper_signals_returns_200(self):
        """GET /api/strategies/sniper/signals returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/signals")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/sniper/signals returns 200")
    
    def test_sniper_health_returns_200(self):
        """GET /api/strategies/sniper/health returns 200"""
        response = requests.get(f"{BASE_URL}/api/strategies/sniper/health")
        assert response.status_code == 200
        print("PASS: GET /api/strategies/sniper/health returns 200")
    
    def test_analytics_strategy_attribution_returns_200(self):
        """GET /api/analytics/strategy-attribution returns 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/strategy-attribution")
        assert response.status_code == 200
        data = response.json()
        
        # Should have strategy buckets
        assert "weather" in data or "crypto" in data, f"Missing strategy keys. Keys: {data.keys()}"
        print("PASS: GET /api/analytics/strategy-attribution returns 200")
    
    def test_controls_returns_200(self):
        """GET /api/controls returns 200 with mode=paper"""
        response = requests.get(f"{BASE_URL}/api/controls")
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("mode") == "paper", f"Expected paper mode, got {data.get('mode')}"
        print("PASS: GET /api/controls returns 200, mode=paper")


class TestQualityScoreComputation:
    """Verify quality_score is computed correctly (0-1 range, combines edge/conf/liquidity)"""
    
    def test_quality_score_range(self):
        """quality_score should be between 0 and 1"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        data = response.json()
        
        all_signals = data.get("tradable", []) + data.get("rejected", [])
        if len(all_signals) > 0:
            scores = [s.get("quality_score", 0) for s in all_signals]
            for score in scores:
                assert 0 <= score <= 1, f"quality_score {score} out of range [0,1]"
            
            print(f"PASS: All {len(scores)} quality_scores in range [0,1]")
            print(f"  min: {min(scores):.4f}, max: {max(scores):.4f}")
        else:
            pytest.skip("No signals to check quality_score range")
    
    def test_best_signal_has_highest_quality(self):
        """best_signal_this_scan should have highest quality_score among tradable"""
        response = requests.get(f"{BASE_URL}/api/strategies/weather/signals")
        sig_data = response.json()
        
        response = requests.get(f"{BASE_URL}/api/strategies/weather/health")
        health_data = response.json()
        
        tradable = sig_data.get("tradable", [])
        best = health_data.get("best_signal_this_scan")
        
        if best is not None and len(tradable) > 1:
            # Find max quality among tradable
            max_quality = max(s.get("quality_score", 0) for s in tradable)
            assert best["quality_score"] == max_quality or abs(best["quality_score"] - max_quality) < 0.001, \
                f"Best signal quality {best['quality_score']} != max tradable quality {max_quality}"
            print(f"PASS: best_signal_this_scan has highest quality_score: {best['quality_score']}")
        else:
            print("INFO: Cannot verify best signal ranking (0-1 tradable signals)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
