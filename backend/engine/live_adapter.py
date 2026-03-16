"""Live Polymarket CLOB execution adapter — Phase 8B hardened.

Order lifecycle: submit → open → partially_filled → filled / cancelled / expired
Cancel: manual cancel via CLOB API, persisted with reason and timestamp.
Slippage: pre-flight check compares order price against reference; rejects if
  deviation exceeds max_live_slippage_bps.
Fill updates: currently polling (5s). Architecture ready for CLOB WebSocket.
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
POLL_INTERVAL_WS_FALLBACK = 30  # Reduced polling when WS fills active


class LiveAdapter:
    def __init__(self, state, bus):
        self._state = state
        self._bus = bus
        self._client = None
        self._authenticated = False
        self._live_order_service = None
        self._fill_ws = None  # ClobFillWsClient (injected)
        self._poll_task: Optional[asyncio.Task] = None

        self._total_submitted = 0
        self._total_filled = 0
        self._total_partial = 0
        self._total_failed = 0
        self._total_cancelled = 0
        self._total_slippage_rejected = 0
        self._ws_fill_count = 0
        self._poll_fill_count = 0
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
        keys["api_creds_set"] = all([keys["POLYMARKET_API_KEY"], keys["POLYMARKET_API_SECRET"], keys["POLYMARKET_PASSPHRASE"]])
        keys["ready"] = keys["private_key_set"]
        return keys

    # ---- Init ----

    def set_order_service(self, service):
        self._live_order_service = service

    def set_fill_ws(self, fill_ws):
        """Inject fill WebSocket client for real-time fill updates."""
        self._fill_ws = fill_ws

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
            self._client = ClobClient(POLYMARKET_HOST, key=private_key, chain_id=CHAIN_ID, signature_type=1, funder=funder)
        else:
            self._client = ClobClient(POLYMARKET_HOST, key=private_key, chain_id=CHAIN_ID)

        api_key = os.environ.get("POLYMARKET_API_KEY", "").strip()
        api_secret = os.environ.get("POLYMARKET_API_SECRET", "").strip()
        passphrase = os.environ.get("POLYMARKET_PASSPHRASE", "").strip()
        if api_key and api_secret and passphrase:
            from py_clob_client.clob_types import ApiCreds
            self._client.set_api_creds(ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=passphrase))
        else:
            self._client.set_api_creds(self._client.create_or_derive_api_creds())
        return True

    # ---- Background Polling ----

    async def start_polling(self):
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
        while True:
            try:
                # Reduce polling when WS fill updates are active
                interval = POLL_INTERVAL_WS_FALLBACK if (self._fill_ws and self._fill_ws._connected) else POLL_INTERVAL_SECONDS
                await asyncio.sleep(interval)
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
        if not self._client:
            return
        try:
            order_data = await asyncio.to_thread(self._client.get_order, rec.exchange_order_id)
            self._last_api_call = utc_now()
        except Exception as e:
            self._add_error(f"get_order:{e}")
            return
        if not order_data:
            return

        clob_status = order_data.get("status", "").lower()
        size_matched = float(order_data.get("size_matched", 0))
        original_size = float(order_data.get("original_size", rec.requested_size))
        price = float(order_data.get("price", rec.price))

        prev_filled = rec.filled_size
        new_filled = size_matched
        fill_delta = new_filled - prev_filled

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
            new_status = rec.status

        remaining = max(0, original_size - new_filled)
        avg_price = price if new_filled > 0 else rec.avg_fill_price

        # Calculate slippage
        slippage_bps = None
        if avg_price > 0 and rec.price > 0 and new_filled > 0:
            slippage_bps = round(abs(avg_price - rec.price) / rec.price * 10000, 2)

        updates = {
            "status": new_status,
            "filled_size": round(new_filled, 6),
            "remaining_size": round(remaining, 6),
            "avg_fill_price": round(avg_price, 6),
            "update_source": "poll",
        }
        if slippage_bps is not None:
            updates["slippage_bps"] = slippage_bps
        if new_status == "filled":
            updates["filled_at"] = utc_now()

        await self._live_order_service.update_status(rec.id, **updates)

        if fill_delta > 0:
            self._poll_fill_count += 1
            await self._process_fill_delta(rec, fill_delta, avg_price, new_status)
        if new_status != rec.status:
            logger.info(f"[LIVE] Order {rec.exchange_order_id[:12]} status: {rec.status} -> {new_status} (filled {new_filled}/{original_size})")

    async def _process_fill_delta(self, rec: LiveOrderRecord, delta: float, fill_price: float, new_status: str):
        market = self._state.get_market(rec.token_id)
        mkt_question = market.question if market else rec.market_question
        mkt_outcome = market.outcome if market else ""
        from models import OrderSide
        side = OrderSide.BUY if rec.side == "buy" else OrderSide.SELL

        trade = TradeRecord(
            id=new_id(), order_id=rec.order_id, token_id=rec.token_id,
            market_question=mkt_question, outcome=mkt_outcome, side=side,
            price=fill_price, size=round(delta, 6),
            fees=round(delta * fill_price * 0.002, 6),
            strategy_id=rec.strategy_id, signal_reason=f"live_fill_{new_status}",
        )
        self._state.add_trade(trade)

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
            type=EventType.ORDER_UPDATE, source="live_adapter",
            data={"order_id": rec.order_id, "status": new_status, "fill_price": fill_price,
                  "filled_size": rec.filled_size + delta, "remaining_size": rec.remaining_size - delta,
                  "exchange_order_id": rec.exchange_order_id},
        ))

    # ---- WebSocket Fill Callback ----

    async def on_ws_fill(self, fill_event: dict):
        """Process a real-time fill event from ClobFillWsClient.

        Called with trade events (MATCHED, MINED, CONFIRMED).
        Updates LiveOrderRecord, processes fill delta, emits events.
        """
        if not self._live_order_service:
            return

        taker_order_id = fill_event.get("taker_order_id", "")
        asset_id = fill_event.get("asset_id", "")
        side = fill_event.get("side", "")
        size = fill_event.get("size", 0)
        price = fill_event.get("price", 0)

        # Match against active orders by exchange_order_id or token_id
        matched_rec = None
        for rec in self._live_order_service.active_orders.values():
            if rec.exchange_order_id and rec.exchange_order_id == taker_order_id:
                matched_rec = rec
                break
            # Also try matching by asset_id (token_id)
            if rec.token_id == asset_id and rec.side == side.lower():
                matched_rec = rec
                break

        if not matched_rec:
            logger.debug(f"[FILL WS] No matching active order for trade {taker_order_id[:16]}...")
            return

        # Compute fill delta
        prev_filled = matched_rec.filled_size
        new_filled = min(prev_filled + size, matched_rec.requested_size)
        fill_delta = new_filled - prev_filled

        if fill_delta <= 0:
            return

        remaining = max(0, matched_rec.requested_size - new_filled)
        new_status = "filled" if remaining <= 0 else "partially_filled"

        # Calculate slippage
        slippage_bps = None
        if price > 0 and matched_rec.price > 0:
            slippage_bps = round(abs(price - matched_rec.price) / matched_rec.price * 10000, 2)

        updates = {
            "status": new_status,
            "filled_size": round(new_filled, 6),
            "remaining_size": round(remaining, 6),
            "avg_fill_price": round(price, 6),
            "update_source": "websocket",
        }
        if slippage_bps is not None:
            updates["slippage_bps"] = slippage_bps
        if new_status == "filled":
            updates["filled_at"] = utc_now()

        await self._live_order_service.update_status(matched_rec.id, **updates)
        self._ws_fill_count += 1

        await self._process_fill_delta(matched_rec, fill_delta, price, new_status)

        logger.info(
            f"[FILL WS] Order {matched_rec.exchange_order_id[:12] if matched_rec.exchange_order_id else matched_rec.id} "
            f"fill via WS: +{fill_delta:.4f} at {price:.4f} ({new_status})"
        )

    # ---- Cancel ----

    async def cancel_order(self, record_id: str) -> dict:
        """Cancel an open/partial live order on the CLOB."""
        if not self._live_order_service:
            return {"success": False, "reason": "order service not initialized"}

        rec = self._live_order_service.active_orders.get(record_id)
        if not rec:
            # Check DB for already-terminal order
            doc = await self._live_order_service.get_by_id(record_id)
            if doc:
                return {"success": False, "reason": f"order already in terminal state: {doc.get('status', 'unknown')}"}
            return {"success": False, "reason": "order not found"}

        if rec.status not in ("submitted", "open", "partially_filled"):
            return {"success": False, "reason": f"cannot cancel order in status: {rec.status}"}

        if not self._authenticated or not self._client:
            # No CLOB connection — just mark as cancelled locally
            await self._live_order_service.update_status(
                rec.id, status="cancelled", cancelled_at=utc_now(),
                cancel_reason="manual_cancel_offline",
            )
            self._total_cancelled += 1
            return {"success": True, "method": "local_only", "filled_size": rec.filled_size}

        if not rec.exchange_order_id:
            await self._live_order_service.update_status(
                rec.id, status="cancelled", cancelled_at=utc_now(),
                cancel_reason="manual_cancel_no_exchange_id",
            )
            self._total_cancelled += 1
            return {"success": True, "method": "local", "filled_size": rec.filled_size}

        try:
            await asyncio.to_thread(self._client.cancel, rec.exchange_order_id)
            self._last_api_call = utc_now()

            await self._live_order_service.update_status(
                rec.id, status="cancelled", cancelled_at=utc_now(),
                cancel_reason="manual_cancel",
            )
            self._total_cancelled += 1

            logger.info(f"[LIVE] Cancelled order {rec.exchange_order_id[:12]} (filled {rec.filled_size}/{rec.requested_size})")

            await self._bus.emit(Event(
                type=EventType.ORDER_UPDATE, source="live_adapter",
                data={"order_id": rec.order_id, "status": "cancelled",
                      "exchange_order_id": rec.exchange_order_id,
                      "filled_size": rec.filled_size, "remaining_size": rec.remaining_size},
            ))

            return {
                "success": True,
                "method": "clob_cancel",
                "exchange_order_id": rec.exchange_order_id,
                "filled_size": rec.filled_size,
                "remaining_size": rec.remaining_size,
            }

        except Exception as e:
            self._add_error(f"cancel:{e}")
            logger.error(f"[LIVE] Cancel failed for {rec.exchange_order_id[:12]}: {e}")
            return {"success": False, "reason": f"CLOB cancel failed: {e}"}

    # ---- Slippage Protection ----

    def _check_slippage(self, order: OrderRecord) -> tuple:
        """Check if order price is within acceptable slippage bounds.
        Returns (ok, reason, slippage_bps).
        """
        risk = self._state.risk_config
        max_slip = risk.max_live_slippage_bps

        # Get reference price from market data
        market = self._state.get_market(order.token_id)
        if not market:
            if risk.allow_aggressive_live:
                return True, "no reference price (aggressive allowed)", None
            return False, "no reference market price — set allow_aggressive_live to override", None

        ref_price = market.mid_price if hasattr(market, 'mid_price') and market.mid_price else None
        if ref_price is None or ref_price <= 0:
            if risk.allow_aggressive_live:
                return True, "no mid-price (aggressive allowed)", None
            return False, "market has no valid mid-price — set allow_aggressive_live to override", None

        # Calculate slippage
        deviation_bps = abs(order.price - ref_price) / ref_price * 10000 if ref_price > 0 else 0

        if deviation_bps > max_slip:
            return False, f"price deviation {deviation_bps:.0f}bps > max {max_slip:.0f}bps (order={order.price:.4f} ref={ref_price:.4f})", round(deviation_bps, 2)

        return True, "slippage ok", round(deviation_bps, 2)

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

        # Slippage protection
        slip_ok, slip_reason, _ = self._check_slippage(order)
        if not slip_ok:
            self._total_slippage_rejected += 1
            return False, f"slippage protection: {slip_reason}"

        return True, "preflight passed"

    # ---- Execution ----

    async def execute(self, order: OrderRecord):
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
        order_args = OrderArgs(price=order.price, size=order.size, side=side, token_id=order.token_id)
        signed_order = self._client.create_order(order_args)
        resp = self._client.post_order(signed_order, OrderType.GTC)
        self._total_submitted += 1
        if resp and resp.get("orderID"):
            return {"success": True, "exchange_order_id": resp["orderID"], "clob_status": resp.get("status", "live")}
        elif resp and resp.get("errorMsg"):
            return {"success": False, "error": resp["errorMsg"]}
        else:
            return {"success": True, "exchange_order_id": resp.get("orderID", "unknown"), "clob_status": "submitted"}

    async def _handle_submission(self, order: OrderRecord, result: dict, latency_ms: float):
        exchange_id = result.get("exchange_order_id", "")
        self._state.update_order(order.id, status=OrderStatus.SUBMITTED, exchange_order_id=exchange_id, latency_ms=latency_ms, updated_at=utc_now())
        self._state.health["last_order_latency_ms"] = latency_ms

        market = self._state.get_market(order.token_id)
        rec = LiveOrderRecord(
            order_id=order.id, exchange_order_id=exchange_id,
            strategy_id=order.strategy_id, token_id=order.token_id,
            condition_id=market.condition_id if market else "",
            market_question=market.question if market else "",
            side=order.side.value, price=order.price,
            requested_size=order.size, filled_size=0.0,
            remaining_size=order.size, avg_fill_price=0.0,
            status="submitted", update_source="manual",
        )
        if self._live_order_service:
            await self._live_order_service.save(rec)

        logger.info(f"[LIVE] SUBMITTED {order.side.value.upper()} {order.size}@{order.price:.4f} token={order.token_id[:12]}... exch={exchange_id} ({latency_ms}ms)")
        await self._bus.emit(Event(
            type=EventType.ORDER_UPDATE, source="live_adapter",
            data={"order_id": order.id, "status": "submitted", "exchange_order_id": exchange_id, "latency_ms": latency_ms},
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
            type=EventType.RISK_ALERT, source="live_adapter",
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
        ws_connected = self._fill_ws._connected if self._fill_ws else False
        fill_method = "websocket+polling" if ws_connected else "polling"
        poll_interval = POLL_INTERVAL_WS_FALLBACK if ws_connected else POLL_INTERVAL_SECONDS
        return {
            "adapter": "live",
            "authenticated": self._authenticated,
            "credentials": creds,
            "total_submitted": self._total_submitted,
            "total_filled": self._total_filled,
            "total_partial_fills": self._total_partial,
            "total_failed": self._total_failed,
            "total_cancelled": self._total_cancelled,
            "total_slippage_rejected": self._total_slippage_rejected,
            "ws_fill_count": self._ws_fill_count,
            "poll_fill_count": self._poll_fill_count,
            "open_orders": svc.open_count if svc else 0,
            "partial_orders": svc.partial_count if svc else 0,
            "last_api_call": self._last_api_call,
            "last_status_refresh": self._last_status_refresh,
            "last_error": self._last_error,
            "recent_errors": self._recent_errors[-5:],
            "fill_update_method": fill_method,
            "poll_interval_seconds": poll_interval,
            "fill_ws_health": self._fill_ws.health if self._fill_ws else {"connected": False, "has_credentials": False},
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
