"""Data models for the Weather Trading strategy.

Follows the same conventions as arb_models.py / sniper_models.py:
Pydantic BaseModel, new_id(), utc_now(), clear enums.

Key architectural difference: weather markets are MULTI-OUTCOME (5-7 buckets),
not binary YES/NO pairs. Each bucket has its own token_id and market price.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
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


class WeatherMarketType(str, Enum):
    TEMPERATURE = "temperature"
    PRECIPITATION = "precipitation"
    SNOWFALL = "snowfall"
    WIND = "wind"


# ---- Configuration ----

class WeatherConfig(BaseModel):
    # Scan timing
    scan_interval: float = 60.0                          # seconds between EV scans
    classification_refresh_interval: float = 300.0       # seconds between market re-classification
    forecast_refresh_interval: float = 1800.0            # seconds between forecast API calls

    # Edge thresholds
    min_edge_bps: float = 500.0                          # 5% minimum edge (was 3%)

    # Filters
    min_liquidity: float = 200.0
    min_confidence: float = 0.55                         # 55% confidence floor (was 40%)
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
    max_weather_positions: int = 25                      # hard cap on total open weather positions
    cooldown_seconds: float = 1800.0                     # 30 min cooldown per market
    kelly_scale: float = 0.25                            # quarter-Kelly

    # Fees
    maker_taker_rate: float = 0.002

    # Alert settings
    weather_alerts_enabled: bool = True
    min_weather_alert_edge_bps: float = 200.0              # min edge change to trigger alert
    min_weather_alert_price_move_bps: float = 300.0         # min price move (bps) to trigger alert
    weather_alert_cooldown_seconds: float = 300.0           # 5 min debounce per market alert key

    # Rolling calibration settings
    rolling_calibration_enabled: bool = True
    rolling_min_samples: int = 15                           # min resolved records per group to use
    rolling_recalc_interval_hours: float = 168.0            # recalculate weekly (168h)
    rolling_recalc_after_n_records: int = 20                # OR recalculate after N new records

    # Liquidity score filter
    min_liquidity_score: float = 35.0                       # 0-100, skip buckets scoring below this


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
    resolution_type: str           # "daily_high", "daily_precip", "daily_snow", "daily_wind"
    market_type: WeatherMarketType = WeatherMarketType.TEMPERATURE
    unit: str = "F"                # "F", "in", "cm", "mph"
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
    forecast_precip_in: Optional[float] = None    # daily precipitation in inches
    forecast_snow_in: Optional[float] = None      # daily snowfall in inches
    forecast_wind_mph: Optional[float] = None     # max wind speed in mph
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


class RollingCalibration(BaseModel):
    """Rolling live calibration computed from resolved forecast_accuracy records."""
    station_id: str
    source: str = "rolling"                     # always "rolling"
    calibrated_at: str = Field(default_factory=utc_now)
    sample_count: int = 0
    sigma_by_lead_hours: Dict[str, float] = Field(default_factory=dict)
    seasonal_factors: Dict[str, float] = Field(default_factory=dict)
    station_type_factor: float = 1.0
    mean_bias_f: float = 0.0
    # Per-group detail
    bias_by_lead_hours: Dict[str, float] = Field(default_factory=dict)   # lead bracket → mean bias
    bias_by_season: Dict[str, float] = Field(default_factory=dict)       # season → mean bias
    samples_by_lead_hours: Dict[str, int] = Field(default_factory=dict)  # lead bracket → count
    samples_by_season: Dict[str, int] = Field(default_factory=dict)      # season → count
    coverage_start: Optional[str] = None       # earliest target_date in window
    coverage_end: Optional[str] = None         # latest target_date in window
    records_since_last_update: int = 0         # new records since last calc


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
    liquidity_score: float = 0.0
    quality_score: float = 0.0
    market_type: str = "temperature"
    explanation: Dict[str, Any] = Field(default_factory=dict)
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


# ---- Forecast Accuracy Record ----

class ForecastAccuracyRecord(BaseModel):
    """Resolved forecast outcome for calibration tracking."""
    id: str = Field(default_factory=new_id)
    station_id: str
    city: str
    target_date: str                           # ISO date
    forecast_high_f: float                     # model's predicted daily high
    observed_high_f: Optional[float] = None    # actual observed high (null if not yet resolved)
    forecast_error_f: Optional[float] = None   # observed - forecast (positive = model underestimated)
    abs_error_f: Optional[float] = None        # |forecast_error_f|
    sigma_used: float                          # sigma value at time of signal
    lead_hours: float                          # forecast lead time
    calibration_source: str = "default_sigma_table"  # "default_sigma_table" or "historical_calibration"
    winning_bucket: Optional[str] = None       # bucket label that contained the actual outcome
    model_bucket_prob: Optional[float] = None  # model probability assigned to winning bucket
    market_bucket_price: Optional[float] = None  # market price of winning bucket at signal time
    bucket_count: int = 0                      # total buckets in the event
    resolved: bool = False
    recorded_at: str = Field(default_factory=utc_now)
    resolved_at: Optional[str] = None


# ---- Weather Alert ----

class WeatherAlertType(str, Enum):
    PRICE_MOVE = "price_move"
    EDGE_CHANGE = "edge_change"
    BECAME_TRADABLE = "became_tradable"
    NO_LONGER_TRADABLE = "no_longer_tradable"
    SPREAD_DEVIATION = "spread_deviation"


class WeatherAlert(BaseModel):
    id: str = Field(default_factory=new_id)
    alert_type: WeatherAlertType
    station_id: str
    city: str = ""
    target_date: str
    bucket_label: str = ""
    token_id: str = ""
    model_prob: float = 0.0
    market_price: float = 0.0
    edge_bps: float = 0.0
    confidence: float = 0.0
    price_move_bps: float = 0.0
    detail: str = ""
    timestamp: str = Field(default_factory=utc_now)


# ---- Shadow Mode Config Presets ----

SHADOW_CONFIG_OVERRIDES = {
    "min_edge_bps": 500.0,          # tighter threshold (up from 300)
    "kelly_scale": 0.15,            # more conservative sizing (down from 0.25)
    "max_signal_size": 5.0,         # smaller max size (down from 8.0)
    "max_concurrent_signals": 4,    # fewer concurrent (down from 8)
    "max_stale_market_seconds": 600.0,  # more tolerant for non-WebSocket markets (up from 120)
    "cooldown_seconds": 2400.0,     # longer cooldown (up from 1800)
    "default_size": 2.0,            # smaller base size (down from 3.0)
}
