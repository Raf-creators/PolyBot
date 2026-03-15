"""Rolling Calibration Service — refines sigma using live forecast_accuracy data.

Aggregates resolved forecast records from MongoDB `forecast_accuracy` collection
by station + lead-time bracket + season, and computes updated empirical sigma
values and bias estimates.

Storage: `weather_rolling_calibration` collection (separate from bootstrap).
Policy: recalculate on whichever fires first:
  - time interval (rolling_recalc_interval_hours)
  - record count (rolling_recalc_after_n_records new resolved records)

Safety:
  - Requires rolling_min_samples per station to produce a calibration
  - Falls back to historical bootstrap or default sigma table when sparse
  - Never overwrites raw forecast_accuracy records
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from models import utc_now
from engine.strategies.weather_models import (
    RollingCalibration, SigmaCalibration, WeatherConfig, StationType,
)
from engine.strategies.weather_parser import STATION_REGISTRY
from engine.strategies.weather_pricing import get_season, _lead_hours_to_bracket

logger = logging.getLogger(__name__)

COLLECTION = "weather_rolling_calibration"

# Same lead brackets as calibration_service
LEAD_BRACKETS = {
    "0_24": (0, 24),
    "24_48": (24, 48),
    "48_72": (48, 72),
    "72_120": (72, 120),
    "120_168": (120, 168),
}

# Default sigma fallback (same as weather_pricing)
_DEFAULT_SIGMA_TABLE = {
    "0_24": 1.8,
    "24_48": 2.7,
    "48_72": 3.4,
    "72_120": 4.8,
    "120_168": 6.2,
}


class RollingCalibrationService:
    """Computes rolling sigma calibration from live forecast accuracy data."""

    def __init__(self, db):
        self._db = db
        self._collection = db[COLLECTION]
        self._accuracy_collection = db["forecast_accuracy"]
        self._config: Optional[WeatherConfig] = None
        self._last_run: Optional[str] = None
        self._last_status: str = "not_run"
        self._last_record_count: int = 0  # resolved count at last run
        self._calibrations: Dict[str, RollingCalibration] = {}

    async def ensure_indexes(self):
        await self._collection.create_index("station_id", unique=True)

    def set_config(self, config: WeatherConfig):
        self._config = config

    @property
    def enabled(self) -> bool:
        return bool(self._config and self._config.rolling_calibration_enabled)

    # ---- Check whether recalculation is needed ----

    async def should_recalculate(self) -> bool:
        """Returns True if rolling recalculation should run based on policy."""
        if not self.enabled:
            return False

        current_resolved = await self._accuracy_collection.count_documents({"resolved": True})

        # Policy 1: time-based
        if self._last_run:
            try:
                last_dt = datetime.fromisoformat(self._last_run.replace("Z", "+00:00"))
                hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                if hours_since >= self._config.rolling_recalc_interval_hours:
                    return True
            except (ValueError, TypeError):
                pass
        else:
            # Never run before, should run if we have enough data
            if current_resolved >= self._config.rolling_min_samples:
                return True

        # Policy 2: record-count-based
        new_records = current_resolved - self._last_record_count
        if new_records >= self._config.rolling_recalc_after_n_records:
            return True

        return False

    # ---- Core computation ----

    async def run_rolling_calibration(
        self,
        station_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Aggregate resolved forecast_accuracy records and compute rolling sigma per station."""
        self._last_status = "running"
        results = {}
        errors = []

        if not station_ids:
            station_ids = list(STATION_REGISTRY.keys())

        min_samples = self._config.rolling_min_samples if self._config else 15
        current_resolved = await self._accuracy_collection.count_documents({"resolved": True})

        for station_id in station_ids:
            try:
                result = await self._calibrate_station(station_id, min_samples)
                results[station_id] = result
            except Exception as e:
                logger.error(f"[ROLLING CAL] Failed for {station_id}: {e}")
                errors.append(f"{station_id}: {e}")
                results[station_id] = {"status": "error", "error": str(e)}

        self._last_run = utc_now()
        self._last_status = "completed"
        self._last_record_count = current_resolved

        # Reload in-memory cache
        self._calibrations = await self.get_all_calibrations()

        succeeded = sum(1 for r in results.values() if r.get("status") == "calibrated")
        logger.info(
            f"[ROLLING CAL] Completed: {succeeded}/{len(results)} stations calibrated, "
            f"{sum(1 for r in results.values() if r.get('status') == 'insufficient_data')} insufficient"
        )

        return {
            "status": "completed",
            "stations_processed": len(results),
            "stations_calibrated": succeeded,
            "stations_insufficient": sum(1 for r in results.values() if r.get("status") == "insufficient_data"),
            "stations_error": len(errors),
            "errors": errors,
            "results": results,
            "run_at": self._last_run,
            "total_resolved_records": current_resolved,
        }

    async def _calibrate_station(self, station_id: str, min_samples: int) -> Dict[str, Any]:
        """Compute rolling calibration for a single station from resolved forecast records."""
        # Fetch all resolved records for this station
        cursor = self._accuracy_collection.find(
            {"station_id": station_id, "resolved": True},
            {"_id": 0},
        )
        records = await cursor.to_list(length=5000)

        if len(records) < min_samples:
            return {
                "status": "insufficient_data",
                "sample_count": len(records),
                "min_required": min_samples,
            }

        station = STATION_REGISTRY.get(station_id)
        station_type = station.station_type if station else StationType.INLAND

        # Group errors by lead-time bracket
        errors_by_lead: Dict[str, List[float]] = defaultdict(list)
        errors_by_season: Dict[str, List[float]] = defaultdict(list)
        all_errors = []
        dates = []

        for rec in records:
            error_f = rec.get("forecast_error_f")
            lead_hours = rec.get("lead_hours", 48)
            target_date = rec.get("target_date", "")

            if error_f is None:
                continue

            all_errors.append(error_f)
            bracket = _lead_hours_to_bracket(lead_hours)
            errors_by_lead[bracket].append(error_f)

            # Extract month for seasonal grouping
            try:
                month = int(target_date[5:7])
                season = get_season(month)
                errors_by_season[season.value].append(error_f)
            except (ValueError, IndexError):
                pass

            if target_date:
                dates.append(target_date)

        if not all_errors:
            return {"status": "insufficient_data", "sample_count": 0, "min_required": min_samples}

        # ---- Compute sigma per lead bracket ----
        sigma_by_lead = {}
        bias_by_lead = {}
        samples_by_lead = {}
        for bracket in LEAD_BRACKETS:
            errs = errors_by_lead.get(bracket, [])
            samples_by_lead[bracket] = len(errs)
            if len(errs) >= 3:
                mean_e = sum(errs) / len(errs)
                var = sum((e - mean_e) ** 2 for e in errs) / len(errs)
                sigma_by_lead[bracket] = round(math.sqrt(var) if var > 0 else _DEFAULT_SIGMA_TABLE[bracket], 4)
                bias_by_lead[bracket] = round(mean_e, 4)
            else:
                # Fall back to default for this bracket
                sigma_by_lead[bracket] = _DEFAULT_SIGMA_TABLE[bracket]
                bias_by_lead[bracket] = 0.0

        # ---- Compute seasonal factors ----
        # Base sigma = overall std dev
        global_mean = sum(all_errors) / len(all_errors)
        global_var = sum((e - global_mean) ** 2 for e in all_errors) / len(all_errors)
        base_sigma = math.sqrt(global_var) if global_var > 0 else 2.0

        seasonal_factors = {}
        bias_by_season_out = {}
        samples_by_season = {}
        for season_name in ["winter", "spring", "summer", "fall"]:
            errs = errors_by_season.get(season_name, [])
            samples_by_season[season_name] = len(errs)
            if len(errs) >= 3 and base_sigma > 0:
                s_mean = sum(errs) / len(errs)
                s_var = sum((e - s_mean) ** 2 for e in errs) / len(errs)
                s_sigma = math.sqrt(s_var) if s_var > 0 else base_sigma
                seasonal_factors[season_name] = round(s_sigma / base_sigma, 4)
                bias_by_season_out[season_name] = round(s_mean, 4)
            else:
                seasonal_factors[season_name] = 1.0
                bias_by_season_out[season_name] = 0.0

        # Station type factor
        station_type_factor = 0.90 if station_type == StationType.COASTAL else 1.10

        # Overall bias
        mean_bias = round(global_mean, 4)

        # Coverage window
        sorted_dates = sorted(d for d in dates if d)
        coverage_start = sorted_dates[0] if sorted_dates else None
        coverage_end = sorted_dates[-1] if sorted_dates else None

        # Build rolling calibration record
        rolling_cal = RollingCalibration(
            station_id=station_id,
            source="rolling",
            sample_count=len(all_errors),
            sigma_by_lead_hours=sigma_by_lead,
            seasonal_factors=seasonal_factors,
            station_type_factor=station_type_factor,
            mean_bias_f=mean_bias,
            bias_by_lead_hours=bias_by_lead,
            bias_by_season=bias_by_season_out,
            samples_by_lead_hours=samples_by_lead,
            samples_by_season=samples_by_season,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )

        # Persist to MongoDB (upsert)
        doc = rolling_cal.model_dump()
        await self._collection.update_one(
            {"station_id": station_id},
            {"$set": doc},
            upsert=True,
        )

        logger.info(
            f"[ROLLING CAL] {station_id}: samples={len(all_errors)}, "
            f"bias={mean_bias:+.2f}F, sigma_0_24={sigma_by_lead.get('0_24', '?')}, "
            f"coverage={coverage_start} to {coverage_end}"
        )

        return {
            "status": "calibrated",
            "sample_count": len(all_errors),
            "mean_bias_f": mean_bias,
            "sigma_by_lead": sigma_by_lead,
            "bias_by_lead": bias_by_lead,
            "seasonal_factors": seasonal_factors,
            "coverage": f"{coverage_start} to {coverage_end}",
        }

    # ---- Data Access ----

    async def get_all_calibrations(self) -> Dict[str, RollingCalibration]:
        """Load all rolling calibration records from MongoDB."""
        cursor = self._collection.find({}, {"_id": 0})
        calibrations = {}
        async for doc in cursor:
            try:
                cal = RollingCalibration(**doc)
                calibrations[cal.station_id] = cal
            except Exception as e:
                logger.warning(f"[ROLLING CAL] Failed to parse record: {e}")
        return calibrations

    async def get_calibration(self, station_id: str) -> Optional[RollingCalibration]:
        doc = await self._collection.find_one({"station_id": station_id}, {"_id": 0})
        if doc:
            return RollingCalibration(**doc)
        return None

    def get_cached_calibrations(self) -> Dict[str, RollingCalibration]:
        """Return in-memory cached rolling calibrations (loaded on start/after run)."""
        return self._calibrations

    async def get_status(self) -> Dict[str, Any]:
        """Get rolling calibration status for API/dashboard."""
        count = await self._collection.count_documents({})
        resolved_total = await self._accuracy_collection.count_documents({"resolved": True})
        calibrations = await self.get_all_calibrations()

        station_info = {}
        for sid, cal in calibrations.items():
            station_info[sid] = {
                "station_id": sid,
                "source": cal.source,
                "sample_count": cal.sample_count,
                "calibrated_at": cal.calibrated_at,
                "mean_bias_f": cal.mean_bias_f,
                "sigma_0_24": cal.sigma_by_lead_hours.get("0_24"),
                "sigma_48_72": cal.sigma_by_lead_hours.get("48_72"),
                "bias_by_lead": cal.bias_by_lead_hours,
                "bias_by_season": cal.bias_by_season,
                "samples_by_lead": cal.samples_by_lead_hours,
                "coverage_start": cal.coverage_start,
                "coverage_end": cal.coverage_end,
                "sufficient": cal.sample_count >= (self._config.rolling_min_samples if self._config else 15),
            }

        needs_recalc = await self.should_recalculate()

        return {
            "enabled": self.enabled,
            "total_stations_calibrated": count,
            "total_resolved_records": resolved_total,
            "last_run": self._last_run,
            "last_status": self._last_status,
            "last_record_count_at_run": self._last_record_count,
            "needs_recalculation": needs_recalc,
            "min_samples_required": self._config.rolling_min_samples if self._config else 15,
            "recalc_interval_hours": self._config.rolling_recalc_interval_hours if self._config else 168,
            "recalc_after_n_records": self._config.rolling_recalc_after_n_records if self._config else 20,
            "stations": station_info,
        }

    async def load_cached(self):
        """Load calibrations into memory on startup."""
        self._calibrations = await self.get_all_calibrations()
        self._last_record_count = await self._accuracy_collection.count_documents({"resolved": True})
        if self._calibrations:
            logger.info(f"[ROLLING CAL] Loaded {len(self._calibrations)} cached rolling calibrations")
