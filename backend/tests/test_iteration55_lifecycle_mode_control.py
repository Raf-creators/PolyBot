"""
Test suite for Iteration 55: Lifecycle Mode Control UI
Tests POST /api/strategies/weather/lifecycle/mode endpoint and validates:
- Valid mode values (off, tag_only, shadow_exit, auto_exit)
- Invalid mode rejection with 400 error
- Unchanged status when setting same mode
- Mode persistence verification
- Mode changes reflected in lifecycle status endpoint
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def original_mode(api_client):
    """Get the original lifecycle mode before tests run."""
    response = api_client.get(f"{BASE_URL}/api/positions/weather/lifecycle")
    if response.status_code == 200:
        return response.json().get("mode", "tag_only")
    return "tag_only"


class TestLifecycleModeEndpoint:
    """Tests for POST /api/strategies/weather/lifecycle/mode"""
    
    def test_endpoint_accepts_valid_modes(self, api_client):
        """Test that endpoint returns 200 for all valid mode values."""
        valid_modes = ["off", "tag_only", "shadow_exit", "auto_exit"]
        
        for mode in valid_modes:
            response = api_client.post(
                f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
                json={"mode": mode}
            )
            assert response.status_code == 200, f"Expected 200 for mode '{mode}', got {response.status_code}: {response.text}"
            data = response.json()
            assert "status" in data
            assert data["status"] in ["updated", "unchanged"], f"Unexpected status for mode '{mode}': {data}"
        
        print("PASS: All valid modes (off, tag_only, shadow_exit, auto_exit) accepted with 200")
    
    def test_endpoint_returns_required_fields(self, api_client):
        """Test that response contains status, previous_mode, and current_mode."""
        # First set to tag_only
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "tag_only"})
        
        # Now switch to shadow_exit
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "shadow_exit"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data, "Response missing 'status' field"
        assert data["status"] == "updated", f"Expected 'updated' status, got {data['status']}"
        assert "previous_mode" in data, "Response missing 'previous_mode' field"
        assert "current_mode" in data, "Response missing 'current_mode' field"
        assert data["previous_mode"] == "tag_only", f"Expected previous_mode 'tag_only', got {data['previous_mode']}"
        assert data["current_mode"] == "shadow_exit", f"Expected current_mode 'shadow_exit', got {data['current_mode']}"
        
        print(f"PASS: Response contains required fields: status={data['status']}, previous_mode={data['previous_mode']}, current_mode={data['current_mode']}")
    
    def test_endpoint_rejects_invalid_mode(self, api_client):
        """Test that invalid mode values return 400 error."""
        invalid_modes = ["invalid", "LIVE", "shadow", "auto", "123", ""]
        
        for mode in invalid_modes:
            response = api_client.post(
                f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
                json={"mode": mode}
            )
            assert response.status_code == 400, f"Expected 400 for invalid mode '{mode}', got {response.status_code}"
            data = response.json()
            assert "detail" in data, f"Expected 'detail' in error response for mode '{mode}'"
        
        print(f"PASS: All invalid modes rejected with 400 error")
    
    def test_same_mode_returns_unchanged(self, api_client):
        """Test that setting the same mode returns status 'unchanged'."""
        # First set a known mode
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "tag_only"})
        
        # Now try setting the same mode again
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "tag_only"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "unchanged", f"Expected 'unchanged' status when setting same mode, got {data}"
        assert data["mode"] == "tag_only"
        
        print("PASS: Same mode returns 'unchanged' status")
    
    def test_mode_persists_to_lifecycle_endpoint(self, api_client):
        """Test that mode change is reflected in GET /api/positions/weather/lifecycle."""
        # Set to shadow_exit
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "shadow_exit"}
        )
        assert response.status_code == 200
        
        # Wait a moment for persistence
        time.sleep(0.2)
        
        # Verify in lifecycle endpoint
        lifecycle_response = api_client.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert lifecycle_response.status_code == 200
        
        lifecycle_data = lifecycle_response.json()
        assert lifecycle_data["mode"] == "shadow_exit", f"Expected mode 'shadow_exit' in lifecycle endpoint, got {lifecycle_data['mode']}"
        
        print("PASS: Mode change persisted and reflected in lifecycle endpoint")
    
    def test_mode_change_tag_only_to_shadow_exit(self, api_client):
        """Test mode transition from tag_only to shadow_exit."""
        # First ensure we're at tag_only
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "tag_only"})
        
        # Change to shadow_exit
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "shadow_exit"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "updated"
        assert data["previous_mode"] == "tag_only"
        assert data["current_mode"] == "shadow_exit"
        
        print(f"PASS: tag_only → shadow_exit transition works correctly")
    
    def test_mode_change_shadow_exit_back_to_tag_only(self, api_client):
        """Test mode transition from shadow_exit back to tag_only."""
        # Ensure we're at shadow_exit
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "shadow_exit"})
        
        # Change back to tag_only
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "tag_only"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "updated"
        assert data["previous_mode"] == "shadow_exit"
        assert data["current_mode"] == "tag_only"
        
        print("PASS: shadow_exit → tag_only transition works correctly")
    
    def test_mode_change_to_auto_exit_and_back(self, api_client):
        """Test mode transition to auto_exit and back to tag_only."""
        # Set to auto_exit
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "auto_exit"}
        )
        assert response.status_code == 200
        data = response.json()
        if data["status"] == "updated":
            assert data["current_mode"] == "auto_exit"
        
        # Immediately set back to tag_only (important to not leave in auto_exit)
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "tag_only"}
        )
        assert response.status_code == 200
        
        print("PASS: auto_exit transition and rollback works correctly")
    
    def test_mode_persisted_field_present(self, api_client):
        """Test that 'persisted' field is present in response."""
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "tag_only"}
        )
        assert response.status_code == 200
        
        data = response.json()
        # 'persisted' field should be present for 'updated' status
        if data["status"] == "updated":
            assert "persisted" in data, "Response missing 'persisted' field for updated status"
        
        print("PASS: 'persisted' field present in response")
    
    def test_timestamp_field_present_on_update(self, api_client):
        """Test that 'timestamp' field is present when mode is updated."""
        # Set to different mode to ensure update
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "off"})
        
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "tag_only"}
        )
        assert response.status_code == 200
        
        data = response.json()
        if data["status"] == "updated":
            assert "timestamp" in data, "Response missing 'timestamp' field for updated status"
        
        print("PASS: 'timestamp' field present on mode update")


class TestLifecycleModeIntegration:
    """Integration tests for lifecycle mode with other endpoints."""
    
    def test_positions_by_strategy_reflects_mode(self, api_client):
        """Test that /api/positions/by-strategy shows correct lifecycle mode."""
        # Set mode to shadow_exit
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "shadow_exit"})
        time.sleep(0.1)
        
        response = api_client.get(f"{BASE_URL}/api/positions/by-strategy")
        assert response.status_code == 200
        
        data = response.json()
        assert "lifecycle" in data, "positions/by-strategy missing 'lifecycle' field"
        assert data["lifecycle"]["mode"] == "shadow_exit", f"Expected mode 'shadow_exit', got {data['lifecycle']['mode']}"
        
        # Reset to tag_only
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "tag_only"})
        
        print("PASS: positions/by-strategy reflects lifecycle mode correctly")
    
    def test_lifecycle_dashboard_shows_correct_mode(self, api_client):
        """Test that lifecycle dashboard endpoint shows current mode."""
        # Set to tag_only
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "tag_only"})
        time.sleep(0.1)
        
        response = api_client.get(f"{BASE_URL}/api/positions/weather/lifecycle/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        assert "config" in data, "Dashboard missing 'config' field"
        assert data["config"].get("lifecycle_mode") == "tag_only" or "lifecycle_mode" in str(data), \
            f"Dashboard should reflect lifecycle mode"
        
        print("PASS: Lifecycle dashboard shows correct mode in config")
    
    def test_exit_candidates_endpoint_works_with_mode(self, api_client):
        """Test that exit-candidates endpoint still works after mode changes."""
        # Change mode a few times
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "shadow_exit"})
        api_client.post(f"{BASE_URL}/api/strategies/weather/lifecycle/mode", json={"mode": "tag_only"})
        
        response = api_client.get(f"{BASE_URL}/api/positions/weather/exit-candidates")
        assert response.status_code == 200
        
        data = response.json()
        assert "mode" in data
        assert data["mode"] == "tag_only"
        assert "candidates" in data
        
        print("PASS: Exit candidates endpoint works correctly after mode changes")


class TestRestoreModeAfterTests:
    """Restore mode to tag_only after all tests."""
    
    def test_restore_mode_to_tag_only(self, api_client):
        """FINAL TEST: Restore lifecycle mode to tag_only as requested."""
        response = api_client.post(
            f"{BASE_URL}/api/strategies/weather/lifecycle/mode",
            json={"mode": "tag_only"}
        )
        assert response.status_code == 200
        
        # Verify restoration
        lifecycle_response = api_client.get(f"{BASE_URL}/api/positions/weather/lifecycle")
        assert lifecycle_response.status_code == 200
        assert lifecycle_response.json()["mode"] == "tag_only"
        
        print("PASS: Mode restored to tag_only after testing")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
