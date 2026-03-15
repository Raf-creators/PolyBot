"""Unit tests for RollingCalibrationService — sigma computation, min samples, bias."""

import asyncio
import math
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import AsyncMock, MagicMock, patch
from services.rolling_calibration_service import RollingCalibrationService
from engine.strategies.weather_models import WeatherConfig, RollingCalibration


class FakeCursor:
    """Mock async cursor for MongoDB."""
    def __init__(self, docs):
        self._docs = docs
    async def to_list(self, length=None):
        return self._docs
    def __aiter__(self):
        return self._async_iter()
    async def _async_iter(self):
        for doc in self._docs:
            yield doc


class FakeCollection:
    """Mock MongoDB collection."""
    def __init__(self, docs=None):
        self._docs = docs or []
        self.update_one = AsyncMock()
        self.create_index = AsyncMock()

    async def count_documents(self, query):
        if query.get("resolved"):
            return sum(1 for d in self._docs if d.get("resolved"))
        if query.get("station_id"):
            return sum(1 for d in self._docs if d.get("station_id") == query["station_id"])
        return len(self._docs)

    def find(self, query, projection=None):
        result = self._docs
        if query.get("station_id"):
            result = [d for d in result if d.get("station_id") == query["station_id"]]
        if query.get("resolved"):
            result = [d for d in result if d.get("resolved")]
        return FakeCursor(result)

    async def find_one(self, query, projection=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None


def make_service(accuracy_records=None, rolling_records=None, config=None):
    """Create a RollingCalibrationService with mocked collections."""
    accuracy_col = FakeCollection(accuracy_records or [])
    rolling_col = FakeCollection(rolling_records or [])

    class FakeDB:
        def __getitem__(self, key):
            if key == "weather_rolling_calibration":
                return rolling_col
            if key == "forecast_accuracy":
                return accuracy_col
            return FakeCollection()

    svc = RollingCalibrationService(FakeDB())
    svc._collection = rolling_col
    svc._accuracy_collection = accuracy_col
    if config:
        svc.set_config(config)
    return svc


def make_resolved_records(station_id, count, base_error=0.0, error_spread=2.0, lead_hours=36):
    """Generate fake resolved forecast accuracy records."""
    records = []
    for i in range(count):
        month = (i % 12) + 1
        error = base_error + (i % 5 - 2) * error_spread / 2
        records.append({
            "station_id": station_id,
            "target_date": f"2026-{month:02d}-{(i % 28) + 1:02d}",
            "forecast_high_f": 50.0,
            "observed_high_f": 50.0 + error,
            "forecast_error_f": error,
            "abs_error_f": abs(error),
            "lead_hours": lead_hours,
            "sigma_used": 2.5,
            "resolved": True,
            "resolved_at": f"2026-{month:02d}-{(i % 28) + 2:02d}T00:00:00+00:00",
        })
    return records


@pytest.fixture
def config():
    return WeatherConfig(
        rolling_calibration_enabled=True,
        rolling_min_samples=10,
        rolling_recalc_interval_hours=168,
        rolling_recalc_after_n_records=20,
    )


class TestRollingCalibrationComputation:
    @pytest.mark.asyncio
    async def test_sufficient_data_produces_calibration(self, config):
        """With enough records, rolling calibration should produce sigma values."""
        records = make_resolved_records("KLGA", 20)
        svc = make_service(accuracy_records=records, config=config)

        result = await svc.run_rolling_calibration(station_ids=["KLGA"])

        assert result["status"] == "completed"
        assert result["stations_calibrated"] == 1
        klga = result["results"]["KLGA"]
        assert klga["status"] == "calibrated"
        assert klga["sample_count"] == 20
        assert "sigma_by_lead" in klga
        assert "bias_by_lead" in klga
        # Sigma should be reasonable (>0)
        for bracket, sigma in klga["sigma_by_lead"].items():
            assert sigma > 0, f"Sigma for {bracket} should be positive"

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_status(self, config):
        """Fewer records than min_samples should return insufficient_data."""
        records = make_resolved_records("KLGA", 5)
        svc = make_service(accuracy_records=records, config=config)

        result = await svc.run_rolling_calibration(station_ids=["KLGA"])

        assert result["stations_insufficient"] == 1
        klga = result["results"]["KLGA"]
        assert klga["status"] == "insufficient_data"
        assert klga["sample_count"] == 5

    @pytest.mark.asyncio
    async def test_bias_computation(self, config):
        """Bias should reflect systematic over/underestimation."""
        records = []
        for i in range(20):
            records.append({
                "station_id": "KORD",
                "target_date": f"2026-06-{(i % 28) + 1:02d}",
                "forecast_high_f": 70.0,
                "observed_high_f": 73.0,
                "forecast_error_f": 3.0,
                "abs_error_f": 3.0,
                "lead_hours": 36,
                "sigma_used": 2.5,
                "resolved": True,
            })
        svc = make_service(accuracy_records=records, config=config)

        result = await svc.run_rolling_calibration(station_ids=["KORD"])
        kord = result["results"]["KORD"]
        assert kord["status"] == "calibrated"
        assert kord["mean_bias_f"] == pytest.approx(3.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_no_records_returns_insufficient(self, config):
        """No records at all should return insufficient_data."""
        svc = make_service(accuracy_records=[], config=config)

        result = await svc.run_rolling_calibration(station_ids=["KLGA"])
        assert result["stations_insufficient"] == 1


class TestRecalcPolicy:
    @pytest.mark.asyncio
    async def test_should_recalculate_first_time(self, config):
        """Should recalculate on first run when enough data exists."""
        records = make_resolved_records("KLGA", 20)
        svc = make_service(accuracy_records=records, config=config)

        assert await svc.should_recalculate() is True

    @pytest.mark.asyncio
    async def test_should_not_recalculate_when_disabled(self, config):
        """Should not recalculate when disabled."""
        config.rolling_calibration_enabled = False
        records = make_resolved_records("KLGA", 100)
        svc = make_service(accuracy_records=records, config=config)

        assert await svc.should_recalculate() is False


class TestRollingCalibrationModel:
    def test_model_serialization(self):
        """RollingCalibration model should serialize and deserialize correctly."""
        cal = RollingCalibration(
            station_id="KLGA",
            source="rolling",
            sample_count=25,
            sigma_by_lead_hours={"0_24": 1.9, "24_48": 2.8},
            mean_bias_f=0.5,
            bias_by_lead_hours={"0_24": 0.3, "24_48": 0.7},
            samples_by_lead_hours={"0_24": 15, "24_48": 10},
            coverage_start="2026-01-01",
            coverage_end="2026-03-15",
        )
        d = cal.model_dump()
        assert d["source"] == "rolling"
        assert d["sample_count"] == 25
        assert d["mean_bias_f"] == 0.5
        assert d["bias_by_lead_hours"]["0_24"] == 0.3
        assert d["coverage_start"] == "2026-01-01"

        # Round-trip
        cal2 = RollingCalibration(**d)
        assert cal2.station_id == "KLGA"
        assert cal2.sigma_by_lead_hours == {"0_24": 1.9, "24_48": 2.8}


class TestStatsAndStatus:
    @pytest.mark.asyncio
    async def test_status_shape(self, config):
        """get_status() should return well-shaped data."""
        svc = make_service(accuracy_records=[], config=config)

        status = await svc.get_status()
        assert "enabled" in status
        assert "total_stations_calibrated" in status
        assert "total_resolved_records" in status
        assert "needs_recalculation" in status
        assert "min_samples_required" in status
        assert status["enabled"] is True
