"""Live Polymarket CLOB execution adapter — hardened for real-money use.

Order lifecycle: submit → open → partially_filled → filled / cancelled / expired
Partial fills: tracked via LiveOrderRecord, positions/PnL update on actual fill qty.
Status polling: background task polls open orders every N seconds.
All CLOB calls wrapped in asyncio.to_thread (non-blocking).
"""

import asyncio
import logging
import os
import time
from typing import Optional

from models import (
    OrderRecord, OrderStatus, TradeRecord, Position, LiveOrderRecord,
    Event, EventType, utc_now, new_id,
)

logger = logging.getLogger(__name__)

POLYMARKET_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

LIVE_DEFAULTS = {
    "max_order_size": 2.0,
    "max_position_size": 5.0,
    "max_market_exposure": 20.0,
    "max_concurrent_positions": 3,
    "max_daily_loss": 10.0,
}

POLL_INTERVAL_SECONDS = 5


class LiveAdapter:
    """Submits real orders to Polymarket CLOB with full fill tracking."""

    def __init__(self, state, bus):
        self._state = state
        self._bus = bus
        self._client = None
        self._authenticated = False
        self._live_order_service = None
        self._poll_task: Optional[asyncio.Task] = None

        # Counters
        self._total_submitted = 0
        self._total_filled = 0
        self._total_partial = 0
        self._total_failed = 0
        self._last_error: Optional[str] = None
        self._last_api_call: Optional[str] = None
        self._last_status_refresh: Optional[str] = None
        self._recent_errors: list = []

    # ---- Credentials ----

    @staticmethod
    def credentials_present() -> dict:
        keys = {
            "POLYMARKET_PRIVATE_KEY": bool(os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()),
            "POLYMARKET_FUNDER_ADDRESS": bool(os.environ.get("POLYMARKET_FUNDER_ADDRESS", "").strip()),
            "POLYMARKET_API_KEY": bool(os.environ.get("POLYMARKET_API_KEY", "").strip()),
            "POLYMARKET_API_SECRET": bool(os.environ.get("POLYMARKET_API_SECRET", "").strip()),
            "POLYMARKET_PASSPHRASE": bool(os.environ.get("POLYMARKET_PASSPHRASE", "").strip()),
        }
        keys["private_key_set"] = keys["POLYMARKET_PRIVATE_KEY"]
        keys["api_creds_set"] = all([
            keys["POLYMARKET_API_KEY"],
            keys["POLYMARKET_API_SECRET"],
            keys["POLYMARKET_PASSPHRASE"],
        ])
        keys["ready"] = keys["private_key_set"]
        return keys

    # ---- Initialization ----

    def set_order_service(self, service):
        self._live_order_service = service

    async def initialize(self) -> bool:
        creds = self.credentials_present()
        if not creds["private_key_set"]:
            self._last_error = "POLYMARKET_PRIVATE_KEY not set"
            logger.warning(f"LiveAdapter init skipped: {self._last_error}")
            return False

        try:
            result = await asyncio.to_thread(self._sync_init)
            if result:
                self._authenticated = True
                self._last_error = None
                self._last_api_call = utc_now()
                logger.info("LiveAdapter authenticated with Polymarket CLOB")
            return result
        except Exception as e:
            self._authenticated = False
            self._last_error = str(e)
            self._add_error(str(e))
            logger.error(f"LiveAdapter init failed: {e}")
            return False

    def _sync_init(self) -> bool:
        from py_clob_client.client import ClobClient

        private_key = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
        funder = os.environ.get("POLYMARKET_FUNDER_ADDRESS", "").strip()

        if funder:
            self._client = ClobClient(
                POLYMARKET_HOST, key=private_key, chain_id=CHAIN_ID,
                signature_type=1, funder=funder,
            )
        else:
            self._client = ClobClient(
                POLYMARKET_HOST, key=private_key, chain_id=CHAIN_ID,
            )

        api_key = os.environ.get("POLYMARKET_API_KEY", "").strip()
        api_secret = os.environ.get("POLYMARKET_API_SECRET", "").strip()
        passphrase = os.environ.get("POLYMARKET_PASSPHRASE", "").strip()

        if api_key and api_secret and passphrase:
            from py_clob_client.clob_types import ApiCreds
            self._client.set_api_creds(ApiCreds(
                api_key=api_key, api_secret=api_secret, api_passphrase=passphrase,
            ))
        else:
            self._client.set_api_creds(self._client.create_or_derive_api_creds())

        return True

    # ---- Background Polling ----

    async def start_polling(self):
        """Start background task to poll open live orders."""
        if self._poll_task and not self._poll_task.done():
            return
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Live order status polling started")

    async def stop_polling(self):
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Live order status polling stopped")

    async def _poll_loop(self):
        """Periodically check status of open live orders."""
        while True:
            try:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                if not self._authenticated or not self._live_order_service:
                    continue
                active = self._live_order_service.active_orders
                if not active:
                    continue

                for rec_id, rec in list(active.items()):
                    if not rec.exchange_order_id:
                        continue
                    try:
                        await self._refresh_order_status(rec)
                    except Exception as e:
                        logger.warning(f"Status refresh failed for {rec.exchange_order_id[:12]}: {e}")
                        self._add_error(f"poll:{e}")

                self._last_status_refresh = utc_now()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _refresh_order_status(self, rec: LiveOrderRecord):
        """Query CLOB for the latest status of a single order."""
        if not self._client:
            return

        try:
            order_data = await asyncio.to_thread(
                self._client.get_order, rec.exchange_order_id
            )
            self._last_api_call = utc_now()
        except Exception as e:
            self._add_error(f"get_order:{e}")
            return

        if not order_data:
            return

        # Parse CLOB order status
        clob_status = order_data.get("status", "").lower()
        size_matched = float(order_data.get("size_matched", 0))
        original_size = float(order_data.get("original_size", rec.requested_size))
        price = float(order_data.get("price", rec.price))

        prev_filled = rec.filled_size
        new_filled = size_matched
        fill_delta = new_filled - prev_filled

        # Map CLOB status to our lifecycle
        if clob_status == "matched" or new_filled >= original_size:
            new_status = "filled"
        elif new_filled > 0 and new_filled < original_size:
            new_status = "partially_filled"
        elif clob_status == "cancelled":
            new_status = "cancelled"
        elif clob_status == "expired":
            new_status = "expired"
        elif clob_status in ("live", "open"):
            new_status = "open"
        else:
            new_status = rec.status  # Keep current

        remaining = max(0, original_size - new_filled)
        avg_price = price if new_filled > 0 else rec.avg_fill_price

        updates = {
            "status": new_status,
            "filled_size": round(new_filled, 6),
            "remaining_size": round(remaining, 6),
            "avg_fill_price": round(avg_price, 6),
        }

        if new_status == "filled":
            updates["filled_at"] = utc_now()

        await self._live_order_service.update_status(rec.id, **updates)

        # Process new fills — update positions/trades for the delta
        if fill_delta > 0:
            await self._process_fill_delta(rec, fill_delta, avg_price, new_status)

        if new_status != rec.status:
            logger.info(f"[LIVE] Order {rec.exchange_order_id[:12]} status: {rec.status} → {new_status} (filled {new_filled}/{original_size})")

    async def _process_fill_delta(self, rec: LiveOrderRecord, delta: float, fill_price: float, new_status: str):
        """Process an incremental fill — create trade record and update position."""
        market = self._state.get_market(rec.token_id)
        mkt_question = market.question if market else rec.market_question
        mkt_outcome = market.outcome if market else ""

        from models import OrderSide
        side = OrderSide.BUY if rec.side == "buy" else OrderSide.SELL

        trade = TradeRecord(
            id=new_id(),
            order_id=rec.order_id,
            token_id=rec.token_id,
            market_question=mkt_question,
            outcome=mkt_outcome,
            side=side,
            price=fill_price,
            size=round(delta, 6),
            fees=round(delta * fill_price * 0.002, 6),
            strategy_id=rec.strategy_id,
            signal_reason=f"live_fill_{new_status}",
        )
        self._state.add_trade(trade)

        # Update position based on filled delta
        existing = self._state.get_position(rec.token_id)
        if rec.side == "buy":
            if existing:
                new_size = existing.size + delta
                new_cost = ((existing.avg_cost * existing.size) + (fill_price * delta)) / new_size if new_size > 0 else 0
                self._state.update_position(rec.token_id, Position(
                    token_id=rec.token_id, market_question=existing.market_question,
                    outcome=existing.outcome, size=round(new_size, 6),
                    avg_cost=round(new_cost, 6), current_price=fill_price,
                    unrealized_pnl=0.0, realized_pnl=existing.realized_pnl,
                ))
            else:
                self._state.update_position(rec.token_id, Position(
                    token_id=rec.token_id, market_question=mkt_question,
                    outcome=mkt_outcome, size=round(delta, 6),
                    avg_cost=fill_price, current_price=fill_price,
                ))
        else:
            if existing and existing.size >= delta:
                new_size = round(existing.size - delta, 6)
                pnl = round((fill_price - existing.avg_cost) * delta, 6)
                self._state.update_position(rec.token_id, Position(
                    token_id=rec.token_id, market_question=existing.market_question,
                    outcome=existing.outcome, size=new_size,
                    avg_cost=existing.avg_cost, current_price=fill_price,
                    unrealized_pnl=0.0, realized_pnl=round(existing.realized_pnl + pnl, 6),
                ))

        if new_status == "filled":
            self._total_filled += 1
        elif new_status == "partially_filled":
            self._total_partial += 1

        await self._bus.emit(Event(
            type=EventType.ORDER_UPDATE,
            source="live_adapter",
            data={
                "order_id": rec.order_id,
                "status": new_status,
                "fill_price": fill_price,
                "filled_size": rec.filled_size + delta,
                "remaining_size": rec.remaining_size - delta,
                "exchange_order_id": rec.exchange_order_id,
            },
        ))

    # ---- Pre-flight checks ----

    def _preflight_check(self, order: OrderRecord) -> tuple:
        if not self._authenticated:
            return False, "live adapter not authenticated"
        if not self._client:
            return False, "CLOB client not initialized"
        if self._state.trading_mode.value != "live":
            return False, f"trading mode is '{self._state.trading_mode.value}', not 'live'"
        if self._state.risk_config.kill_switch_active:
            return False, "kill switch is active"
        if order.size > LIVE_DEFAULTS["max_order_size"]:
            return False, f"live order size {order.size} > safe max {LIVE_DEFAULTS['max_order_size']}"
        return True, "preflight passed"

    # ---- Execution ----

    async def execute(self, order: OrderRecord):
        """Submit a real order to Polymarket CLOB."""
        t_start = time.time()

        ok, reason = self._preflight_check(order)
        if not ok:
            await self._reject_order(order, reason, t_start)
            return

        try:
            result = await asyncio.to_thread(self._sync_execute, order)
            latency_ms = round((time.time() - t_start) * 1000, 2)
            self._last_api_call = utc_now()

            if result.get("success"):
                await self._handle_submission(order, result, latency_ms)
            else:
                await self._reject_order(order, result.get("error", "CLOB submission failed"), t_start)

        except Exception as e:
            self._total_failed += 1
            self._last_error = str(e)
            self._add_error(str(e))
            logger.error(f"[LIVE] Order {order.id} execution error: {e}")
            await self._reject_order(order, f"execution error: {e}", t_start)

    def _sync_execute(self, order: OrderRecord) -> dict:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        side = BUY if order.side.value == "buy" else SELL
        order_args = OrderArgs(
            price=order.price, size=order.size,
            side=side, token_id=order.token_id,
        )

        signed_order = self._client.create_order(order_args)
        resp = self._client.post_order(signed_order, OrderType.GTC)
        self._total_submitted += 1

        if resp and resp.get("orderID"):
            return {
                "success": True,
                "exchange_order_id": resp["orderID"],
                "clob_status": resp.get("status", "live"),
            }
        elif resp and resp.get("errorMsg"):
            return {"success": False, "error": resp["errorMsg"]}
        else:
            return {
                "success": True,
                "exchange_order_id": resp.get("orderID", "unknown"),
                "clob_status": "submitted",
            }

    async def _handle_submission(self, order: OrderRecord, result: dict, latency_ms: float):
        """Process a successful order submission — DO NOT treat as filled yet."""
        exchange_id = result.get("exchange_order_id", "")

        # Mark order as SUBMITTED (not filled — fills come from polling)
        self._state.update_order(
            order.id,
            status=OrderStatus.SUBMITTED,
            exchange_order_id=exchange_id,
            latency_ms=latency_ms,
            updated_at=utc_now(),
        )
        self._state.health["last_order_latency_ms"] = latency_ms

        # Create persistent live order record
        market = self._state.get_market(order.token_id)
        rec = LiveOrderRecord(
            order_id=order.id,
            exchange_order_id=exchange_id,
            strategy_id=order.strategy_id,
            token_id=order.token_id,
            condition_id=market.condition_id if market else "",
            market_question=market.question if market else "",
            side=order.side.value,
            price=order.price,
            requested_size=order.size,
            filled_size=0.0,
            remaining_size=order.size,
            avg_fill_price=0.0,
            status="submitted",
        )

        if self._live_order_service:
            await self._live_order_service.save(rec)

        logger.info(f"[LIVE] SUBMITTED {order.side.value.upper()} {order.size}@{order.price:.4f} token={order.token_id[:12]}... exch={exchange_id} ({latency_ms}ms)")

        await self._bus.emit(Event(
            type=EventType.ORDER_UPDATE,
            source="live_adapter",
            data={
                "order_id": order.id,
                "status": "submitted",
                "exchange_order_id": exchange_id,
                "latency_ms": latency_ms,
            },
        ))

    async def _reject_order(self, order: OrderRecord, reason: str, t_start: float):
        self._total_failed += 1
        self._last_error = reason
        self._add_error(reason)
        latency_ms = round((time.time() - t_start) * 1000, 2)

        self._state.update_order(order.id, status=OrderStatus.REJECTED)
        logger.warning(f"[LIVE] Order {order.id} rejected: {reason} ({latency_ms}ms)")

        if self._live_order_service:
            rec = LiveOrderRecord(
                order_id=order.id, strategy_id=order.strategy_id,
                token_id=order.token_id, side=order.side.value,
                price=order.price, requested_size=order.size,
                remaining_size=order.size, status="rejected", error=reason,
            )
            await self._live_order_service.save(rec)

        await self._bus.emit(Event(
            type=EventType.RISK_ALERT,
            source="live_adapter",
            data={"order_id": order.id, "reason": reason, "action": "live_order_rejected"},
        ))

    def _add_error(self, msg: str):
        self._recent_errors.append({"error": msg, "at": utc_now()})
        self._recent_errors = self._recent_errors[-20:]

    # ---- Status ----

    @property
    def status(self) -> dict:
        creds = self.credentials_present()
        svc = self._live_order_service
        return {
            "adapter": "live",
            "authenticated": self._authenticated,
            "credentials": creds,
            "total_submitted": self._total_submitted,
            "total_filled": self._total_filled,
            "total_partial_fills": self._total_partial,
            "total_failed": self._total_failed,
            "open_orders": svc.open_count if svc else 0,
            "partial_orders": svc.partial_count if svc else 0,
            "last_api_call": self._last_api_call,
            "last_status_refresh": self._last_status_refresh,
            "last_error": self._last_error,
            "recent_errors": self._recent_errors[-5:],
        }

    async def get_balance(self) -> Optional[float]:
        if not self._authenticated or not self._client:
            return None
        try:
            balance_wei = await asyncio.to_thread(self._client.get_balance)
            self._last_api_call = utc_now()
            return int(balance_wei) / 1e6
        except Exception as e:
            self._add_error(f"balance:{e}")
            logger.warning(f"Balance check failed: {e}")
            return None
