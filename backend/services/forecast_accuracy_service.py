"""Forecast accuracy tracking service for WeatherTrader calibration.

Stores resolved forecast outcomes in MongoDB `forecast_accuracy` collection.
Provides rolling per-station accuracy metrics for calibration visibility.
Does NOT modify any execution or strategy state.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models import utc_now
from engine.strategies.weather_models import ForecastAccuracyRecord

logger = logging.getLogger(__name__)

COLLECTION = "forecast_accuracy"

# Minimum samples to consider a station's calibration data meaningful
MIN_SAMPLES_FOR_CALIBRATION = 10


class ForecastAccuracyService:
    """Persists and queries resolved forecast accuracy records."""

    def __init__(self, db):
        self._db = db
        self._collection = db[COLLECTION]

    async def ensure_indexes(self):
        """Create indexes for efficient querying."""
        await self._collection.create_index("station_id")
        await self._collection.create_index("target_date")
        await self._collection.create_index([("station_id", 1), ("target_date", 1)], unique=True)

    async def record_forecast(self, record: ForecastAccuracyRecord):
        """Insert or update a forecast accuracy record (upsert on station+date)."""
        doc = record.model_dump()
        doc.pop("id", None)
        await self._collection.update_one(
            {"station_id": record.station_id, "target_date": record.target_date},
            {"$set": doc},
            upsert=True,
        )
        logger.info(
            f"[ACCURACY] Recorded forecast: {record.station_id} {record.target_date} "
            f"forecast={record.forecast_high_f:.1f}F"
        )

    async def resolve_forecast(
        self, station_id: str, target_date: str,
        observed_high_f: float, winning_bucket: Optional[str] = None,
    ):
        """Mark a forecast as resolved with the actual observed temperature."""
        forecast_doc = await self._collection.find_one(
            {"station_id": station_id, "target_date": target_date},
            {"_id": 0},
        )
        if not forecast_doc:
            logger.warning(f"[ACCURACY] No forecast record for {station_id}:{target_date}")
            return

        forecast_high = forecast_doc.get("forecast_high_f", 0)
        error = round(observed_high_f - forecast_high, 2)
        abs_error = round(abs(error), 2)

        update = {
            "observed_high_f": observed_high_f,
            "forecast_error_f": error,
            "abs_error_f": abs_error,
            "resolved": True,
            "resolved_at": utc_now(),
        }
        if winning_bucket:
            update["winning_bucket"] = winning_bucket

        await self._collection.update_one(
            {"station_id": station_id, "target_date": target_date},
            {"$set": update},
        )
        logger.info(
            f"[ACCURACY] Resolved: {station_id} {target_date} "
            f"forecast={forecast_high:.1f}F actual={observed_high_f:.1f}F "
            f"error={error:+.1f}F"
        )

    async def get_history(self, limit: int = 100, station_id: Optional[str] = None) -> List[Dict]:
        """Get forecast accuracy records, most recent first."""
        query = {}
        if station_id:
            query["station_id"] = station_id
        cursor = self._collection.find(query, {"_id": 0}).sort("target_date", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_station_summary(self) -> Dict[str, Any]:
        """Per-station accuracy summary with rolling MAE."""
        pipeline = [
            {"$match": {"resolved": True}},
            {"$group": {
                "_id": "$station_id",
                "sample_count": {"$sum": 1},
                "mean_abs_error_f": {"$avg": "$abs_error_f"},
                "mean_error_f": {"$avg": "$forecast_error_f"},
                "max_abs_error_f": {"$max": "$abs_error_f"},
                "min_error_f": {"$min": "$forecast_error_f"},
                "max_error_f": {"$max": "$forecast_error_f"},
                "avg_sigma_used": {"$avg": "$sigma_used"},
                "avg_lead_hours": {"$avg": "$lead_hours"},
                "latest_date": {"$max": "$target_date"},
            }},
            {"$sort": {"_id": 1}},
        ]
        results = await self._collection.aggregate(pipeline).to_list(length=100)

        summaries = {}
        for r in results:
            station = r["_id"]
            count = r["sample_count"]
            summaries[station] = {
                "station_id": station,
                "sample_count": count,
                "mean_abs_error_f": round(r["mean_abs_error_f"], 2) if r["mean_abs_error_f"] else None,
                "mean_bias_f": round(r["mean_error_f"], 2) if r["mean_error_f"] else None,
                "max_abs_error_f": round(r["max_abs_error_f"], 2) if r["max_abs_error_f"] else None,
                "avg_sigma_used": round(r["avg_sigma_used"], 2) if r["avg_sigma_used"] else None,
                "avg_lead_hours": round(r["avg_lead_hours"], 1) if r["avg_lead_hours"] else None,
                "latest_resolved_date": r["latest_date"],
                "calibration_meaningful": count >= MIN_SAMPLES_FOR_CALIBRATION,
                "calibration_note": (
                    f"Sufficient data ({count} samples)" if count >= MIN_SAMPLES_FOR_CALIBRATION
                    else f"Insufficient data ({count}/{MIN_SAMPLES_FOR_CALIBRATION} needed)"
                ),
            }
        return summaries

    async def get_calibration_health(self) -> Dict[str, Any]:
        """Overall calibration health for the dashboard."""
        total = await self._collection.count_documents({})
        resolved = await self._collection.count_documents({"resolved": True})
        pending = total - resolved

        station_summary = await self.get_station_summary()
        stations_with_data = len(station_summary)
        stations_calibratable = sum(
            1 for s in station_summary.values() if s["calibration_meaningful"]
        )

        # Global MAE across all resolved samples
        global_pipeline = [
            {"$match": {"resolved": True}},
            {"$group": {
                "_id": None,
                "global_mae": {"$avg": "$abs_error_f"},
                "global_bias": {"$avg": "$forecast_error_f"},
                "total_resolved": {"$sum": 1},
            }},
        ]
        global_results = await self._collection.aggregate(global_pipeline).to_list(length=1)
        global_stats = global_results[0] if global_results else {}

        return {
            "total_records": total,
            "resolved_records": resolved,
            "pending_resolution": pending,
            "stations_with_data": stations_with_data,
            "stations_calibratable": stations_calibratable,
            "global_mae_f": round(global_stats.get("global_mae", 0), 2) if global_stats.get("global_mae") else None,
            "global_bias_f": round(global_stats.get("global_bias", 0), 2) if global_stats.get("global_bias") else None,
            "using_defaults": stations_calibratable == 0,
            "calibration_status": (
                "no_data" if total == 0
                else "collecting" if stations_calibratable == 0
                else "partial" if stations_calibratable < stations_with_data
                else "ready"
            ),
            "calibration_note": (
                "No forecast accuracy data collected yet"
                if total == 0
                else f"Collecting data ({resolved} resolved, {pending} pending)"
                if stations_calibratable == 0
                else f"{stations_calibratable}/{stations_with_data} stations have enough data for calibration"
            ),
            "station_summaries": station_summary,
        }

    async def get_unresolved(self, limit: int = 50) -> List[Dict]:
        """Get forecasts awaiting resolution (for a cron/manual resolution flow)."""
        cursor = self._collection.find(
            {"resolved": False}, {"_id": 0}
        ).sort("target_date", 1).limit(limit)
        return await cursor.to_list(length=limit)
