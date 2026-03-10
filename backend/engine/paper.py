import logging
import time

from models import (
    OrderRecord, OrderStatus, TradeRecord, Position,
    Event, EventType, utc_now, new_id,
)

logger = logging.getLogger(__name__)


class PaperAdapter:
    """Simulates fills for paper trading mode."""

    def __init__(self, state, bus):
        self._state = state
        self._bus = bus

    async def execute(self, order: OrderRecord):
        t_start = time.time()
        market = self._state.get_market(order.token_id)
        fill_price = order.price

        if market and market.mid_price:
            slippage = 0.001
            if order.side.value == "buy":
                fill_price = market.mid_price * (1 + slippage)
            else:
                fill_price = market.mid_price * (1 - slippage)

        fill_price = round(fill_price, 4)

        # Mark order filled
        self._state.update_order(
            order.id,
            status=OrderStatus.FILLED,
            filled_size=order.size,
            fill_price=fill_price,
            slippage=round(abs(fill_price - order.price), 6),
            updated_at=utc_now(),
        )

        # Record trade
        trade = TradeRecord(
            id=new_id(),
            order_id=order.id,
            token_id=order.token_id,
            side=order.side,
            price=fill_price,
            size=order.size,
            fees=round(order.size * fill_price * 0.002, 4),
            strategy_id=order.strategy_id,
            signal_reason="paper_fill",
        )
        self._state.add_trade(trade)

        # Update position
        existing = self._state.get_position(order.token_id)

        if order.side.value == "buy":
            if existing:
                new_size = existing.size + order.size
                new_cost = ((existing.avg_cost * existing.size) + (fill_price * order.size)) / new_size
                self._state.update_position(order.token_id, Position(
                    token_id=order.token_id,
                    market_question=existing.market_question,
                    outcome=existing.outcome,
                    size=round(new_size, 4),
                    avg_cost=round(new_cost, 4),
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    realized_pnl=existing.realized_pnl,
                ))
            else:
                self._state.update_position(order.token_id, Position(
                    token_id=order.token_id,
                    size=order.size,
                    avg_cost=fill_price,
                    current_price=fill_price,
                ))
        else:
            if existing and existing.size >= order.size:
                new_size = round(existing.size - order.size, 4)
                pnl = round((fill_price - existing.avg_cost) * order.size, 4)
                self._state.update_position(order.token_id, Position(
                    token_id=order.token_id,
                    market_question=existing.market_question,
                    outcome=existing.outcome,
                    size=new_size,
                    avg_cost=existing.avg_cost,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    realized_pnl=round(existing.realized_pnl + pnl, 4),
                ))

        latency_ms = round((time.time() - t_start) * 1000, 2)
        self._state.health["last_order_latency_ms"] = latency_ms
        logger.info(f"[PAPER] {order.side.value.upper()} {order.size}@{fill_price:.4f} token={order.token_id[:12]}... ({latency_ms}ms)")

        await self._bus.emit(Event(
            type=EventType.ORDER_UPDATE,
            source="paper_adapter",
            data={"order_id": order.id, "status": "filled", "fill_price": fill_price, "latency_ms": latency_ms},
        ))
