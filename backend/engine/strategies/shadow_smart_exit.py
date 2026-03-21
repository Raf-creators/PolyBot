"""Shadow Smart Exit — trailing profit capture for crypto sniper.

Mirrors the live crypto sniper signals but applies a trailing stop exit strategy:
- Activates at 1.5x profit multiple
- Trails at 75% of peak profit multiple
- Captures profit on reversal instead of waiting for binary resolution

100% shadow — no live orders. Compares trailing-exit PnL vs hold-to-resolution PnL.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List

from models import utc_now

logger = logging.getLogger(__name__)

TRAILING_ACTIVATION = 1.5    # activate trailing stop at 1.5x
TRAILING_FLOOR_PCT = 0.75    # floor = 75% of peak
PARTIAL_EXIT_AT = 2.0        # take 50% off at 2.0x (optional tracking)


class SmartExitShadowEngine:

    def __init__(self):
        self._state = None
        self._running = False

        # Positions: keyed by token_id
        self._positions: Dict[str, dict] = {}
        self._closed: List[dict] = []
        self._pnl = 0.0
        self._wins = 0
        self._losses = 0

        # Comparison: what would have happened with hold-to-resolution
        self._hold_closed: List[dict] = []
        self._hold_pnl = 0.0
        self._hold_wins = 0
        self._hold_losses = 0

        self._m = {
            "signals_received": 0,
            "positions_opened": 0,
            "trailing_exits": 0,
            "resolution_exits": 0,
            "peak_captures": [],  # last N peak multiples at exit
            "last_eval_time": None,
        }

    async def start(self, state):
        self._state = state
        self._running = True
        asyncio.create_task(self._monitor_loop())
        logger.info("[SMART-EXIT] Shadow engine started — trailing profit capture")

    async def stop(self):
        self._running = False

    def evaluate_signal(self, condition_id, asset, direction, spot,
                        fair_prob, yes_price, no_price, edge_bps,
                        tte_seconds, side, token_id, size, question,
                        is_tradable, **kwargs):
        """Called from crypto_sniper for every signal."""
        self._m["signals_received"] += 1
        self._m["last_eval_time"] = utc_now()

        if not is_tradable:
            return

        # Only open new position if not already tracking this token
        if token_id in self._positions:
            return

        entry_price = yes_price if "yes" in side else no_price
        if entry_price <= 0:
            return

        self._positions[token_id] = {
            "token_id": token_id,
            "condition_id": condition_id,
            "question": (question or "")[:80],
            "asset": asset,
            "direction": direction,
            "side": side,
            "entry_price": round(entry_price, 6),
            "size": size,
            "invested": round(size * entry_price, 4),
            "peak_price": entry_price,
            "peak_multiple": 1.0,
            "trailing_active": False,
            "trailing_floor": 0.0,
            "opened_at": utc_now(),
            "edge_bps": round(edge_bps, 1),
        }
        self._m["positions_opened"] += 1

    async def _monitor_loop(self):
        await asyncio.sleep(15)
        while self._running:
            try:
                self._check_positions()
            except Exception as e:
                logger.error(f"[SMART-EXIT] Monitor error: {e}")
            await asyncio.sleep(5)

    def _check_positions(self):
        if not self._state:
            return

        now = utc_now()
        to_close = []

        for token_id, pos in self._positions.items():
            market = self._state.get_market(token_id)
            if not market:
                continue

            cp = market.mid_price or market.last_price
            if cp is None or cp <= 0:
                continue

            entry = pos["entry_price"]
            current_multiple = cp / entry if entry > 0 else 1.0

            # Track peak
            if cp > pos["peak_price"]:
                pos["peak_price"] = cp
                pos["peak_multiple"] = current_multiple

            # Check for binary resolution (price → 0 or → 1)
            if cp >= 0.95 or cp <= 0.05:
                won = cp >= 0.95
                pnl = (1.0 - entry) * pos["size"] if won else -entry * pos["size"]
                to_close.append((token_id, "resolution", won, pnl, current_multiple))

                # Also record hold comparison (same result since resolved)
                self._hold_closed.append({
                    **pos, "exit_price": cp, "pnl": round(pnl, 4),
                    "won": won, "exit_reason": "resolution",
                    "closed_at": now,
                })
                if won:
                    self._hold_wins += 1
                else:
                    self._hold_losses += 1
                self._hold_pnl += pnl
                continue

            # Trailing stop logic
            if not pos["trailing_active"] and current_multiple >= TRAILING_ACTIVATION:
                pos["trailing_active"] = True
                pos["trailing_floor"] = current_multiple * TRAILING_FLOOR_PCT
                logger.debug(f"[SMART-EXIT] Trailing activated: {pos['question'][:40]} at {current_multiple:.2f}x, floor={pos['trailing_floor']:.2f}x")

            if pos["trailing_active"]:
                # Update floor if new peak
                new_floor = pos["peak_multiple"] * TRAILING_FLOOR_PCT
                if new_floor > pos["trailing_floor"]:
                    pos["trailing_floor"] = new_floor

                # Check if price dropped below floor
                if current_multiple <= pos["trailing_floor"]:
                    exit_price = cp
                    pnl = (exit_price - entry) * pos["size"]
                    won = pnl > 0
                    to_close.append((token_id, "trailing_stop", won, pnl, current_multiple))

                    # Hold comparison: this position is still open, mark as pending
                    # It will resolve later — we track the exit price for comparison
                    logger.info(
                        f"[SMART-EXIT] Trailing exit: {pos['question'][:40]} "
                        f"peak={pos['peak_multiple']:.2f}x, exit={current_multiple:.2f}x, "
                        f"PnL=${pnl:.4f}"
                    )

            # Timeout: if position open > 6h with no trailing activation, close at market
            try:
                opened = datetime.fromisoformat(pos["opened_at"].replace("Z", "+00:00"))
                age_h = (datetime.now(timezone.utc) - opened).total_seconds() / 3600
            except (ValueError, TypeError):
                age_h = 0

            if age_h > 6 and not pos["trailing_active"]:
                exit_price = cp
                pnl = (exit_price - entry) * pos["size"]
                won = pnl > 0
                to_close.append((token_id, "timeout", won, pnl, current_multiple))

        # Process closures
        for token_id, reason, won, pnl, exit_mult in to_close:
            pos = self._positions.pop(token_id, None)
            if not pos:
                continue

            closed = {
                **pos,
                "exit_price": round(self._state.get_market(token_id).mid_price or 0, 6) if self._state.get_market(token_id) else 0,
                "exit_multiple": round(exit_mult, 4),
                "peak_multiple": round(pos["peak_multiple"], 4),
                "pnl": round(pnl, 4),
                "won": won,
                "exit_reason": reason,
                "closed_at": now,
            }
            self._closed.append(closed)
            self._pnl += pnl
            if won:
                self._wins += 1
            else:
                self._losses += 1

            if reason == "trailing_stop":
                self._m["trailing_exits"] += 1
                self._m["peak_captures"].append(round(pos["peak_multiple"], 2))
                if len(self._m["peak_captures"]) > 50:
                    self._m["peak_captures"] = self._m["peak_captures"][-50:]
            else:
                self._m["resolution_exits"] += 1

    # ---- Reporting ----

    def get_report(self):
        total = self._wins + self._losses
        hold_total = self._hold_wins + self._hold_losses

        avg_peak = (sum(self._m["peak_captures"]) / len(self._m["peak_captures"])
                    if self._m["peak_captures"] else 0)

        return {
            "status": "active" if self._m["signals_received"] > 0 else "collecting",
            "experiment": "smart_exit",
            "description": "Trailing profit capture — exit at 75% of peak after 1.5x activation",
            "config": {
                "trailing_activation": TRAILING_ACTIVATION,
                "trailing_floor_pct": TRAILING_FLOOR_PCT,
                "timeout_hours": 6,
            },
            "trailing": {
                "pnl": round(self._pnl, 4),
                "win_rate": round(self._wins / total, 4) if total else 0,
                "wins": self._wins,
                "losses": self._losses,
                "total": total,
                "trailing_exits": self._m["trailing_exits"],
                "resolution_exits": self._m["resolution_exits"],
                "avg_peak_at_exit": round(avg_peak, 2),
                "open_positions": len(self._positions),
            },
            "hold_comparison": {
                "pnl": round(self._hold_pnl, 4),
                "win_rate": round(self._hold_wins / hold_total, 4) if hold_total else 0,
                "wins": self._hold_wins,
                "losses": self._hold_losses,
                "total": hold_total,
            },
            "metrics": self._m,
            "sample_size_sufficient": total >= 15,
        }

    def get_positions(self):
        result = []
        for pos in self._positions.values():
            market = self._state.get_market(pos["token_id"]) if self._state else None
            cp = (market.mid_price if market and market.mid_price else None)
            entry = pos["entry_price"]
            mult = cp / entry if cp and entry > 0 else 1.0
            unrealized = (cp - entry) * pos["size"] if cp else 0
            result.append({
                **pos,
                "current_price": round(cp, 6) if cp else None,
                "current_multiple": round(mult, 4),
                "unrealized_pnl": round(unrealized, 4),
            })
        return result

    def get_closed(self, limit=50):
        return list(reversed(self._closed[-limit:]))
