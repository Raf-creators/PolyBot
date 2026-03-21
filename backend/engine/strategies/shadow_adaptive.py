"""Shadow Adaptive Edge — vol-adjusted min_edge_bps for crypto sniper.

Tracks what would happen if min_edge_bps scaled with realized volatility:
  High vol (>0.15):  350 bps — more opportunities during best conditions
  Medium (0.08-0.15): 400 bps — current baseline
  Low (<0.08):        500 bps — fewer but higher-quality during quiet markets

Also tracks Gabagool dynamic threshold based on time-to-resolution:
  5m markets:  0.975 (fast turnover compensates thinner edge)
  15m markets: 0.970
  1h+ markets: 0.960

100% shadow — no live orders. Compares adaptive vs fixed performance.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List

from models import utc_now

logger = logging.getLogger(__name__)

# Adaptive edge tiers
VOL_HIGH = 0.15
VOL_LOW = 0.08
EDGE_HIGH_VOL = 350.0    # bps
EDGE_MEDIUM_VOL = 400.0  # bps (current live)
EDGE_LOW_VOL = 500.0     # bps

# Gabagool dynamic thresholds by window
GABA_THRESHOLDS = {
    "5m": 0.975,
    "15m": 0.970,
    "1h": 0.965,
    "4h": 0.960,
    "default": 0.960,
}


def adaptive_min_edge(vol):
    """Return min_edge_bps based on current volatility."""
    if vol is None or vol <= 0:
        return EDGE_MEDIUM_VOL
    if vol >= VOL_HIGH:
        return EDGE_HIGH_VOL
    if vol <= VOL_LOW:
        return EDGE_LOW_VOL
    return EDGE_MEDIUM_VOL


class AdaptiveEdgeShadow:

    def __init__(self):
        self._m = {
            "signals_received": 0,
            "adaptive_would_trade": 0,
            "adaptive_would_skip": 0,
            "live_traded_adaptive_skip": 0,
            "live_skipped_adaptive_trade": 0,
            "last_vol": None,
            "last_adaptive_edge": None,
            "last_eval_time": None,
        }

        # Track hypothetical PnL for "adaptive only" signals
        self._positions: Dict[str, dict] = {}
        self._closed: List[dict] = []
        self._pnl = 0.0
        self._wins = 0
        self._losses = 0

        # Gabagool dynamic shadow
        self._gaba_pairs: Dict[str, dict] = {}
        self._gaba_closed: List[dict] = []
        self._gaba_pnl = 0.0
        self._gaba_wins = 0
        self._gaba_total = 0
        self._gaba_scanned = 0
        self._gaba_m = {"by_window": {}}

        self._state = None

    async def start(self, state):
        self._state = state
        logger.info("[ADAPTIVE-EDGE] Shadow engine started — vol-scaled edge + dynamic Gabagool")

    async def stop(self):
        pass

    def evaluate_signal(self, condition_id, asset, edge_bps, vol,
                        is_live_tradable, side, token_id, size,
                        entry_price, question, window=None, **kwargs):
        """Evaluate if adaptive edge would trade differently than live."""
        self._m["signals_received"] += 1
        self._m["last_eval_time"] = utc_now()
        self._m["last_vol"] = round(vol, 4) if vol else None

        adaptive_edge = adaptive_min_edge(vol)
        self._m["last_adaptive_edge"] = adaptive_edge

        would_trade = edge_bps >= adaptive_edge and entry_price > 0
        if would_trade:
            self._m["adaptive_would_trade"] += 1
        else:
            self._m["adaptive_would_skip"] += 1

        # Disagreement tracking
        if is_live_tradable and not would_trade:
            self._m["live_traded_adaptive_skip"] += 1
        if not is_live_tradable and would_trade:
            self._m["live_skipped_adaptive_trade"] += 1

        # Track positions for "adaptive unique" signals (ones live skipped)
        if would_trade and not is_live_tradable and token_id not in self._positions:
            self._positions[token_id] = {
                "token_id": token_id,
                "condition_id": condition_id,
                "question": (question or "")[:80],
                "asset": asset,
                "side": side,
                "window": window,
                "entry_price": round(entry_price, 6),
                "size": size,
                "edge_bps": round(edge_bps, 1),
                "vol_at_entry": round(vol, 4) if vol else 0,
                "adaptive_edge_at_entry": adaptive_edge,
                "opened_at": utc_now(),
            }

    def evaluate_gabagool_pair(self, yes_price, no_price, condition_id,
                                question, window=None, **kwargs):
        """Evaluate with dynamic threshold based on window."""
        self._gaba_scanned += 1
        if not yes_price or not no_price:
            return

        pair_sum = yes_price + no_price
        threshold = GABA_THRESHOLDS.get(window, GABA_THRESHOLDS["default"])

        window_key = window or "unknown"
        stats = self._gaba_m["by_window"].setdefault(window_key, {
            "scanned": 0, "triggered": 0, "threshold": threshold
        })
        stats["scanned"] += 1

        if pair_sum < threshold and condition_id not in self._gaba_pairs:
            stats["triggered"] += 1
            self._gaba_pairs[condition_id] = {
                "condition_id": condition_id,
                "question": (question or "")[:80],
                "window": window_key,
                "pair_sum": round(pair_sum, 6),
                "threshold_used": threshold,
                "edge_pct": round((1.0 - pair_sum) * 100, 2),
                "opened_at": utc_now(),
            }

    def check_resolutions(self):
        """Check if tracked positions resolved (call periodically from server)."""
        if not self._state:
            return

        # Adaptive edge positions
        to_close = []
        for token_id, pos in self._positions.items():
            market = self._state.get_market(token_id)
            if not market:
                continue
            cp = market.mid_price or market.last_price
            if cp is None:
                continue
            if cp >= 0.95 or cp <= 0.05:
                won = cp >= 0.95
                entry = pos["entry_price"]
                pnl = (1.0 - entry) * pos["size"] if won else -entry * pos["size"]
                to_close.append((token_id, won, pnl, cp))

            # Timeout
            try:
                opened = datetime.fromisoformat(pos["opened_at"].replace("Z", "+00:00"))
                age_h = (datetime.now(timezone.utc) - opened).total_seconds() / 3600
            except (ValueError, TypeError):
                age_h = 0
            if age_h > 8:
                entry = pos["entry_price"]
                pnl = (cp - entry) * pos["size"]
                won = pnl > 0
                to_close.append((token_id, won, pnl, cp))

        for token_id, won, pnl, exit_price in to_close:
            pos = self._positions.pop(token_id, None)
            if not pos:
                continue
            closed = {
                **pos,
                "exit_price": round(exit_price, 6),
                "pnl": round(pnl, 4),
                "won": won,
                "closed_at": utc_now(),
            }
            self._closed.append(closed)
            self._pnl += pnl
            if won:
                self._wins += 1
            else:
                self._losses += 1

    # ---- Reporting ----

    def get_report(self):
        total = self._wins + self._losses
        return {
            "status": "active" if self._m["signals_received"] > 0 else "collecting",
            "experiment": "adaptive_edge",
            "description": "Vol-scaled min_edge + Gabagool dynamic thresholds",
            "adaptive_edge": {
                "pnl_unique_signals": round(self._pnl, 4),
                "wins": self._wins,
                "losses": self._losses,
                "total": total,
                "win_rate": round(self._wins / total, 4) if total else 0,
                "open_positions": len(self._positions),
                "signals_received": self._m["signals_received"],
                "would_trade": self._m["adaptive_would_trade"],
                "would_skip": self._m["adaptive_would_skip"],
                "disagreements": {
                    "live_traded_adaptive_skip": self._m["live_traded_adaptive_skip"],
                    "live_skipped_adaptive_trade": self._m["live_skipped_adaptive_trade"],
                },
                "current_vol": self._m["last_vol"],
                "current_adaptive_edge": self._m["last_adaptive_edge"],
            },
            "gabagool_dynamic": {
                "pnl": round(self._gaba_pnl, 4),
                "wins": self._gaba_wins,
                "total_pairs": self._gaba_total,
                "open_pairs": len(self._gaba_pairs),
                "scanned": self._gaba_scanned,
                "by_window": self._gaba_m["by_window"],
            },
            "config": {
                "vol_high": VOL_HIGH,
                "vol_low": VOL_LOW,
                "edge_high_vol": EDGE_HIGH_VOL,
                "edge_medium_vol": EDGE_MEDIUM_VOL,
                "edge_low_vol": EDGE_LOW_VOL,
                "gaba_thresholds": GABA_THRESHOLDS,
            },
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

    def get_gaba_pairs(self):
        return list(self._gaba_pairs.values())

    def get_gaba_closed(self, limit=50):
        return list(reversed(self._gaba_closed[-limit:]))
