"""Live Polymarket CLOB execution adapter.

Authenticates with Polymarket's Central Limit Order Book and submits real
orders. Mirrors the PaperAdapter interface so the ExecutionEngine can swap
between them transparently.

Safety: All live orders go through the same risk engine pipeline. The adapter
adds extra pre-flight checks (mode, credentials, kill switch) before every
submission. Calls to the synchronous py-clob-client are wrapped in
asyncio.to_thread to avoid blocking the event loop.
"""

import asyncio
import logging
import os
import time
from typing import Optional

from models import (
    OrderRecord, OrderStatus, TradeRecord, Position,
    Event, EventType, utc_now, new_id,
)

logger = logging.getLogger(__name__)

POLYMARKET_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet

# Conservative defaults for live mode
LIVE_DEFAULTS = {
    "max_order_size": 2.0,
    "max_position_size": 5.0,
    "max_market_exposure": 20.0,
    "max_concurrent_positions": 3,
    "max_daily_loss": 10.0,
}


class LiveAdapter:
    """Submits real orders to Polymarket CLOB."""

    def __init__(self, state, bus):
        self._state = state
        self._bus = bus
        self._client = None
        self._authenticated = False
        self._total_submitted = 0
        self._total_filled = 0
        self._total_failed = 0
        self._last_error: Optional[str] = None

    # ---- Credentials ----

    @staticmethod
    def credentials_present() -> dict:
        """Check which credentials are set."""
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

    async def initialize(self) -> bool:
        """Attempt to authenticate with Polymarket CLOB. Returns True if successful."""
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
                logger.info("LiveAdapter authenticated with Polymarket CLOB")
            return result
        except Exception as e:
            self._authenticated = False
            self._last_error = str(e)
            logger.error(f"LiveAdapter init failed: {e}")
            return False

    def _sync_init(self) -> bool:
        """Synchronous CLOB client initialization."""
        from py_clob_client.client import ClobClient

        private_key = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
        funder = os.environ.get("POLYMARKET_FUNDER_ADDRESS", "").strip()

        if funder:
            self._client = ClobClient(
                POLYMARKET_HOST,
                key=private_key,
                chain_id=CHAIN_ID,
                signature_type=1,
                funder=funder,
            )
        else:
            self._client = ClobClient(
                POLYMARKET_HOST,
                key=private_key,
                chain_id=CHAIN_ID,
            )

        # Set API credentials
        api_key = os.environ.get("POLYMARKET_API_KEY", "").strip()
        api_secret = os.environ.get("POLYMARKET_API_SECRET", "").strip()
        passphrase = os.environ.get("POLYMARKET_PASSPHRASE", "").strip()

        if api_key and api_secret and passphrase:
            from py_clob_client.clob_types import ApiCreds
            self._client.set_api_creds(ApiCreds(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=passphrase,
            ))
        else:
            # Derive credentials from private key
            self._client.set_api_creds(self._client.create_or_derive_api_creds())

        return True

    # ---- Pre-flight checks ----

    def _preflight_check(self, order: OrderRecord) -> tuple:
        """Extra safety checks before live execution. Returns (ok, reason)."""
        if not self._authenticated:
            return False, "live adapter not authenticated"

        if not self._client:
            return False, "CLOB client not initialized"

        if self._state.trading_mode.value != "live":
            return False, f"trading mode is '{self._state.trading_mode.value}', not 'live'"

        if self._state.risk_config.kill_switch_active:
            return False, "kill switch is active"

        # Enforce conservative live limits
        if order.size > LIVE_DEFAULTS["max_order_size"]:
            return False, f"live order size {order.size} > safe max {LIVE_DEFAULTS['max_order_size']}"

        return True, "preflight passed"

    # ---- Execution ----

    async def execute(self, order: OrderRecord):
        """Submit a real order to Polymarket CLOB."""
        t_start = time.time()

        # Pre-flight safety
        ok, reason = self._preflight_check(order)
        if not ok:
            await self._reject_order(order, reason, t_start)
            return

        try:
            result = await asyncio.to_thread(self._sync_execute, order)
            latency_ms = round((time.time() - t_start) * 1000, 2)

            if result.get("success"):
                await self._handle_fill(order, result, latency_ms)
            else:
                await self._reject_order(order, result.get("error", "CLOB submission failed"), t_start)

        except Exception as e:
            self._total_failed += 1
            self._last_error = str(e)
            logger.error(f"[LIVE] Order {order.id} execution error: {e}")
            await self._reject_order(order, f"execution error: {e}", t_start)

    def _sync_execute(self, order: OrderRecord) -> dict:
        """Synchronous order submission to Polymarket CLOB."""
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        side = BUY if order.side.value == "buy" else SELL

        order_args = OrderArgs(
            price=order.price,
            size=order.size,
            side=side,
            token_id=order.token_id,
        )

        signed_order = self._client.create_order(order_args)
        resp = self._client.post_order(signed_order, OrderType.GTC)

        self._total_submitted += 1

        if resp and resp.get("orderID"):
            return {
                "success": True,
                "exchange_order_id": resp["orderID"],
                "status": resp.get("status", "live"),
            }
        elif resp and resp.get("errorMsg"):
            return {
                "success": False,
                "error": resp["errorMsg"],
            }
        else:
            return {
                "success": True,
                "exchange_order_id": resp.get("orderID", "unknown"),
                "status": "submitted",
            }

    async def _handle_fill(self, order: OrderRecord, result: dict, latency_ms: float):
        """Process a successful order submission."""
        exchange_id = result.get("exchange_order_id", "")
        fill_price = order.price  # Use order price as initial fill price

        self._state.update_order(
            order.id,
            status=OrderStatus.SUBMITTED,
            exchange_order_id=exchange_id,
            updated_at=utc_now(),
        )

        # Record trade (treat submission as fill for now — full fill tracking in future phase)
        market = self._state.get_market(order.token_id)
        mkt_question = market.question if market else ""
        mkt_outcome = market.outcome if market else ""

        trade = TradeRecord(
            id=new_id(),
            order_id=order.id,
            token_id=order.token_id,
            market_question=mkt_question,
            outcome=mkt_outcome,
            side=order.side,
            price=fill_price,
            size=order.size,
            fees=round(order.size * fill_price * 0.002, 4),
            strategy_id=order.strategy_id,
            signal_reason="live_submission",
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
                    market_question=mkt_question,
                    outcome=mkt_outcome,
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

        self._total_filled += 1
        self._state.health["last_order_latency_ms"] = latency_ms
        logger.info(f"[LIVE] {order.side.value.upper()} {order.size}@{fill_price:.4f} token={order.token_id[:12]}... exch_id={exchange_id} ({latency_ms}ms)")

        await self._bus.emit(Event(
            type=EventType.ORDER_UPDATE,
            source="live_adapter",
            data={
                "order_id": order.id,
                "status": "filled",
                "fill_price": fill_price,
                "latency_ms": latency_ms,
                "exchange_order_id": exchange_id,
            },
        ))

    async def _reject_order(self, order: OrderRecord, reason: str, t_start: float):
        """Handle order rejection."""
        self._total_failed += 1
        self._last_error = reason
        latency_ms = round((time.time() - t_start) * 1000, 2)

        self._state.update_order(order.id, status=OrderStatus.REJECTED)
        logger.warning(f"[LIVE] Order {order.id} rejected: {reason} ({latency_ms}ms)")

        await self._bus.emit(Event(
            type=EventType.RISK_ALERT,
            source="live_adapter",
            data={"order_id": order.id, "reason": reason, "action": "live_order_rejected"},
        ))

    # ---- Status ----

    @property
    def status(self) -> dict:
        creds = self.credentials_present()
        return {
            "adapter": "live",
            "authenticated": self._authenticated,
            "credentials": creds,
            "total_submitted": self._total_submitted,
            "total_filled": self._total_filled,
            "total_failed": self._total_failed,
            "last_error": self._last_error,
        }

    async def get_balance(self) -> Optional[float]:
        """Get USDC balance from Polymarket. Returns None if not authenticated."""
        if not self._authenticated or not self._client:
            return None
        try:
            balance_wei = await asyncio.to_thread(self._client.get_balance)
            return int(balance_wei) / 1e6
        except Exception as e:
            logger.warning(f"Balance check failed: {e}")
            return None
