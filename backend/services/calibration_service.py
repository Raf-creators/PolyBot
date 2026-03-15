"""Historical calibration bootstrap for WeatherTrader sigma values.

Fetches historical forecast vs observed temperature data from Open-Meteo,
computes empirical forecast error distributions per station/lead-time/season,
and stores calibrated SigmaCalibration records in MongoDB.

Data sources:
  - Historical Forecast API: what the model predicted (best available forecast)
  - Historical Weather API:  what actually happened (observed)

The calibration only writes to `weather_sigma_calibration` collection.
It does NOT modify any execution, strategy, or forecast_accuracy data.
"""

import asyncio
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from models import utc_now
from engine.strategies.weather_models import SigmaCalibration, StationType, Season
from engine.strategies.weather_parser import STATION_REGISTRY
from engine.strategies.weather_pricing import get_season

logger = logging.getLogger(__name__)

COLLECTION = "weather_sigma_calibration"

# Open-Meteo API endpoints
HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
HISTORICAL_WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"

# Calibration settings
DEFAULT_LOOKBACK_DAYS = 90
MIN_SAMPLES_PER_BRACKET = 5
LEAD_BRACKETS = {
    "0_24":    (0, 24),
    "24_48":   (24, 48),
    "48_72":   (48, 72),
    "72_120":  (72, 120),
    "120_168": (120, 168),
}
# Approximate lead-time scaling factors (sqrt of midpoint ratio)
# Used to extrapolate from base error when we lack direct lead-time data
LEAD_SCALE_FACTORS = {
    "0_24":    1.0,
    "24_48":   1.41,   # sqrt(2)
    "48_72":   1.73,   # sqrt(3)
    "72_120":  2.0,    # sqrt(4)
    "120_168": 2.45,   # sqrt(6)
}

# Temperature unit conversion
def _c_to_f(c: float) -> float:
    return round(c * 9.0 / 5.0 + 32.0, 2)


class CalibrationService:
    """Fetches historical data and computes sigma calibration per station."""

    def __init__(self, db):
        self._db = db
        self._collection = db[COLLECTION]
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_run: Optional[str] = None
        self._last_status: str = "not_run"

    async def ensure_indexes(self):
        await self._collection.create_index("station_id", unique=True)

    async def run_calibration(
        self,
        station_ids: Optional[List[str]] = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> Dict[str, Any]:
        """Run the full calibration pipeline for all (or specified) stations.

        Returns a summary dict with per-station results.
        """
        self._last_status = "running"
        results = {}
        errors = []

        if not station_ids:
            station_ids = list(STATION_REGISTRY.keys())

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "PolymarketEdgeOS/1.0 (calibration)"},
        )

        try:
            for station_id in station_ids:
                station = STATION_REGISTRY.get(station_id)
                if not station:
                    errors.append(f"Unknown station: {station_id}")
                    continue

                try:
                    result = await self._calibrate_station(station_id, station, lookback_days)
                    results[station_id] = result
                    # Brief delay to be polite to Open-Meteo
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"[CALIBRATION] Failed for {station_id}: {e}")
                    errors.append(f"{station_id}: {e}")
                    results[station_id] = {"status": "error", "error": str(e)}
        finally:
            await self._session.close()
            self._session = None

        self._last_run = utc_now()
        self._last_status = "completed"

        return {
            "status": "completed",
            "stations_processed": len(results),
            "stations_succeeded": sum(1 for r in results.values() if r.get("status") == "calibrated"),
            "stations_failed": sum(1 for r in results.values() if r.get("status") == "error"),
            "errors": errors,
            "results": results,
            "run_at": self._last_run,
        }

    async def _calibrate_station(
        self, station_id: str, station, lookback_days: int,
    ) -> Dict[str, Any]:
        """Calibrate sigma for a single station."""
        end_date = (datetime.now(timezone.utc) - timedelta(days=2)).date()
        start_date = end_date - timedelta(days=lookback_days)

        logger.info(f"[CALIBRATION] Fetching data for {station_id} ({start_date} to {end_date})")

        # Fetch historical forecasts (what model predicted)
        forecast_highs = await self._fetch_historical_forecasts(
            station.latitude, station.longitude, str(start_date), str(end_date),
        )

        # Fetch historical observations (what actually happened)
        observed_highs = await self._fetch_historical_observations(
            station.latitude, station.longitude, str(start_date), str(end_date),
        )

        if not forecast_highs or not observed_highs:
            return {"status": "error", "error": "No data returned from Open-Meteo"}

        # Align dates and compute errors
        errors_by_date = {}
        for d, fcst in forecast_highs.items():
            obs = observed_highs.get(d)
            if obs is not None and fcst is not None:
                errors_by_date[d] = fcst - obs  # positive = forecast overestimated

        if len(errors_by_date) < MIN_SAMPLES_PER_BRACKET:
            return {"status": "insufficient_data", "sample_count": len(errors_by_date)}

        # Compute base sigma (std dev of forecast errors at 0-24h)
        error_values = list(errors_by_date.values())
        n = len(error_values)
        mean_err = sum(error_values) / n
        variance = sum((e - mean_err) ** 2 for e in error_values) / n
        base_sigma = math.sqrt(variance) if variance > 0 else 1.0

        # Compute sigma by lead bracket using scaling factors
        sigma_by_lead = {}
        for bracket, scale in LEAD_SCALE_FACTORS.items():
            sigma_by_lead[bracket] = round(base_sigma * scale, 4)

        # Compute seasonal factors
        seasonal_errors = defaultdict(list)
        for d_str, err in errors_by_date.items():
            month = int(d_str[5:7])
            season = get_season(month)
            seasonal_errors[season.value].append(err)

        seasonal_factors = {}
        for season_name in ["winter", "spring", "summer", "fall"]:
            errs = seasonal_errors.get(season_name, [])
            if len(errs) >= 3:
                s_var = sum((e - sum(errs) / len(errs)) ** 2 for e in errs) / len(errs)
                s_sigma = math.sqrt(s_var) if s_var > 0 else base_sigma
                seasonal_factors[season_name] = round(s_sigma / base_sigma, 4) if base_sigma > 0 else 1.0
            else:
                seasonal_factors[season_name] = 1.0

        # Station type factor
        station_type_factor = 0.90 if station.station_type == StationType.COASTAL else 1.10

        # Build calibration record
        calibration = SigmaCalibration(
            station_id=station_id,
            sample_count=n,
            sigma_by_lead_hours=sigma_by_lead,
            seasonal_factors=seasonal_factors,
            station_type_factor=station_type_factor,
            mean_bias_f=round(mean_err, 4),
        )

        # Persist to MongoDB (upsert)
        doc = calibration.model_dump()
        await self._collection.update_one(
            {"station_id": station_id},
            {"$set": doc},
            upsert=True,
        )

        logger.info(
            f"[CALIBRATION] {station_id}: samples={n}, base_sigma={base_sigma:.2f}F, "
            f"bias={mean_err:+.2f}F, 0-24h={sigma_by_lead['0_24']:.2f}F, "
            f"48-72h={sigma_by_lead['48_72']:.2f}F"
        )

        return {
            "status": "calibrated",
            "sample_count": n,
            "base_sigma_f": round(base_sigma, 4),
            "mean_bias_f": round(mean_err, 4),
            "sigma_by_lead": sigma_by_lead,
            "seasonal_factors": seasonal_factors,
            "date_range": f"{start_date} to {end_date}",
        }

    async def _fetch_historical_forecasts(
        self, lat: float, lon: float, start: str, end: str,
    ) -> Dict[str, float]:
        """Fetch historical daily max temperature forecasts from Open-Meteo."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "timezone": "UTC",
        }
        try:
            async with self._session.get(HISTORICAL_FORECAST_URL, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"[CALIBRATION] Historical forecast API {resp.status}: {body[:200]}")
                    return {}
                data = await resp.json()
                daily = data.get("daily", {})
                dates = daily.get("time", [])
                temps = daily.get("temperature_2m_max", [])
                return {d: t for d, t in zip(dates, temps) if t is not None}
        except Exception as e:
            logger.error(f"[CALIBRATION] Historical forecast fetch error: {e}")
            return {}

    async def _fetch_historical_observations(
        self, lat: float, lon: float, start: str, end: str,
    ) -> Dict[str, float]:
        """Fetch historical daily observed max temperature from Open-Meteo archive."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "timezone": "UTC",
        }
        try:
            async with self._session.get(HISTORICAL_WEATHER_URL, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"[CALIBRATION] Historical weather API {resp.status}: {body[:200]}")
                    return {}
                data = await resp.json()
                daily = data.get("daily", {})
                dates = daily.get("time", [])
                temps = daily.get("temperature_2m_max", [])
                return {d: t for d, t in zip(dates, temps) if t is not None}
        except Exception as e:
            logger.error(f"[CALIBRATION] Historical weather fetch error: {e}")
            return {}

    async def get_all_calibrations(self) -> Dict[str, SigmaCalibration]:
        """Load all calibration records from MongoDB."""
        cursor = self._collection.find({}, {"_id": 0})
        calibrations = {}
        async for doc in cursor:
            try:
                cal = SigmaCalibration(**doc)
                calibrations[cal.station_id] = cal
            except Exception as e:
                logger.warning(f"[CALIBRATION] Failed to parse record: {e}")
        return calibrations

    async def get_calibration(self, station_id: str) -> Optional[SigmaCalibration]:
        """Load a single station's calibration from MongoDB."""
        doc = await self._collection.find_one({"station_id": station_id}, {"_id": 0})
        if doc:
            return SigmaCalibration(**doc)
        return None

    async def get_status(self) -> Dict[str, Any]:
        """Get overall calibration status."""
        count = await self._collection.count_documents({})
        calibrations = await self.get_all_calibrations()

        station_info = {}
        for sid, cal in calibrations.items():
            station_info[sid] = {
                "station_id": sid,
                "sample_count": cal.sample_count,
                "calibrated_at": cal.calibrated_at,
                "base_sigma_0_24": cal.sigma_by_lead_hours.get("0_24"),
                "base_sigma_48_72": cal.sigma_by_lead_hours.get("48_72"),
                "mean_bias_f": cal.mean_bias_f,
                "ready": cal.sample_count >= 30,
            }

        return {
            "total_stations_calibrated": count,
            "total_stations_registered": len(STATION_REGISTRY),
            "last_run": self._last_run,
            "last_status": self._last_status,
            "stations": station_info,
        }
