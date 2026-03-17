"""Global Market Resolver — closes positions when markets resolve.

Runs every 30s, checks all open positions against Polymarket Gamma API.
When a market is resolved (closed=True, outcomePrices shows 1/0),
computes realized PnL and removes the position.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import aiohttp

from models import (
    TradeRecord, OrderSide, Event, EventType, utc_now, new_id,
)

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"


class MarketResolverService:
    def __init__(self, tracker=None, on_trade_closed=None):
        self._state = None
        self._bus = None
        self._running = False
        self._task = None
        self._tracker = tracker
        self._on_trade_closed = on_trade_closed  # async callback
        self._session = None

        # Stats
        self._stats = {
            "total_runs": 0,
            "last_run": None,
            "last_run_duration_ms": 0,
            "positions_checked": 0,
            "markets_queried": 0,
            "positions_resolved": 0,
            "total_realized_pnl": 0.0,
            "wins": 0,
            "losses": 0,
            "errors": 0,
            "recent_resolutions": [],
        }

    @property
    def health(self) -> dict:
        return {
            "running": self._running,
            "interval_seconds": 30,
            **self._stats,
        }

    async def start(self, state, bus):
        self._state = state
        self._bus = bus
        self._running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"User-Agent": "PolymarketEdgeOS/1.0"},
        )
        self._task = asyncio.create_task(self._resolve_loop())
        logger.info("[RESOLVER] Market resolver started (interval=30s)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
        logger.info("[RESOLVER] Market resolver stopped")

    async def _resolve_loop(self):
        await asyncio.sleep(10)  # let feeds settle on startup
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[RESOLVER] Loop error: {e}", exc_info=True)
                self._stats["errors"] += 1
            await asyncio.sleep(30)

    async def run_once(self) -> dict:
        """Single resolution pass. Returns summary."""
        if not self._state:
            return {"error": "not initialized"}

        t0 = time.monotonic()
        positions = list(self._state.positions.items())
        now = datetime.now(timezone.utc)

        resolved_count = 0
        total_pnl = 0.0
        queried = 0
        already_checked = set()  # track condition_ids already queried this pass
        skip_reasons = {"no_market": 0, "no_end_date": 0, "not_expired": 0, "already_checked": 0}

        for token_id, pos in positions:
            if not self._running:
                break

            market = self._state.get_market(token_id)
            if not market:
                skip_reasons["no_market"] += 1
                continue
            if not market.end_date:
                skip_reasons["no_end_date"] += 1
                continue

            # Check if expired
            try:
                end_dt = datetime.fromisoformat(
                    market.end_date.replace("Z", "+00:00")
                )
                if end_dt > now:
                    skip_reasons["not_expired"] += 1
                    continue  # not expired yet
            except (ValueError, TypeError):
                skip_reasons["no_end_date"] += 1
                continue

            # Skip if we already checked this token's condition this pass
            cid = market.condition_id or token_id
            if cid in already_checked:
                skip_reasons["already_checked"] += 1
                continue
            already_checked.add(cid)

            # Query Gamma API for resolution using clob_token_id (unique per outcome)
            resolution = await self._check_resolution_by_token(token_id)
            queried += 1
            if not resolution:
                continue

            winning_outcome = resolution["winning_outcome"]
            if winning_outcome is None:
                continue  # Closed but not yet resolved

            # Find all positions sharing this market (both Up/Down sides)
            sibling_tokens = [token_id]
            if market.complement_token_id:
                sibling_tokens.append(market.complement_token_id)

            for tid in sibling_tokens:
                sib_pos = self._state.positions.get(tid)
                sib_market = self._state.get_market(tid)
                if not sib_pos or not sib_market:
                    continue
                outcome = (sib_market.outcome or "").strip()
                position_won = outcome.lower() == winning_outcome.lower()
                settlement_price = 1.0 if position_won else 0.0

                pnl = round((settlement_price - sib_pos.avg_cost) * sib_pos.size, 4)
                total_pnl += pnl

                # Use the original strategy that opened the position
                original_strategy = getattr(sib_pos, "strategy_id", "") or "unknown"

                trade = TradeRecord(
                    id=new_id(),
                    order_id="resolution",
                    token_id=tid,
                    market_question=sib_pos.market_question,
                    outcome=outcome,
                    side=OrderSide.SELL,
                    price=settlement_price,
                    size=sib_pos.size,
                    fees=0.0,
                    pnl=pnl,
                    strategy_id=original_strategy,
                    signal_reason=f"market_resolved:{winning_outcome}",
                )
                self._state.add_trade(trade)
                if self._tracker:
                    self._tracker.record_close(original_strategy, pnl)

                self._state.positions.pop(tid, None)
                resolved_count += 1

                if pnl >= 0:
                    self._stats["wins"] += 1
                else:
                    self._stats["losses"] += 1

                logger.info(
                    f"[RESOLVER] Closed: {sib_pos.market_question[:40]}... "
                    f"outcome={outcome} won={position_won} "
                    f"pnl=${pnl:+.4f} (cost={sib_pos.avg_cost:.4f} settle={settlement_price})"
                )

                self._stats["recent_resolutions"].append({
                    "token_id": tid[:16] + "...",
                    "question": sib_pos.market_question[:60],
                    "outcome": outcome,
                    "won": position_won,
                    "pnl": pnl,
                    "size": sib_pos.size,
                    "avg_cost": sib_pos.avg_cost,
                    "resolved_at": utc_now(),
                })
                if len(self._stats["recent_resolutions"]) > 50:
                    self._stats["recent_resolutions"] = self._stats["recent_resolutions"][-50:]

            # Small delay between API calls
            await asyncio.sleep(0.1)

        elapsed_ms = (time.monotonic() - t0) * 1000
        self._stats["total_runs"] += 1
        self._stats["last_run"] = utc_now()
        self._stats["last_run_duration_ms"] = round(elapsed_ms, 1)
        self._stats["positions_checked"] = len(positions)
        self._stats["markets_queried"] += queried
        self._stats["positions_resolved"] += resolved_count
        self._stats["skip_reasons"] = skip_reasons
        self._stats["total_realized_pnl"] = round(
            self._stats["total_realized_pnl"] + total_pnl, 4
        )

        if resolved_count:
            logger.info(
                f"[RESOLVER] Pass complete: {resolved_count} resolved, "
                f"pnl=${total_pnl:+.4f}, {queried} markets queried "
                f"({elapsed_ms:.0f}ms)"
            )

            # Emit event for notification system
            if self._bus:
                await self._bus.emit(Event(
                    type=EventType.SYSTEM_EVENT,
                    source="market_resolver",
                    data={
                        "action": "positions_resolved",
                        "count": resolved_count,
                        "pnl": total_pnl,
                    },
                ))

            # Immediate WS push so frontend sees the new close instantly
            if resolved_count > 0 and self._on_trade_closed:
                try:
                    await self._on_trade_closed()
                except Exception:
                    pass

        return {
            "resolved": resolved_count,
            "pnl": round(total_pnl, 4),
            "queried": queried,
            "checked": len(positions),
            "duration_ms": round(elapsed_ms, 1),
        }

    async def _check_resolution_by_token(self, clob_token_id: str) -> dict | None:
        """Query Gamma API by CLOB token ID for unique market resolution.

        Returns {winning_outcome: str} if resolved, None otherwise.
        """
        try:
            async with self._session.get(
                f"{GAMMA_API}/markets",
                params={"clob_token_ids": clob_token_id},
            ) as resp:
                if resp.status != 200:
                    return None
                markets = await resp.json()
                if not markets:
                    return None

            market = markets[0]
            if not market.get("closed", False):
                return None

            # Parse outcome prices to determine winner
            try:
                outcome_prices = json.loads(
                    market.get("outcomePrices", "[]")
                )
                outcomes = json.loads(market.get("outcomes", "[]"))
            except (json.JSONDecodeError, TypeError):
                return None

            if not outcomes or not outcome_prices:
                return None

            # Winner has price == "1" or closest to 1.0
            winning_idx = None
            for i, price_str in enumerate(outcome_prices):
                try:
                    price = float(price_str)
                    if price >= 0.99:
                        winning_idx = i
                        break
                except (ValueError, TypeError):
                    continue

            if winning_idx is None:
                return None  # Closed but prices not yet settled to 0/1

            winning_outcome = outcomes[winning_idx] if winning_idx < len(outcomes) else None
            return {"winning_outcome": winning_outcome}

        except Exception as e:
            logger.warning(f"[RESOLVER] API error for token {clob_token_id[:16]}...: {e}")
            self._stats["errors"] += 1
            return None
