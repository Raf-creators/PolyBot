"""Global Market Resolver — closes positions when markets resolve.

Runs every 30s, checks all open positions against Polymarket Gamma API.
When a market is resolved (closed=True, outcomePrices shows 1/0),
computes realized PnL and removes the position.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
import re

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
        # Grace period before force-resolving zombie positions (hours past end_date)
        self._zombie_grace_hours = 6.0

        # Stats
        self._stats = {
            "total_runs": 0,
            "last_run": None,
            "last_run_duration_ms": 0,
            "positions_checked": 0,
            "markets_queried": 0,
            "positions_resolved": 0,
            "zombies_force_resolved": 0,
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

        # ---- Second pass: Force-resolve zombie positions ----
        # Positions that are past end_date + grace period and were NOT resolved by Gamma API
        # If end_date is missing, infer expiry from market question text (date parsing)
        zombie_count = 0
        zombie_pnl = 0.0
        remaining_positions = list(self._state.positions.items())
        grace_td = timedelta(hours=self._zombie_grace_hours)

        for token_id, pos in remaining_positions:
            if not self._running:
                break

            market = self._state.get_market(token_id)

            # Try to determine end_date from multiple sources
            end_dt = None

            # Source 1: market.end_date
            if market and market.end_date:
                try:
                    end_dt = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            # Source 2: Parse date from market question text
            if end_dt is None:
                end_dt = self._infer_expiry_from_question(
                    getattr(pos, 'market_question', '') or (market.question if market else '')
                )

            if end_dt is None:
                continue

            # Only force-resolve if past end_date + grace period
            if now < end_dt + grace_td:
                continue

            # This position is a zombie — force-resolve at current market price
            current_price = 0
            if market and market.mid_price:
                current_price = market.mid_price
            elif pos.current_price:
                current_price = pos.current_price

            pnl = round((current_price - pos.avg_cost) * pos.size, 4)
            zombie_pnl += pnl
            total_pnl += pnl

            original_strategy = getattr(pos, "strategy_id", "") or "unknown"
            outcome = ""
            if market and market.outcome:
                outcome = market.outcome.strip()

            trade = TradeRecord(
                id=new_id(),
                order_id="zombie_force_resolve",
                token_id=token_id,
                market_question=pos.market_question,
                outcome=outcome,
                side=OrderSide.SELL,
                price=current_price,
                size=pos.size,
                fees=0.0,
                pnl=pnl,
                strategy_id=original_strategy,
                signal_reason=f"zombie_force_resolve:expired_{self._zombie_grace_hours:.0f}h",
            )
            self._state.add_trade(trade)
            if self._tracker:
                self._tracker.record_close(original_strategy, pnl)

            self._state.positions.pop(token_id, None)
            zombie_count += 1

            if pnl >= 0:
                self._stats["wins"] += 1
            else:
                self._stats["losses"] += 1

            hours_expired = (now - end_dt).total_seconds() / 3600
            logger.warning(
                f"[RESOLVER] Zombie force-resolved: {pos.market_question[:40]}... "
                f"outcome={outcome} pnl=${pnl:+.4f} "
                f"(expired {hours_expired:.1f}h ago, strategy={original_strategy})"
            )

            self._stats["recent_resolutions"].append({
                "token_id": token_id[:16] + "...",
                "question": pos.market_question[:60],
                "outcome": outcome,
                "won": pnl >= 0,
                "pnl": pnl,
                "size": pos.size,
                "avg_cost": pos.avg_cost,
                "resolved_at": utc_now(),
                "type": "zombie_force_resolve",
            })
            if len(self._stats["recent_resolutions"]) > 50:
                self._stats["recent_resolutions"] = self._stats["recent_resolutions"][-50:]

        resolved_count += zombie_count
        self._stats["zombies_force_resolved"] += zombie_count
        if zombie_count > 0:
            logger.info(
                f"[RESOLVER] Force-resolved {zombie_count} zombie positions, "
                f"zombie_pnl=${zombie_pnl:+.4f}"
            )

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
            "zombies_force_resolved": zombie_count,
            "pnl": round(total_pnl, 4),
            "queried": queried,
            "checked": len(positions),
            "duration_ms": round(elapsed_ms, 1),
        }

    def _infer_expiry_from_question(self, question: str) -> datetime | None:
        """Infer market expiry datetime from the question text.

        Parses patterns like:
        - "March 17" / "March 17, 2026"
        - "3:00PM-4:00PM ET" (use the end time)
        - "March 17, 6:00PM-6:05PM ET"
        """
        if not question:
            return None

        try:
            now = datetime.now(timezone.utc)
            year = now.year

            # Pattern: "Month Day" with optional time window
            month_map = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12,
            }

            # Match "March 17" style dates
            date_match = re.search(
                r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})',
                question, re.IGNORECASE
            )
            if not date_match:
                return None

            month = month_map[date_match.group(1).lower()]
            day = int(date_match.group(2))

            # Try to find end time like "6:05PM" or "8:00PM" in time ranges
            time_match = re.search(r'(\d{1,2}):(\d{2})(AM|PM)', question.split('-')[-1] if '-' in question else question, re.IGNORECASE)
            hour, minute = 23, 59  # default to end of day
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                ampm = time_match.group(3).upper()
                if ampm == 'PM' and hour != 12:
                    hour += 12
                elif ampm == 'AM' and hour == 12:
                    hour = 0

            # Build datetime (assume ET = UTC-5, but use UTC with offset)
            try:
                end_dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
                # ET is UTC-5 (EST) or UTC-4 (EDT), add 5 hours to convert to UTC
                end_dt += timedelta(hours=5)
            except ValueError:
                return None

            return end_dt

        except Exception:
            return None

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
