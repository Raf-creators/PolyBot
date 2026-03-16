"""Data models for the Crypto Sniper strategy.

Follows the same conventions as arb_models.py:
Pydantic BaseModel, new_id(), utc_now(), clear enums.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from models import utc_now, new_id


class SniperConfig(BaseModel):
    # Scan timing
    scan_interval: float = 5.0
    classification_refresh_interval: float = 30.0

    # Edge thresholds
    min_edge_bps: float = 200.0

    # Filters
    min_liquidity: float = 500.0
    min_confidence: float = 0.30
    max_spread: float = 0.10
    max_stale_age_seconds: float = 60.0
    min_tte_seconds: float = 30.0
    max_tte_seconds: float = 28800.0  # 8h — supports 4h+ updown windows

    # Volatility
    vol_lookback_minutes: float = 60.0
    vol_sample_interval: float = 5.0
    vol_min_samples: int = 30
    vol_floor: float = 0.10

    # Momentum
    momentum_lookback_seconds: float = 300.0
    momentum_weight: float = 0.05

    # Sizing
    default_size: float = 3.0
    max_signal_size: float = 8.0
    max_concurrent_signals: int = 5
    cooldown_seconds: float = 60.0

    # Fees
    maker_taker_rate: float = 0.002


class CryptoMarketClassification(BaseModel):
    """Cached parse result for one crypto market pair."""
    condition_id: str
    asset: str                  # "BTC" or "ETH"
    direction: str              # "above" or "below"
    strike: float               # 0 = updown (use spot at eval time)
    expiry_utc: str             # ISO datetime of resolution
    yes_token_id: str
    no_token_id: str
    question: str
    market_type: str = "threshold"  # "updown", "threshold", "range"
    window: Optional[str] = None    # "5m", "15m", "1h", "4h" for updown
    classified_at: str = Field(default_factory=utc_now)


class SniperSignalStatus(str, Enum):
    GENERATED = "generated"
    SUBMITTED = "submitted"
    FILLED = "filled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class SniperSignal(BaseModel):
    id: str = Field(default_factory=new_id)
    condition_id: str
    asset: str
    direction: str
    strike: float
    expiry_utc: str
    spot_price: float
    market_price: float         # Polymarket Yes mid
    fair_price: float           # model output
    edge_bps: float
    volatility: float           # annualized sigma used
    time_to_expiry_seconds: float
    momentum: float
    confidence: float
    side: str                   # "buy_yes" or "buy_no"
    token_id: str               # token to trade
    recommended_size: float
    is_tradable: bool
    rejection_reason: Optional[str] = None
    detected_at: str = Field(default_factory=utc_now)


class SniperExecution(BaseModel):
    id: str = Field(default_factory=new_id)
    signal_id: str
    condition_id: str
    question: str
    asset: str
    side: str
    order_id: str
    status: SniperSignalStatus = SniperSignalStatus.SUBMITTED
    entry_price: Optional[float] = None
    target_edge_bps: float
    size: float
    submitted_at: str = Field(default_factory=utc_now)
    filled_at: Optional[str] = None
