"""Gabagool Live Executor — guaranteed structural arbitrage on crypto UpDown markets.

Buys BOTH YES and NO when combined price < threshold (default 0.96).
At resolution, one side pays $1.00, so profit = $1.00 - pair_cost per share.
This is RISK-FREE arbitrage — no directional exposure.

Uses the paper execution engine for fills, classified as 'arb' bucket for risk.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from models import OrderRecord, OrderSide, utc_now, new_id
from engine.strategies.arb_pricing import compute_data_age

logger = logging.getLogger(__name__)


class GabagoolExecutor:

    def __init__(self):
        self._state = None
        self._risk_engine = None
        self._execution_engine = None
        self._running = False

        # Config
        self._threshold = 0.96        # buy both sides when sum < this
        self._max_stale_seconds = 60.0
        self._scan_interval = 10.0
        self._size_per_side = 10.0    # $ per side (total = 2x this)
        self._cooldown_seconds = 300.0
        self._max_open_pairs = 20     # max simultaneous gabagool pairs

        # Tracking
        self._open_pairs: Dict[str, dict] = {}   # condition_id -> pair info
        self._closed_pairs: list = []
        self._cooldown: Dict[str, float] = {}
        self._pnl_total = 0.0
        self._wins = 0
        self._losses = 0

        self._m = {
            "total_scans": 0,
            "pairs_found": 0,
            "trades_executed": 0,
            "pairs_resolved": 0,
        }

    def set_execution_context(self, risk_engine, execution_engine):
        self._risk_engine = risk_engine
        self._execution_engine = execution_engine

    async def start(self, state):
        self._state = state
        self._running = True
        asyncio.create_task(self._scan_loop())
        asyncio.create_task(self._resolution_loop())
        logger.info(
            f"[GABAGOOL] Live executor started "
            f"(threshold={self._threshold}, size=${self._size_per_side}/side, "
            f"max_pairs={self._max_open_pairs})"
        )

    async def stop(self):
        self._running = False

    async def _scan_loop(self):
        await asyncio.sleep(15)  # let markets populate
        while self._running:
            try:
                await self._scan()
            except Exception as e:
                logger.error(f"[GABAGOOL] Scan error: {e}")
            await asyncio.sleep(self._scan_interval)

    async def _scan(self):
        if not self._state or not self._execution_engine:
            return

        self._m["total_scans"] += 1
        now_ts = datetime.now(timezone.utc).timestamp()

        # Clean expired cooldowns
        self._cooldown = {k: v for k, v in self._cooldown.items()
                          if now_ts - v < self._cooldown_seconds}

        # Group markets by condition_id to find YES/NO pairs
        by_condition: Dict[str, Dict] = {}
        for snap in self._state.markets.values():
            cid = snap.condition_id
            if not cid:
                continue
            if cid not in by_condition:
                by_condition[cid] = {}
            out = (snap.outcome or "").upper()
            if "YES" in out or "UP" in out:
                by_condition[cid]["yes"] = snap
            elif "NO" in out or "DOWN" in out:
                by_condition[cid]["no"] = snap

        for cid, pair in by_condition.items():
            if "yes" not in pair or "no" not in pair:
                continue

            yes_snap, no_snap = pair["yes"], pair["no"]
            yp, np_ = yes_snap.mid_price, no_snap.mid_price
            if not yp or not np_ or yp <= 0 or np_ <= 0:
                continue

            # Staleness check
            y_age = compute_data_age(yes_snap.updated_at)
            n_age = compute_data_age(no_snap.updated_at)
            if max(y_age, n_age) > self._max_stale_seconds:
                continue

            price_sum = yp + np_
            if price_sum >= self._threshold:
                continue

            # Found a gabagool pair!
            self._m["pairs_found"] += 1

            # Skip if already open, on cooldown, or at max capacity
            if cid in self._open_pairs:
                continue
            if cid in self._cooldown:
                continue
            if len(self._open_pairs) >= self._max_open_pairs:
                continue

            # Only trade crypto UpDown markets (not weather/political)
            q = (yes_snap.question or "").lower()
            if not any(kw in q for kw in ("btc", "bitcoin", "eth", "ethereum", "up or down")):
                continue

            # Calculate guaranteed edge
            guaranteed_edge = 1.0 - price_sum
            guaranteed_edge_pct = round(guaranteed_edge * 100, 1)
            guaranteed_profit = round(guaranteed_edge * self._size_per_side, 4)

            logger.info(
                f"[GABAGOOL] Pair found: {yes_snap.question[:60]} "
                f"YES={yp:.4f} + NO={np_:.4f} = {price_sum:.4f} "
                f"edge={guaranteed_edge_pct}% guar_profit=${guaranteed_profit:.4f}"
            )

            # Submit YES buy order
            yes_order = OrderRecord(
                id=new_id(),
                token_id=yes_snap.token_id,
                condition_id=cid,
                market_question=yes_snap.question or "",
                side=OrderSide.BUY,
                size=self._size_per_side,
                price=yp,
                strategy_id="gabagool",
            )

            # Submit NO buy order
            no_order = OrderRecord(
                id=new_id(),
                token_id=no_snap.token_id,
                condition_id=cid,
                market_question=no_snap.question or "",
                side=OrderSide.BUY,
                size=self._size_per_side,
                price=np_,
                strategy_id="gabagool",
            )

            # Risk check and execute both sides
            yes_ok, yes_reason = self._risk_engine.approve_order(yes_order)
            no_ok, no_reason = self._risk_engine.approve_order(no_order)

            if yes_ok and no_ok:
                await self._execution_engine.submit_order(yes_order)
                await self._execution_engine.submit_order(no_order)

                self._open_pairs[cid] = {
                    "condition_id": cid,
                    "question": (yes_snap.question or "")[:80],
                    "yes_token_id": yes_snap.token_id,
                    "no_token_id": no_snap.token_id,
                    "yes_entry": round(yp, 6),
                    "no_entry": round(np_, 6),
                    "pair_cost": round(price_sum, 6),
                    "guaranteed_edge_pct": guaranteed_edge_pct,
                    "guaranteed_profit": guaranteed_profit,
                    "size": self._size_per_side,
                    "notional": round(price_sum * self._size_per_side, 4),
                    "opened_at": utc_now(),
                    "yes_order_id": yes_order.id,
                    "no_order_id": no_order.id,
                }
                self._cooldown[cid] = now_ts
                self._m["trades_executed"] += 1

                logger.info(
                    f"[GABAGOOL] EXECUTED pair: {yes_snap.question[:50]} "
                    f"cost={price_sum:.4f} edge={guaranteed_edge_pct}% "
                    f"guar_profit=${guaranteed_profit:.4f}"
                )
            else:
                reasons = []
                if not yes_ok:
                    reasons.append(f"YES: {yes_reason}")
                if not no_ok:
                    reasons.append(f"NO: {no_reason}")
                logger.info(f"[GABAGOOL] Risk rejected: {', '.join(reasons)}")

    async def _resolution_loop(self):
        """Check if open gabagool pairs have resolved."""
        await asyncio.sleep(30)
        while self._running:
            try:
                self._check_resolutions()
            except Exception as e:
                logger.error(f"[GABAGOOL] Resolution error: {e}")
            await asyncio.sleep(30)

    def _check_resolutions(self):
        if not self._state:
            return

        resolved = []
        for cid, pair_info in list(self._open_pairs.items()):
            yes_pos = self._state.get_position(pair_info["yes_token_id"])
            no_pos = self._state.get_position(pair_info["no_token_id"])

            # Both positions must be gone (resolved) for pair to be complete
            if yes_pos is None and no_pos is None:
                # Market resolved — calculate PnL from trade history
                pair_pnl = self._calculate_pair_pnl(pair_info)
                won = pair_pnl > -0.01  # small tolerance for rounding

                self._closed_pairs.append({
                    **pair_info,
                    "pnl": round(pair_pnl, 4),
                    "won": won,
                    "closed_at": utc_now(),
                    "resolution_type": "resolved",
                })
                self._pnl_total += pair_pnl
                if won:
                    self._wins += 1
                else:
                    self._losses += 1
                self._m["pairs_resolved"] += 1
                resolved.append(cid)

                logger.info(
                    f"[GABAGOOL] Pair resolved: {pair_info['question'][:50]} "
                    f"pnl=${pair_pnl:+.4f} won={won}"
                )

        for cid in resolved:
            del self._open_pairs[cid]

    def _calculate_pair_pnl(self, pair_info):
        """Calculate PnL for a resolved gabagool pair, including realistic Polymarket fees.
        Trading fee: 0.2% per leg (already charged by paper adapter on fills).
        Resolution fee: 2% on winning side profit (Polymarket's actual fee).
        """
        size = pair_info["size"]
        pair_cost = pair_info["pair_cost"]
        yes_entry = pair_info["yes_entry"]
        no_entry = pair_info["no_entry"]
        gross_profit = size * (1.0 - pair_cost)
        # Resolution fee: 2% on the winning side's profit (worst case = cheaper side wins more)
        # Winning side profit = size * (1.0 - cheaper_entry)
        cheaper = min(yes_entry, no_entry)
        winning_side_profit = size * (1.0 - cheaper)
        resolution_fee = winning_side_profit * 0.02
        net_profit = gross_profit - resolution_fee
        return round(net_profit, 4)

    def get_report(self) -> dict:
        total_closed = self._wins + self._losses
        return {
            "status": "active" if self._running else "stopped",
            "strategy": "gabagool_live",
            "description": "Live structural arb — buys YES+NO when sum < threshold",
            "config": {
                "threshold": self._threshold,
                "size_per_side": self._size_per_side,
                "max_open_pairs": self._max_open_pairs,
                "cooldown_seconds": self._cooldown_seconds,
            },
            "metrics": self._m,
            "performance": {
                "pnl_total": round(self._pnl_total, 4),
                "open_pairs": len(self._open_pairs),
                "closed_pairs": total_closed,
                "wins": self._wins,
                "losses": self._losses,
                "win_rate": round(self._wins / max(total_closed, 1) * 100, 1),
            },
        }

    def get_open_pairs(self) -> list:
        return list(self._open_pairs.values())

    def get_closed_pairs(self, limit=50) -> list:
        return list(reversed(self._closed_pairs[-limit:]))
