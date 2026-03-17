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
from engine.strategies.weather_pricing import get_season, _lead_hours_to_bracket, compute_all_bucket_probabilities

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


    # ---- Calibration Metrics (Brier Score, Calibration Error) ----

    async def compute_calibration_metrics(self) -> Dict[str, Any]:
        """Compute Brier score, calibration error, and sigma evolution.

        Uses resolved forecast_accuracy records. For each:
        - Compute how well sigma predicted the actual error distribution
        - Measure over/under-confidence
        - Group by lead_hours and market_type where available
        """
        cursor = self._accuracy_collection.find(
            {"resolved": True},
            {"_id": 0},
        )
        records = await cursor.to_list(length=10000)

        if not records:
            return {
                "status": "no_data",
                "total_resolved": 0,
                "brier_score": None,
                "calibration_error": None,
            }

        # === Brier-like score: how well does sigma capture actual errors? ===
        # For each record: check if actual error falls within predicted sigma
        # A well-calibrated model should have ~68% of errors within 1-sigma
        brier_contributions = []
        within_1sigma = 0
        within_2sigma = 0
        over_confident = 0  # sigma too small (error > sigma)
        under_confident = 0  # sigma too large (error < 0.25 * sigma)
        total_valid = 0

        # Grouped metrics
        by_lead = defaultdict(lambda: {"errors": [], "sigmas": [], "brier": [], "within_1s": 0, "count": 0})
        by_station = defaultdict(lambda: {"errors": [], "sigmas": [], "brier": [], "within_1s": 0, "count": 0})
        by_market_type = defaultdict(lambda: {"errors": [], "sigmas": [], "brier": [], "within_1s": 0, "count": 0})

        # For calibration curve: bin predictions by confidence level
        calibration_bins = defaultdict(lambda: {"predictions": [], "outcomes": []})

        sigma_evolution = []  # Track sigma accuracy over time

        for rec in records:
            error_f = rec.get("forecast_error_f")
            sigma = rec.get("sigma_used")
            lead_hours = rec.get("lead_hours", 48)
            station_id = rec.get("station_id", "unknown")
            market_type = rec.get("market_type", "temperature")
            target_date = rec.get("target_date", "")

            if error_f is None or sigma is None or sigma <= 0:
                continue

            total_valid += 1
            abs_error = abs(error_f)
            normalized_error = abs_error / sigma  # z-score

            # Brier-like: (normalized_error)^2 penalizes miscalibration
            # Perfect calibration: normalized errors follow N(0,1)
            # Expected value of normalized_error^2 for N(0,1) = 1.0
            brier = (normalized_error - 1.0) ** 2  # 0 = perfect calibration
            brier_contributions.append(brier)

            # Sigma coverage
            if abs_error <= sigma:
                within_1sigma += 1
            if abs_error <= 2 * sigma:
                within_2sigma += 1
            if abs_error > 1.5 * sigma:
                over_confident += 1
            if abs_error < 0.25 * sigma:
                under_confident += 1

            # Group by lead bracket
            bracket = _lead_hours_to_bracket(lead_hours)
            by_lead[bracket]["errors"].append(abs_error)
            by_lead[bracket]["sigmas"].append(sigma)
            by_lead[bracket]["brier"].append(brier)
            if abs_error <= sigma:
                by_lead[bracket]["within_1s"] += 1
            by_lead[bracket]["count"] += 1

            # Group by station
            by_station[station_id]["errors"].append(abs_error)
            by_station[station_id]["sigmas"].append(sigma)
            by_station[station_id]["brier"].append(brier)
            if abs_error <= sigma:
                by_station[station_id]["within_1s"] += 1
            by_station[station_id]["count"] += 1

            # Group by market type
            by_market_type[market_type]["errors"].append(abs_error)
            by_market_type[market_type]["sigmas"].append(sigma)
            by_market_type[market_type]["brier"].append(brier)
            if abs_error <= sigma:
                by_market_type[market_type]["within_1s"] += 1
            by_market_type[market_type]["count"] += 1

            # Calibration curve: bin by predicted confidence (1-sigma coverage proxy)
            # Use sigma size as confidence indicator (smaller sigma = more confident)
            confidence_bin = min(int(sigma / 0.5), 20)  # 0.5F bins
            calibration_bins[confidence_bin]["predictions"].append(sigma)
            calibration_bins[confidence_bin]["outcomes"].append(abs_error)

            # Sigma evolution (time-ordered)
            if target_date:
                sigma_evolution.append({
                    "date": target_date,
                    "sigma_used": round(sigma, 2),
                    "actual_error": round(abs_error, 2),
                    "z_score": round(normalized_error, 3),
                    "lead_hours": lead_hours,
                    "station": station_id,
                })

        if total_valid == 0:
            return {"status": "no_valid_data", "total_resolved": len(records), "total_valid": 0}

        # === Aggregate metrics ===
        overall_brier = round(sum(brier_contributions) / total_valid, 4)
        coverage_1s = round(within_1sigma / total_valid, 4)  # should be ~0.68
        coverage_2s = round(within_2sigma / total_valid, 4)  # should be ~0.95
        calibration_error = round(abs(coverage_1s - 0.6827), 4)  # how far from ideal

        # Per-lead breakdown
        lead_breakdown = {}
        for bracket, data in by_lead.items():
            n = data["count"]
            if n == 0:
                continue
            avg_err = sum(data["errors"]) / n
            avg_sig = sum(data["sigmas"]) / n
            cov = data["within_1s"] / n
            b = sum(data["brier"]) / n
            lead_breakdown[bracket] = {
                "count": n,
                "avg_error": round(avg_err, 2),
                "avg_sigma": round(avg_sig, 2),
                "coverage_1sigma": round(cov, 4),
                "calibration_error": round(abs(cov - 0.6827), 4),
                "brier_score": round(b, 4),
                "sigma_recommendation": round(avg_err / 0.6745, 2),  # adjust sigma so 68% coverage
                "is_overconfident": cov < 0.55,
                "is_underconfident": cov > 0.80,
            }

        # Per-station breakdown
        station_breakdown = {}
        for sid, data in by_station.items():
            n = data["count"]
            if n < 3:
                continue
            avg_err = sum(data["errors"]) / n
            avg_sig = sum(data["sigmas"]) / n
            cov = data["within_1s"] / n
            b = sum(data["brier"]) / n
            station_breakdown[sid] = {
                "count": n,
                "avg_error": round(avg_err, 2),
                "avg_sigma": round(avg_sig, 2),
                "coverage_1sigma": round(cov, 4),
                "brier_score": round(b, 4),
                "sigma_recommendation": round(avg_err / 0.6745, 2),
            }

        # Per-market-type breakdown
        market_type_breakdown = {}
        for mt, data in by_market_type.items():
            n = data["count"]
            if n == 0:
                continue
            avg_err = sum(data["errors"]) / n
            avg_sig = sum(data["sigmas"]) / n
            cov = data["within_1s"] / n
            b = sum(data["brier"]) / n
            market_type_breakdown[mt] = {
                "count": n,
                "avg_error": round(avg_err, 2),
                "avg_sigma": round(avg_sig, 2),
                "coverage_1sigma": round(cov, 4),
                "calibration_error": round(abs(cov - 0.6827), 4),
                "brier_score": round(b, 4),
                "sigma_recommendation": round(avg_err / 0.6745, 2),
            }

        # Calibration curve data (binned)
        calibration_curve = []
        for bin_idx in sorted(calibration_bins.keys()):
            data = calibration_bins[bin_idx]
            if not data["predictions"]:
                continue
            avg_predicted_sigma = sum(data["predictions"]) / len(data["predictions"])
            avg_actual_error = sum(data["outcomes"]) / len(data["outcomes"])
            calibration_curve.append({
                "predicted_sigma": round(avg_predicted_sigma, 2),
                "actual_error": round(avg_actual_error, 2),
                "count": len(data["predictions"]),
                "ratio": round(avg_actual_error / avg_predicted_sigma, 3) if avg_predicted_sigma > 0 else None,
            })

        # Sort sigma evolution by date, limit to last 100
        sigma_evolution.sort(key=lambda x: x["date"])
        sigma_evolution = sigma_evolution[-100:]

        return {
            "status": "computed",
            "total_resolved": len(records),
            "total_valid": total_valid,
            # Overall metrics
            "brier_score": overall_brier,
            "coverage_1sigma": coverage_1s,
            "coverage_2sigma": coverage_2s,
            "ideal_coverage_1sigma": 0.6827,
            "calibration_error": calibration_error,
            "over_confident_pct": round(over_confident / total_valid, 4),
            "under_confident_pct": round(under_confident / total_valid, 4),
            # Breakdowns
            "by_lead_bracket": lead_breakdown,
            "by_station": station_breakdown,
            "by_market_type": market_type_breakdown,
            # Curve + evolution
            "calibration_curve": calibration_curve,
            "sigma_evolution": sigma_evolution,
        }
