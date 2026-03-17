import logging
import time
from collections import defaultdict

from models import Event, EventType, OrderRecord, OrderStatus

logger = logging.getLogger(__name__)

WEATHER_STRATEGIES = {"weather_trader"}

WEATHER_KEYWORDS = {"temperature", "highest temp", "lowest temp", "weather", "°f", "fahrenheit"}


def _is_weather_position(pos) -> bool:
    """Classify a position as weather based on strategy_id or market question keywords."""
    sid = getattr(pos, "strategy_id", "") or ""
    if sid in WEATHER_STRATEGIES:
        return True
    if sid and sid not in WEATHER_STRATEGIES:
        return False  # explicit non-weather strategy
    # Fallback to keyword matching for legacy positions without strategy_id
    q = (getattr(pos, "market_question", "") or "").lower()
    return any(kw in q for kw in WEATHER_KEYWORDS)


class RiskEngine:
    """Gates all order requests. Enforces limits, kill switch, exposure checks."""

    def __init__(self):
        self._state = None
        self._bus = None
        self._running = False
        # Diagnostics: track rejections by reason
        self._slot_blocks = defaultdict(int)  # strategy_bucket -> count

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True
        self._bus.on(EventType.ORDER_REQUEST, self._on_order_request)
        logger.info("Risk engine started")

    async def stop(self):
        self._running = False
        if self._bus:
            self._bus.off(EventType.ORDER_REQUEST, self._on_order_request)
        logger.info("Risk engine stopped")

    # ---- helpers ----

    def _count_positions_by_bucket(self):
        """Count open positions per strategy bucket."""
        weather = 0
        nonweather = 0
        by_strategy = defaultdict(int)
        for pos in self._state.positions.values():
            sid = getattr(pos, "strategy_id", "") or "unknown"
            by_strategy[sid] += 1
            if _is_weather_position(pos):
                weather += 1
            else:
                nonweather += 1
        return weather, nonweather, dict(by_strategy)

    def get_slot_diagnostics(self) -> dict:
        """Return detailed position slot diagnostics."""
        weather, nonweather, by_strategy = self._count_positions_by_bucket()
        cfg = self._state.risk_config if self._state else None
        return {
            "weather_count": weather,
            "nonweather_count": nonweather,
            "total": weather + nonweather,
            "by_strategy": by_strategy,
            "limits": {
                "max_weather": cfg.max_weather_positions if cfg else 0,
                "max_nonweather": cfg.max_nonweather_positions if cfg else 0,
                "max_global": cfg.max_concurrent_positions if cfg else 0,
            },
            "headroom": {
                "weather": max(0, (cfg.max_weather_positions if cfg else 0) - weather),
                "nonweather": max(0, (cfg.max_nonweather_positions if cfg else 0) - nonweather),
                "global": max(0, (cfg.max_concurrent_positions if cfg else 0) - weather - nonweather),
            },
            "blocked_by_position_limit": dict(self._slot_blocks),
        }

    # ---- main check ----

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

        # Per-strategy-bucket slot check (only for NEW positions)
        if order.token_id not in self._state.positions:
            weather_count, nonweather_count, _ = self._count_positions_by_bucket()
            strategy = getattr(order, "strategy_id", "") or ""
            is_weather = strategy in WEATHER_STRATEGIES

            if is_weather:
                if weather_count >= cfg.max_weather_positions:
                    self._slot_blocks["weather"] += 1
                    return False, f"weather positions ({weather_count}) >= max {cfg.max_weather_positions}"
            else:
                if nonweather_count >= cfg.max_nonweather_positions:
                    self._slot_blocks["nonweather"] += 1
                    return False, f"nonweather positions ({nonweather_count}) >= max {cfg.max_nonweather_positions}"

            # Global fallback
            total = weather_count + nonweather_count
            if total >= cfg.max_concurrent_positions:
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
