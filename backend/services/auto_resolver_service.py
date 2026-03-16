"""Automated Forecast Resolution Service.

Periodically scans forecast_accuracy for unresolved records, fetches the
observed daily-high temperature from the Open-Meteo Archive API once the
target day is complete, and resolves them.

Resolved records are immediately available to:
  - Global Analytics (reads forecast_accuracy)
  - Rolling Calibration (reads forecast_accuracy)

Safety:
  - Never overwrites already-resolved records
  - Never fabricates observed data — uses real Open-Meteo archive only
  - Skips records whose target_date hasn't ended yet
  - Graceful on API errors: logs and retries next cycle
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Dict, List, Optional

import aiohttp

from engine.strategies.weather_parser import STATION_REGISTRY

logger = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class AutoResolverService:
    """Background service that auto-resolves pending forecast_accuracy records."""

    def __init__(
        self,
        db,
        forecast_accuracy_service,
        rolling_calibration_service=None,
        interval_hours: float = 6.0,
    ):
        self._db = db
        self._accuracy_svc = forecast_accuracy_service
        self._rolling_cal_svc = rolling_calibration_service
        self._interval_seconds = interval_hours * 3600
        self._collection = db["forecast_accuracy"]

        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None

        # Health / observability
        self._health = {
            "running": False,
            "interval_hours": interval_hours,
            "total_runs": 0,
            "total_resolved": 0,
            "total_skipped": 0,
            "total_errors": 0,
            "last_run_at": None,
            "last_run_resolved": 0,
            "last_run_pending": 0,
            "last_run_duration_s": 0,
            "last_error": None,
            "pending_records": 0,
        }

    async def start(self):
        """Start the background resolver loop."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            headers={"User-Agent": "PolymarketEdgeOS/1.0 (auto-resolver)"},
        )
        self._health["running"] = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"[AUTO-RESOLVER] Started — interval={self._health['interval_hours']}h"
        )

    async def stop(self):
        """Stop the background loop and close HTTP session."""
        self._health["running"] = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("[AUTO-RESOLVER] Stopped")

    @property
    def health(self) -> dict:
        return dict(self._health)

    async def run_once(self) -> dict:
        """Execute one resolution pass. Returns summary dict."""
        start = asyncio.get_event_loop().time()
        resolved_count = 0
        skipped = 0
        errors = 0

        try:
            pending = await self._get_pending_records()
            self._health["last_run_pending"] = len(pending)
            self._health["pending_records"] = len(pending)

            if not pending:
                logger.info("[AUTO-RESOLVER] No pending records to resolve")
                return {"resolved": 0, "pending": 0, "skipped": 0, "errors": 0}

            # Group by station for efficient API calls
            by_station: Dict[str, list] = {}
            for rec in pending:
                sid = rec["station_id"]
                by_station.setdefault(sid, []).append(rec)

            for station_id, records in by_station.items():
                station = STATION_REGISTRY.get(station_id)
                if not station:
                    logger.warning(f"[AUTO-RESOLVER] Unknown station {station_id}, skipping {len(records)} records")
                    skipped += len(records)
                    continue

                # Collect all target dates for this station
                dates = sorted(set(r["target_date"] for r in records))

                # Fetch observed highs in one API call
                observed = await self._fetch_observed_highs(
                    station.latitude, station.longitude, dates[0], dates[-1]
                )

                for rec in records:
                    td = rec["target_date"]
                    obs_high = observed.get(td)
                    if obs_high is None:
                        logger.debug(f"[AUTO-RESOLVER] No observed data for {station_id}:{td}")
                        skipped += 1
                        continue

                    try:
                        await self._accuracy_svc.resolve_forecast(
                            station_id=station_id,
                            target_date=td,
                            observed_high_f=obs_high,
                        )
                        resolved_count += 1
                    except Exception as e:
                        logger.error(f"[AUTO-RESOLVER] Error resolving {station_id}:{td}: {e}")
                        errors += 1

                # Rate limit between stations
                await asyncio.sleep(0.5)

            # Trigger rolling calibration refresh if records were resolved
            if resolved_count > 0 and self._rolling_cal_svc:
                try:
                    await self._rolling_cal_svc.run_rolling_calibration()
                    logger.info(f"[AUTO-RESOLVER] Triggered rolling calibration refresh after {resolved_count} resolutions")
                except Exception as e:
                    logger.error(f"[AUTO-RESOLVER] Rolling calibration refresh failed: {e}")

        except Exception as e:
            logger.error(f"[AUTO-RESOLVER] Run failed: {e}")
            self._health["last_error"] = str(e)
            errors += 1

        duration = asyncio.get_event_loop().time() - start
        self._health["total_runs"] += 1
        self._health["total_resolved"] += resolved_count
        self._health["total_skipped"] += skipped
        self._health["total_errors"] += errors
        self._health["last_run_at"] = datetime.now(timezone.utc).isoformat()
        self._health["last_run_resolved"] = resolved_count
        self._health["last_run_duration_s"] = round(duration, 2)

        # Update pending count after resolution
        remaining = await self._collection.count_documents({"resolved": {"$ne": True}})
        self._health["pending_records"] = remaining

        logger.info(
            f"[AUTO-RESOLVER] Run complete: resolved={resolved_count} skipped={skipped} "
            f"errors={errors} duration={duration:.1f}s"
        )

        return {
            "resolved": resolved_count,
            "pending": remaining,
            "skipped": skipped,
            "errors": errors,
            "duration_s": round(duration, 2),
        }

    async def _loop(self):
        """Background loop — runs first pass after 30s, then every interval."""
        await asyncio.sleep(30)  # Initial delay to let services settle
        while self._health["running"]:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[AUTO-RESOLVER] Loop error: {e}")
                self._health["last_error"] = str(e)
            await asyncio.sleep(self._interval_seconds)

    async def _get_pending_records(self) -> List[dict]:
        """Find unresolved records whose target_date has passed (day is complete)."""
        # Only resolve records from completed days (yesterday or earlier in UTC)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        cursor = self._collection.find(
            {
                "resolved": {"$ne": True},
                "target_date": {"$lte": yesterday},
            },
            {"_id": 0},
        ).sort("target_date", 1).limit(100)
        return await cursor.to_list(length=100)

    async def _fetch_observed_highs(
        self, lat: float, lon: float, start_date: str, end_date: str
    ) -> Dict[str, float]:
        """Fetch observed daily max temperatures from Open-Meteo Archive API."""
        if not self._session:
            return {}

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
            "timezone": "UTC",
        }
        try:
            async with self._session.get(OPEN_METEO_ARCHIVE_URL, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"[AUTO-RESOLVER] Open-Meteo archive {resp.status}: {body[:200]}")
                    return {}
                data = await resp.json()
                daily = data.get("daily", {})
                dates = daily.get("time", [])
                temps = daily.get("temperature_2m_max", [])
                result = {d: t for d, t in zip(dates, temps) if t is not None}
                logger.debug(f"[AUTO-RESOLVER] Got {len(result)} observed highs for ({lat},{lon}) {start_date}→{end_date}")
                return result
        except Exception as e:
            logger.error(f"[AUTO-RESOLVER] Open-Meteo archive fetch error: {e}")
            return {}
