import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from models import Event, EventType, OrderRecord, OrderStatus

logger = logging.getLogger(__name__)

# ---- Strategy Classification ----

WEATHER_KEYWORDS = {"temperature", "highest temp", "lowest temp", "weather", "°f", "fahrenheit", "°c"}


def classify_strategy(pos_or_order) -> str:
    """Classify a position/order into a strategy bucket: weather / crypto / arb / unknown."""
    sid = getattr(pos_or_order, "strategy_id", "") or ""
    if sid == "weather_trader":
        return "weather"
    if sid == "crypto_sniper":
        return "crypto"
    if sid == "arb_scanner":
        return "arb"
    if sid and sid != "unknown":
        return sid  # pass through unknown strategies

    # Fallback: keyword matching for legacy positions without strategy_id
    q = (getattr(pos_or_order, "market_question", "") or "").lower()
    if any(kw in q for kw in WEATHER_KEYWORDS):
        return "weather"
    if any(kw in q for kw in ("btc", "bitcoin", "eth", "ethereum", "up or down")):
        return "crypto"
    return "unknown"


def estimate_time_to_resolution(market) -> float:
    """Estimate hours until market resolves. Lower = faster capital turnover."""
    if not market:
        return 999.0
    end_date_str = getattr(market, "end_date", None)
    if not end_date_str:
        return 999.0
    try:
        end = datetime.fromisoformat(str(end_date_str).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours = max(0, (end - now).total_seconds() / 3600)
        return round(hours, 1)
    except Exception:
        return 999.0


class RiskEngine:
    """Gates all order requests with per-strategy reserved slot system."""

    def __init__(self):
        self._state = None
        self._bus = None
        self._running = False
        self._slot_blocks = defaultdict(int)

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True
        self._bus.on(EventType.ORDER_REQUEST, self._on_order_request)
        logger.info("Risk engine started — per-strategy slot system active")

    async def stop(self):
        self._running = False
        if self._bus:
            self._bus.off(EventType.ORDER_REQUEST, self._on_order_request)
        logger.info("Risk engine stopped")

    # ---- Position Counting ----

    def _count_positions(self):
        """Count positions per strategy bucket."""
        counts = {"weather": 0, "crypto": 0, "arb": 0, "unknown": 0}
        by_strategy_id = defaultdict(int)

        for pos in self._state.positions.values():
            bucket = classify_strategy(pos)
            counts[bucket] = counts.get(bucket, 0) + 1
            sid = getattr(pos, "strategy_id", "") or "unknown"
            by_strategy_id[sid] += 1

        return counts, dict(by_strategy_id)

    def get_slot_diagnostics(self) -> dict:
        """Detailed per-strategy slot diagnostics."""
        counts, by_strategy_id = self._count_positions()
        cfg = self._state.risk_config if self._state else None
        total = sum(counts.values())

        return {
            "weather_count": counts["weather"],
            "crypto_count": counts["crypto"],
            "arb_count": counts["arb"],
            "unknown_count": counts.get("unknown", 0),
            "total": total,
            "by_strategy": by_strategy_id,
            "limits": {
                "max_weather": cfg.max_weather_positions if cfg else 0,
                "max_crypto": cfg.max_crypto_positions if cfg else 0,
                "max_arb": cfg.max_arb_positions if cfg else 0,
                "max_global": cfg.max_concurrent_positions if cfg else 0,
            },
            "headroom": {
                "weather": max(0, (cfg.max_weather_positions if cfg else 0) - counts["weather"]),
                "crypto": max(0, (cfg.max_crypto_positions if cfg else 0) - counts["crypto"]),
                "arb": max(0, (cfg.max_arb_positions if cfg else 0) - counts["arb"]),
                "global": max(0, (cfg.max_concurrent_positions if cfg else 0) - total),
            },
            "blocked_by_position_limit": dict(self._slot_blocks),
            "sizing": {
                "crypto": cfg.crypto_position_size if cfg else 0,
                "weather": cfg.weather_position_size if cfg else 0,
                "arb": cfg.arb_position_size if cfg else 0,
            },
        }

    # ---- Main Check ----

    def check_order(self, order: OrderRecord) -> tuple:
        """Returns (approved: bool, reason: str)."""
        if not self._state:
            return False, "risk engine not initialized"

        cfg = self._state.risk_config

        if cfg.kill_switch_active:
            return False, "kill switch active"

        if order.size > cfg.max_order_size:
            return False, f"order size {order.size} > max {cfg.max_order_size}"

        # Position size projection
        existing = self._state.get_position(order.token_id)
        projected = (existing.size if existing else 0) + order.size
        if projected > cfg.max_position_size:
            return False, f"projected position {projected} > max {cfg.max_position_size}"

        # Per-strategy slot check (only for NEW positions)
        if order.token_id not in self._state.positions:
            counts, _ = self._count_positions()
            bucket = classify_strategy(order)
            total = sum(counts.values())

            # Per-strategy bucket limit
            limit_map = {
                "weather": cfg.max_weather_positions,
                "crypto": cfg.max_crypto_positions,
                "arb": cfg.max_arb_positions,
            }

            bucket_limit = limit_map.get(bucket)
            if bucket_limit is not None:
                current = counts.get(bucket, 0)
                if current >= bucket_limit:
                    self._slot_blocks[bucket] += 1
                    return False, f"{bucket} positions ({current}) >= max {bucket_limit}"

            # Global fallback (but never blocks arb if arb has headroom)
            if total >= cfg.max_concurrent_positions:
                if bucket == "arb" and counts.get("arb", 0) < cfg.max_arb_positions:
                    pass  # arb gets priority — skip global check
                else:
                    self._slot_blocks["global"] += 1
                    return False, f"max concurrent positions ({total}) >= {cfg.max_concurrent_positions}"

        # Market freshness check
        market = self._state.get_market(order.token_id)
        if market and cfg.min_market_freshness_seconds > 0:
            from engine.strategies.arb_pricing import compute_data_age
            age = compute_data_age(market.updated_at)
            if age > cfg.min_market_freshness_seconds:
                return False, f"stale market data ({age:.0f}s > {cfg.min_market_freshness_seconds}s)"

        # Spread check
        if market and cfg.max_spread_bps > 0:
            if market.best_bid and market.best_ask:
                spread_bps = ((market.best_ask - market.best_bid) / max(market.mid_price or 0.5, 0.01)) * 10000
                if spread_bps > cfg.max_spread_bps:
                    return False, f"spread {spread_bps:.0f}bps > max {cfg.max_spread_bps}bps"

        # Liquidity ratio check
        if market and cfg.max_size_to_liquidity_ratio > 0 and market.liquidity > 0:
            ratio = order.size / market.liquidity
            if ratio > cfg.max_size_to_liquidity_ratio:
                return False, f"size/liquidity ratio {ratio:.2f} > max {cfg.max_size_to_liquidity_ratio}"

        # Daily loss limit
        if self._state.daily_pnl <= -cfg.max_daily_loss:
            return False, f"daily loss limit hit ({self._state.daily_pnl})"

        # Total exposure check
        total_exposure = sum(
            p.size * p.current_price for p in self._state.positions.values()
        )
        order_value = order.size * order.price
        if total_exposure + order_value > cfg.max_market_exposure:
            return False, f"total exposure {total_exposure + order_value:.2f} > max {cfg.max_market_exposure}"

        return True, "approved"

    def get_strategy_position_size(self, strategy_id: str) -> float:
        """Return the configured position size for a strategy."""
        if not self._state:
            return 5.0
        cfg = self._state.risk_config
        sizing = {
            "crypto_sniper": cfg.crypto_position_size,
            "weather_trader": cfg.weather_position_size,
            "arb_scanner": cfg.arb_position_size,
        }
        return sizing.get(strategy_id, cfg.crypto_position_size)

    def get_duration_priority_score(self, token_id: str) -> float:
        """Lower score = higher priority. Short-duration markets are preferred."""
        market = self._state.get_market(token_id) if self._state else None
        hours = estimate_time_to_resolution(market)
        # Crypto (5min markets) → ~0.08 hours → score ~0.08
        # Weather (1 day) → ~24 hours → score ~24
        return hours

    # ---- Event Handler ----

    async def _on_order_request(self, event: Event):
        order = OrderRecord(**event.data)
        approved, reason = self.check_order(order)

        if approved:
            await self._bus.emit(Event(
                type=EventType.ORDER_UPDATE,
                source="risk_engine",
                data={**order.model_dump(), "_risk_approved": True},
            ))
        else:
            logger.warning(f"Order {order.id} rejected: {reason}")
            order.status = OrderStatus.REJECTED
            self._state.update_order(order.id, status=OrderStatus.REJECTED)
            await self._bus.emit(Event(
                type=EventType.RISK_ALERT,
                source="risk_engine",
                data={"order_id": order.id, "reason": reason},
            ))

    async def activate_kill_switch(self, reason: str = "manual"):
        if self._state:
            self._state.risk_config.kill_switch_active = True
            logger.warning(f"KILL SWITCH ACTIVATED: {reason}")
            if self._bus:
                await self._bus.emit(Event(
                    type=EventType.RISK_ALERT,
                    source="risk_engine",
                    data={"action": "kill_switch_activated", "reason": reason},
                ))

    async def deactivate_kill_switch(self):
        if self._state:
            self._state.risk_config.kill_switch_active = False
            logger.info("Kill switch deactivated")
