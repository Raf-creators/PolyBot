from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from models import utc_now, new_id


class ArbPairStatus(str, Enum):
    DETECTED = "detected"
    ELIGIBLE = "eligible"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    CLOSED = "closed"
    REJECTED = "rejected"


class ArbConfig(BaseModel):
    scan_interval: float = 10.0
    min_net_edge_bps: float = 15.0            # absolute floor — never trade below this
    min_liquidity: float = 200.0
    min_confidence: float = 0.25
    max_stale_age_seconds: float = 300.0      # legacy — kept for risk engine compat
    max_arb_size: float = 15.0
    max_concurrent_arbs: int = 15
    default_size: float = 5.0
    # Edge-scaled sizing: bigger edge → bigger position
    min_size: float = 2.0                     # minimum position per leg
    edge_scale_factor: float = 0.5            # size = min_size + edge_bps * factor / 100
    max_exposure_per_market: float = 30.0     # max $ deployed per single condition_id
    # Fee model params
    maker_taker_rate: float = 0.002  # 0.2% per leg on trade value
    resolution_fee_rate: float = 0.02  # 2% on gross profit at resolution
    # Slippage model params
    slippage_base_bps: float = 5.0
    # Execution penalty params
    execution_penalty_base_bps: float = 3.0
    # Safety: kill-switch on repeated failures
    max_consecutive_failures: int = 5
    failure_cooldown_seconds: float = 300.0
    # Dynamic threshold: staleness-adjusted edge floor
    staleness_edge_base_bps: float = 15.0     # min edge for fresh data (<60s)
    staleness_edge_per_minute_bps: float = 6.0  # addl bps per minute of staleness
    hard_max_stale_seconds: float = 2400.0    # absolute hard reject (40 min)
    # Dynamic threshold: liquidity-adjusted edge buffer
    liquidity_deep_threshold: float = 2000.0  # above this = no liq buffer
    liquidity_mid_threshold: float = 500.0    # above this = half buffer
    liquidity_buffer_thin_bps: float = 15.0   # full buffer for thin liquidity (<500)


class ArbOpportunity(BaseModel):
    id: str = Field(default_factory=new_id)
    arb_type: str = "binary"  # "binary" | "multi_outcome" | "cross_market"
    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
    total_cost: float = 0.0           # actual cost to acquire all legs
    expected_profit: float = 0.0       # 1.0 - total_cost (for binary/multi)
    gross_edge_bps: float
    estimated_fees_bps: float
    estimated_slippage_bps: float
    execution_penalty_bps: float
    net_edge_bps: float
    liquidity_estimate: float
    confidence_score: float
    recommended_size: float
    is_tradable: bool
    rejection_reason: Optional[str] = None
    detected_at: str = Field(default_factory=utc_now)
    execution_id: Optional[str] = None
    # Multi-outcome: list of all leg token_ids and prices
    all_leg_token_ids: List[str] = Field(default_factory=list)
    all_leg_prices: List[float] = Field(default_factory=list)


class ArbExecution(BaseModel):
    id: str = Field(default_factory=new_id)
    arb_type: str = "binary"
    opportunity_id: str
    condition_id: str
    question: str
    status: ArbPairStatus = ArbPairStatus.SUBMITTED
    yes_order_id: str
    no_order_id: str
    yes_fill_price: Optional[float] = None
    no_fill_price: Optional[float] = None
    target_edge_bps: float
    realized_edge_bps: Optional[float] = None
    size: float
    submitted_at: str = Field(default_factory=utc_now)
    completed_at: Optional[str] = None
    invalidation_reason: Optional[str] = None
    # Multi-leg tracking
    all_order_ids: List[str] = Field(default_factory=list)
    all_fill_prices: List[Optional[float]] = Field(default_factory=list)
    legs_filled: int = 0
    legs_total: int = 2
