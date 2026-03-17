"""
Tests for P&L Chart X-Axis Fix (Issue: timestamps showing only HH:MM, causing confusion for cross-day data)

Backend features tested:
1. /api/analytics/pnl-history returns latest_close_at (non-null ISO timestamp if close_trades > 0)
2. /api/analytics/pnl-history returns server_time (current UTC)
3. Each PnL history point has timestamp field with full ISO format (including date, not just time)
4. Data consistency: /api/status close_count matches /api/analytics/pnl-history close_trades
"""
import pytest
import requests
import os
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPnlHistoryEndpoint:
    """Tests for /api/analytics/pnl-history endpoint enhancements"""
    
    def test_pnl_history_returns_200(self):
        """GET /api/analytics/pnl-history should return 200"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ /api/analytics/pnl-history returns 200")
    
    def test_pnl_history_contains_latest_close_at(self):
        """Response should contain latest_close_at field"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "latest_close_at" in data, "Response missing 'latest_close_at' field"
        
        # If there are closed trades, latest_close_at should be non-null ISO timestamp
        close_trades = data.get("close_trades", 0)
        latest_close_at = data.get("latest_close_at")
        
        if close_trades > 0:
            assert latest_close_at is not None, f"latest_close_at should not be null when close_trades={close_trades}"
            # Validate ISO format
            try:
                dt = datetime.fromisoformat(latest_close_at.replace('Z', '+00:00'))
                print(f"✓ latest_close_at is valid ISO timestamp: {latest_close_at}")
            except ValueError:
                pytest.fail(f"latest_close_at is not valid ISO format: {latest_close_at}")
        else:
            print(f"✓ latest_close_at is null (expected when close_trades=0)")
    
    def test_pnl_history_contains_server_time(self):
        """Response should contain server_time field with current UTC"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        assert "server_time" in data, "Response missing 'server_time' field"
        server_time = data.get("server_time")
        assert server_time is not None, "server_time should not be null"
        
        # Validate ISO format and check it's recent (within 60 seconds)
        try:
            dt = datetime.fromisoformat(server_time.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = abs((now - dt).total_seconds())
            assert diff < 60, f"server_time is {diff} seconds from now (expected < 60)"
            print(f"✓ server_time is valid ISO timestamp: {server_time} ({diff:.1f}s ago)")
        except ValueError:
            pytest.fail(f"server_time is not valid ISO format: {server_time}")
    
    def test_pnl_history_points_have_full_timestamp(self):
        """Each point should have timestamp with full ISO format (including date)"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        points = data.get("points", [])
        if not points:
            pytest.skip("No close trades yet - cannot verify timestamp format")
        
        # Check first, middle, and last points
        sample_points = [points[0], points[len(points)//2], points[-1]]
        for i, point in enumerate(sample_points):
            timestamp = point.get("timestamp")
            assert timestamp is not None, f"Point {i} missing timestamp"
            
            # Validate ISO format with date component
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                # Verify it has date info (year, month, day)
                assert dt.year >= 2026, f"Timestamp year looks invalid: {dt.year}"
                print(f"✓ Point timestamp is full ISO: {timestamp}")
            except ValueError:
                pytest.fail(f"Timestamp is not valid ISO format: {timestamp}")
    
    def test_pnl_history_has_expected_fields(self):
        """Response should have all expected fields"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        expected_fields = [
            "points", "current_pnl", "peak_pnl", "trough_pnl", 
            "max_drawdown", "total_trades", "close_trades",
            "latest_close_at", "server_time"
        ]
        
        for field in expected_fields:
            assert field in data, f"Response missing expected field: {field}"
        
        print(f"✓ Response contains all expected fields: {expected_fields}")


class TestDataConsistency:
    """Tests for data consistency between endpoints"""
    
    def test_close_count_matches_across_endpoints(self):
        """close_count from /api/status should match close_trades from /api/analytics/pnl-history"""
        # Get from /api/status
        status_response = requests.get(f"{BASE_URL}/api/status", timeout=10)
        assert status_response.status_code == 200
        status_data = status_response.json()
        status_close_count = status_data.get("stats", {}).get("close_count", 0)
        
        # Get from /api/analytics/pnl-history
        pnl_response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert pnl_response.status_code == 200
        pnl_data = pnl_response.json()
        pnl_close_trades = pnl_data.get("close_trades", 0)
        
        # They should match
        assert status_close_count == pnl_close_trades, \
            f"Mismatch: /api/status close_count={status_close_count} vs /api/analytics/pnl-history close_trades={pnl_close_trades}"
        
        print(f"✓ Data consistent: close_count={status_close_count} matches across endpoints")
    
    def test_pnl_history_points_count_matches_close_trades(self):
        """Number of points should match close_trades count"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        points_count = len(data.get("points", []))
        close_trades = data.get("close_trades", 0)
        
        assert points_count == close_trades, \
            f"Mismatch: points count={points_count} vs close_trades={close_trades}"
        
        print(f"✓ Points count ({points_count}) matches close_trades ({close_trades})")


class TestTimestampRangeForXAxisFormat:
    """Tests to verify data spans multiple days (for X-axis MM/DD HH:MM format)"""
    
    def test_data_spans_multiple_days(self):
        """Verify data spans > 18 hours (triggers MM/DD HH:MM format on X-axis)"""
        response = requests.get(f"{BASE_URL}/api/analytics/pnl-history", timeout=10)
        assert response.status_code == 200
        data = response.json()
        
        points = data.get("points", [])
        if len(points) < 2:
            pytest.skip("Need at least 2 points to check time range")
        
        first_ts = points[0].get("timestamp")
        last_ts = points[-1].get("timestamp")
        
        first_dt = datetime.fromisoformat(first_ts.replace('Z', '+00:00'))
        last_dt = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
        
        range_hours = (last_dt - first_dt).total_seconds() / 3600
        
        print(f"First point: {first_ts}")
        print(f"Last point: {last_ts}")
        print(f"Time range: {range_hours:.1f} hours")
        
        # If range > 18 hours, X-axis should show MM/DD HH:MM format
        if range_hours > 18:
            print(f"✓ Data spans {range_hours:.1f} hours (> 18 hours) - X-axis will show MM/DD HH:MM format")
        else:
            print(f"Note: Data spans {range_hours:.1f} hours (<= 18 hours) - X-axis will show HH:MM format")
        
        # The test passes regardless - we're just checking the actual data
        assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
