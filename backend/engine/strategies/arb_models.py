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
    min_net_edge_bps: float = 30.0
    min_liquidity: float = 500.0
    min_confidence: float = 0.25
    max_stale_age_seconds: float = 300.0
    max_arb_size: float = 10.0
    max_concurrent_arbs: int = 5
    default_size: float = 5.0
    # Fee model params
    maker_taker_rate: float = 0.002  # 0.2% per leg on trade value
    resolution_fee_rate: float = 0.02  # 2% on gross profit at resolution
    # Slippage model params
    slippage_base_bps: float = 5.0
    # Execution penalty params
    execution_penalty_base_bps: float = 3.0


class ArbOpportunity(BaseModel):
    id: str = Field(default_factory=new_id)
    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
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


class ArbExecution(BaseModel):
    id: str = Field(default_factory=new_id)
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
