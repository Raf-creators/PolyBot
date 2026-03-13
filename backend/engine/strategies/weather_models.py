"""Data models for the Weather Trading strategy.

Follows the same conventions as arb_models.py / sniper_models.py:
Pydantic BaseModel, new_id(), utc_now(), clear enums.

Key architectural difference: weather markets are MULTI-OUTCOME (5-7 buckets),
not binary YES/NO pairs. Each bucket has its own token_id and market price.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum
from models import utc_now, new_id
import math


# ---- Enums ----

class WeatherSignalStatus(str, Enum):
    GENERATED = "generated"
    SUBMITTED = "submitted"
    FILLED = "filled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class StationType(str, Enum):
    COASTAL = "coastal"
    INLAND = "inland"


class Season(str, Enum):
    WINTER = "winter"
    SPRING = "spring"
    SUMMER = "summer"
    FALL = "fall"


# ---- Configuration ----

class WeatherConfig(BaseModel):
    # Scan timing
    scan_interval: float = 60.0                          # seconds between EV scans
    classification_refresh_interval: float = 300.0       # seconds between market re-classification
    forecast_refresh_interval: float = 1800.0            # seconds between forecast API calls

    # Edge thresholds
    min_edge_bps: float = 300.0                          # 3% minimum edge

    # Filters
    min_liquidity: float = 200.0
    min_confidence: float = 0.40
    max_spread_sum: float = 0.30                         # max deviation of bucket price sum from 1.0
    max_stale_forecast_minutes: float = 120.0            # reject if forecast older than 2h
    max_stale_market_seconds: float = 120.0              # reject if market data older than 2min
    min_hours_to_resolution: float = 4.0                 # don't trade within 4h of resolution
    max_hours_to_resolution: float = 168.0               # don't trade beyond 7-day horizon
    max_sigma: float = 8.0                               # skip if calibrated sigma > 8F

    # Sizing
    default_size: float = 3.0
    max_signal_size: float = 8.0
    max_buckets_per_market: int = 2                      # max buckets to trade per market
    max_concurrent_signals: int = 8
    cooldown_seconds: float = 1800.0                     # 30 min cooldown per market
    kelly_scale: float = 0.25                            # quarter-Kelly

    # Fees
    maker_taker_rate: float = 0.002


# ---- Station Info ----

class StationInfo(BaseModel):
    """Metadata for a weather observation station (airport ASOS/AWOS)."""
    station_id: str                # ICAO code, e.g. "KLGA"
    city: str                      # "New York City"
    state: str                     # "NY"
    latitude: float
    longitude: float
    elevation_ft: float
    timezone: str                  # IANA timezone, e.g. "America/New_York"
    station_type: StationType
    wunderground_slug: str         # e.g. "us/ny/new-york-city/KLGA"
    aliases: List[str]             # ["NYC", "New York", "LaGuardia"]


# ---- Temperature Bucket ----

class TempBucket(BaseModel):
    """One temperature outcome bucket in a multi-outcome weather market.

    Bounds are in whole degrees Fahrenheit (matching Polymarket resolution).
    lower_bound = -inf is represented as None (open lower).
    upper_bound = +inf is represented as None (open upper).
    """
    label: str                     # original outcome string, e.g. "43-44F"
    token_id: str                  # Polymarket token for this outcome
    lower_bound: Optional[float] = None   # None = negative infinity
    upper_bound: Optional[float] = None   # None = positive infinity

    @property
    def is_lower_open(self) -> bool:
        return self.lower_bound is None

    @property
    def is_upper_open(self) -> bool:
        return self.upper_bound is None

    @property
    def midpoint(self) -> Optional[float]:
        """Midpoint of the bucket, or None if unbounded on both sides."""
        if self.lower_bound is not None and self.upper_bound is not None:
            return (self.lower_bound + self.upper_bound) / 2.0
        return None


# ---- Market Classification ----

class WeatherMarketClassification(BaseModel):
    """Cached parse result for one multi-outcome weather market."""
    condition_id: str
    station_id: str                # resolved ICAO code
    city: str
    target_date: str               # ISO date string, e.g. "2026-03-15"
    resolution_type: str           # always "daily_high" for now
    buckets: List[TempBucket]
    question: str
    classified_at: str = Field(default_factory=utc_now)


# ---- Forecast Snapshot ----

class ForecastSnapshot(BaseModel):
    """Cached forecast data for one station and target date."""
    station_id: str
    target_date: str               # ISO date
    forecast_high_f: float         # predicted daily high in Fahrenheit
    forecast_low_f: Optional[float] = None
    source: str = "open_meteo"     # "open_meteo", "nws", "blended"
    fetched_at: str = Field(default_factory=utc_now)
    lead_hours: float              # hours between fetch time and target date end
    raw_hourly: Optional[List[float]] = None   # hourly temps if available


# ---- Calibration ----

class SigmaCalibration(BaseModel):
    """Calibrated forecast standard deviation for a station."""
    station_id: str
    calibrated_at: str = Field(default_factory=utc_now)
    sample_count: int = 0
    sigma_by_lead_hours: Dict[str, float] = Field(default_factory=lambda: {
        "0_24": 1.8,
        "24_48": 2.7,
        "48_72": 3.4,
        "72_120": 4.8,
        "120_168": 6.2,
    })
    seasonal_factors: Dict[str, float] = Field(default_factory=lambda: {
        "winter": 1.15,
        "spring": 1.0,
        "summer": 0.88,
        "fall": 1.02,
    })
    station_type_factor: float = 1.0   # 0.90 coastal, 1.10 inland
    mean_bias_f: float = 0.0           # systematic bias in degrees F


# ---- Bucket Probability Result ----

class BucketProbability(BaseModel):
    """Model probability output for one bucket."""
    label: str
    token_id: str
    model_prob: float              # P(bucket) from distribution model
    market_price: float            # current Polymarket price
    edge_bps: float                # (model_prob - market_price) * 10000
    is_tradable: bool = False
    rejection_reason: Optional[str] = None


# ---- Signal ----

class WeatherSignal(BaseModel):
    """Trading signal for one bucket in a weather market."""
    id: str = Field(default_factory=new_id)
    condition_id: str
    station_id: str
    target_date: str
    bucket_label: str
    token_id: str
    forecast_high_f: float
    sigma: float
    lead_hours: float
    model_prob: float
    market_price: float
    edge_bps: float
    confidence: float
    recommended_size: float
    is_tradable: bool
    rejection_reason: Optional[str] = None
    detected_at: str = Field(default_factory=utc_now)


# ---- Execution ----

class WeatherExecution(BaseModel):
    """Execution record for a weather bucket trade."""
    id: str = Field(default_factory=new_id)
    signal_id: str
    condition_id: str
    station_id: str
    target_date: str
    bucket_label: str
    order_id: str
    status: WeatherSignalStatus = WeatherSignalStatus.SUBMITTED
    entry_price: Optional[float] = None
    target_edge_bps: float
    size: float
    submitted_at: str = Field(default_factory=utc_now)
    filled_at: Optional[str] = None
