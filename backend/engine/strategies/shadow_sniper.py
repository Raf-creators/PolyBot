"""Shadow Crypto Sniper — EV-gap + pseudo-Stoikov evaluation layer.

Evaluates the SAME BTC/ETH opportunities as the live CryptoSniper, but:
  - No live fills, no live promotion, no auto-enable
  - Adds EV-gap filter and Stoikov reservation price adjustment
  - Logs side-by-side comparison vs live sniper decisions
  - Tracks hypothetical PnL for shadow trades

Fully isolated from live production.

SIZING: Uses live sniper's default_size per signal. Does NOT accumulate
multiple fills on the same token. All PnL is unit-size ($3/signal) research PnL.
"""

import asyncio
import logging
import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models import utc_now

logger = logging.getLogger(__name__)


class ShadowSniperConfig:
    """Shadow-layer tuning parameters."""
    min_ev_ratio: float = 0.04          # 4% minimum EV/risk ratio
    gamma: float = 0.1                   # risk aversion (higher = more conservative)
    inventory_decay: float = 0.8         # how fast inventory pressure decays with time


class ShadowSniperEngine:
    """Shadow evaluation engine that mirrors live sniper decisions."""

    def __init__(self):
        self._config = ShadowSniperConfig()
        self._live_sniper = None
        self._state = None
        self._running = False

        # Shadow trade log
        self._evaluations: List[dict] = []
        self._max_evaluations = 2000

        # Shadow hypothetical positions: token_id -> entry record
        self._shadow_positions: Dict[str, dict] = {}
        # Shadow closed trades
        self._shadow_closed: List[dict] = []
        self._max_closed = 500

        # PnL tracking
        self._shadow_pnl_total = 0.0
        self._shadow_trades_won = 0
        self._shadow_trades_lost = 0

        # Disagreement tracking for FP/FN (token_id -> info)
        self._disagreements: Dict[str, dict] = {}

        # Metrics
        self._m = {
            "total_evaluations": 0,
            "meaningful_evaluations": 0,
            "shadow_would_trade": 0,
            "shadow_would_skip": 0,
            "live_traded": 0,
            "live_skipped": 0,
            "agreements": 0,
            "meaningful_agreements": 0,
            "false_positives": 0,  # shadow traded, outcome was loss
            "false_negatives": 0,  # shadow skipped, live traded and won
            "shadow_pnl": 0.0,
            "shadow_win_rate": 0.0,
            "shadow_avg_edge": 0.0,
            "shadow_trade_count": 0,
            "last_eval_time": None,
        }

    async def start(self, state, live_sniper):
        """Start shadow engine with references to live components."""
        self._state = state
        self._live_sniper = live_sniper
        self._running = True
        asyncio.create_task(self._resolution_loop())
        logger.info("[SHADOW-SNIPER] Started — EV-gap + pseudo-Stoikov shadow layer active")

    async def stop(self):
        self._running = False
        logger.info("[SHADOW-SNIPER] Stopped")

    def _get_live_size(self) -> float:
        """Read default_size from live sniper config (not hardcoded)."""
        try:
            return self._live_sniper.config.default_size
        except Exception:
            return 3.0

    # ---- Core evaluation ----

    def evaluate_signal(
        self,
        condition_id: str,
        asset: str,
        direction: str,
        spot: float,
        fair_prob: float,
        yes_price: float,
        no_price: float,
        edge_bps_yes: float,
        edge_bps_no: float,
        tte_seconds: float,
        volatility: float,
        live_decision: str,
        live_rejection: str,
        token_id_yes: str,
        token_id_no: str,
        question: str,
    ):
        """Evaluate one market opportunity through the shadow lens."""
        self._m["total_evaluations"] += 1
        now = utc_now()

        # Pick the better side (same logic as live)
        if edge_bps_yes >= edge_bps_no and edge_bps_yes > 0:
            side = "buy_yes"
            edge_bps = edge_bps_yes
            market_price = yes_price
            token_id = token_id_yes
            fair = fair_prob
        elif edge_bps_no > 0:
            side = "buy_no"
            edge_bps = edge_bps_no
            market_price = no_price
            token_id = token_id_no
            fair = 1.0 - fair_prob
        else:
            side = "none"
            edge_bps = max(edge_bps_yes, edge_bps_no)
            market_price = yes_price
            token_id = ""
            fair = fair_prob

        # ---- EV-gap filter ----
        ev_ratio = self._compute_ev_ratio(fair, market_price)
        ev_pass = ev_ratio >= self._config.min_ev_ratio

        # ---- Pseudo-Stoikov reservation price ----
        inventory = self._compute_inventory(asset)
        reservation_price = self._compute_reservation_price(
            fair, inventory, volatility, tte_seconds
        )
        stoikov_adjusted_edge = (reservation_price - market_price) * 10_000
        stoikov_pass = stoikov_adjusted_edge > 0

        # Shadow decision
        shadow_would_trade = ev_pass and stoikov_pass and edge_bps > 0
        shadow_rejection = None
        if not shadow_would_trade:
            reasons = []
            if edge_bps <= 0:
                reasons.append("no_edge")
            if not ev_pass:
                reasons.append(f"ev_ratio={ev_ratio:.4f}<{self._config.min_ev_ratio}")
            if not stoikov_pass:
                reasons.append(f"stoikov_edge={stoikov_adjusted_edge:.0f}bps<0")
            shadow_rejection = "; ".join(reasons)

        live_traded = live_decision.startswith("trade")

        # Meaningful evaluation: at least one side had edge > 0
        is_meaningful = (edge_bps > 0) or live_traded
        if is_meaningful:
            self._m["meaningful_evaluations"] += 1

        # Track agreements
        both_agree = (shadow_would_trade == live_traded)
        self._m["agreements"] += 1 if both_agree else 0
        if is_meaningful:
            self._m["meaningful_agreements"] += 1 if both_agree else 0

        if shadow_would_trade:
            self._m["shadow_would_trade"] += 1
        else:
            self._m["shadow_would_skip"] += 1

        if live_traded:
            self._m["live_traded"] += 1
        else:
            self._m["live_skipped"] += 1

        # Track disagreements for later FP/FN calculation at resolution
        if not both_agree and token_id:
            self._disagreements[token_id] = {
                "shadow_would_trade": shadow_would_trade,
                "live_traded": live_traded,
            }

        # Open shadow position
        size = self._get_live_size()
        if shadow_would_trade and token_id and token_id not in self._shadow_positions:
            notional = size * market_price
            self._shadow_positions[token_id] = {
                "token_id": token_id,
                "condition_id": condition_id,
                "asset": asset,
                "side": side,
                "entry_price": market_price,
                "fair_at_entry": fair,
                "ev_ratio": ev_ratio,
                "reservation_price": reservation_price,
                "stoikov_edge_bps": stoikov_adjusted_edge,
                "edge_bps": edge_bps,
                "tte_seconds": tte_seconds,
                "opened_at": now,
                "question": question,
                "size": size,
                "notional": round(notional, 4),
            }

        # Build evaluation record
        record = {
            "timestamp": now,
            "condition_id": condition_id,
            "asset": asset,
            "direction": direction,
            "spot": round(spot, 2),
            "fair_prob": round(fair, 6),
            "market_price": round(market_price, 6),
            "edge_bps": round(edge_bps, 1),
            "tte_seconds": round(tte_seconds, 1),
            "volatility": round(volatility, 6),
            "live_decision": live_decision,
            "live_rejection": live_rejection,
            "live_traded": live_traded,
            "ev_ratio": round(ev_ratio, 6),
            "ev_pass": ev_pass,
            "inventory": round(inventory, 2),
            "reservation_price": round(reservation_price, 6),
            "stoikov_edge_bps": round(stoikov_adjusted_edge, 1),
            "stoikov_pass": stoikov_pass,
            "shadow_would_trade": shadow_would_trade,
            "shadow_rejection": shadow_rejection,
            "shadow_side": side if shadow_would_trade else "none",
            "question": question[:80],
            "is_meaningful": is_meaningful,
        }

        self._evaluations.append(record)
        if len(self._evaluations) > self._max_evaluations:
            self._evaluations = self._evaluations[-self._max_evaluations:]

        self._m["last_eval_time"] = now
        return record

    # ---- EV-gap computation ----

    def _compute_ev_ratio(self, fair_prob: float, market_price: float) -> float:
        """EV ratio = (fair - market) / market"""
        if market_price <= 0.001:
            return 0.0
        return (fair_prob - market_price) / market_price

    # ---- Pseudo-Stoikov reservation price ----

    def _compute_inventory(self, asset: str) -> float:
        """Net shadow inventory for this asset."""
        inv = 0.0
        for pos in self._shadow_positions.values():
            if pos["asset"] == asset:
                inv += pos["size"]
        return inv

    def _compute_reservation_price(
        self,
        fair: float,
        inventory: float,
        volatility: float,
        tte_seconds: float,
    ) -> float:
        """Avellaneda-Stoikov reservation price: r = s - q * gamma * sigma^2 * tau"""
        tau = max(tte_seconds / 31_536_000.0, 1e-8)
        sigma = max(volatility, 0.10)
        adjustment = inventory * self._config.gamma * (sigma ** 2) * tau
        decay = math.exp(-self._config.inventory_decay * tau * 365)
        return fair - adjustment * decay

    # ---- Resolution loop ----

    async def _resolution_loop(self):
        """Periodically check if shadow positions have resolved to binary outcomes."""
        await asyncio.sleep(60)
        while self._running:
            try:
                self._resolve_positions()
            except Exception as e:
                logger.error(f"[SHADOW-SNIPER] Resolution error: {e}")
            await asyncio.sleep(120)

    def _resolve_positions(self):
        """Resolve shadow positions ONLY when binary outcome is clear (price near 0 or 1)."""
        if not self._state:
            return

        to_close = []
        now = datetime.now(timezone.utc)

        for token_id, pos in self._shadow_positions.items():
            market = self._state.get_market(token_id)
            current_price = None
            if market:
                current_price = market.mid_price or market.last_price

            # Check elapsed time
            try:
                opened = datetime.fromisoformat(pos["opened_at"].replace("Z", "+00:00"))
                elapsed = (now - opened).total_seconds()
            except (ValueError, TypeError):
                elapsed = 0

            if current_price is not None:
                # Resolution criteria: price has reached binary outcome (near 0 or 1)
                if current_price >= 0.92:
                    to_close.append((token_id, 1.0, "resolved_yes"))
                elif current_price <= 0.08:
                    to_close.append((token_id, 0.0, "resolved_no"))
                elif elapsed > pos["tte_seconds"] + 7200:
                    # Fallback: if 2+ hours past TTE and still no binary resolution,
                    # mark-to-market but flag as "unresolved"
                    to_close.append((token_id, current_price, "expired_mtm"))
            elif elapsed > pos["tte_seconds"] + 14400:
                # No market data AND 4+ hours past TTE — assume lost
                to_close.append((token_id, 0.5, "no_data"))

        for token_id, exit_price, resolution_type in to_close:
            pos = self._shadow_positions.pop(token_id)
            pnl = (exit_price - pos["entry_price"]) * pos["size"]

            is_binary = resolution_type.startswith("resolved")
            won = pnl > 0

            closed = {
                "token_id": pos["token_id"],
                "condition_id": pos["condition_id"],
                "asset": pos["asset"],
                "side": pos["side"],
                "entry_price": pos["entry_price"],
                "fair_at_entry": pos["fair_at_entry"],
                "ev_ratio": pos["ev_ratio"],
                "stoikov_edge_bps": pos["stoikov_edge_bps"],
                "edge_bps": pos["edge_bps"],
                "question": pos["question"],
                "size": pos["size"],
                "notional": pos.get("notional", 0),
                "opened_at": pos["opened_at"],
                "exit_price": round(exit_price, 6),
                "pnl": round(pnl, 4),
                "closed_at": utc_now(),
                "won": won,
                "resolution_type": resolution_type,
                "is_binary_resolved": is_binary,
            }
            self._shadow_closed.append(closed)
            if len(self._shadow_closed) > self._max_closed:
                self._shadow_closed = self._shadow_closed[-self._max_closed:]

            self._shadow_pnl_total += pnl
            if won:
                self._shadow_trades_won += 1
            else:
                self._shadow_trades_lost += 1

            # False positive / false negative tracking
            disagree = self._disagreements.pop(token_id, None)
            if disagree and is_binary:
                if disagree["shadow_would_trade"] and not won:
                    self._m["false_positives"] += 1
                elif not disagree["shadow_would_trade"] and disagree["live_traded"] and won:
                    self._m["false_negatives"] += 1

            total_trades = self._shadow_trades_won + self._shadow_trades_lost
            self._m["shadow_pnl"] = round(self._shadow_pnl_total, 4)
            self._m["shadow_trade_count"] = total_trades
            self._m["shadow_win_rate"] = round(
                self._shadow_trades_won / total_trades if total_trades > 0 else 0, 4
            )

            logger.info(
                f"[SHADOW-SNIPER] Resolved ({resolution_type}): {pos['asset']} {pos['side']} "
                f"entry={pos['entry_price']:.4f} exit={exit_price:.4f} "
                f"pnl=${pnl:.4f} (total=${self._shadow_pnl_total:.2f})"
            )

    # ---- Comparison metrics ----

    def get_comparison_report(self) -> dict:
        """Build side-by-side comparison of live vs shadow performance."""
        total_evals = self._m["total_evaluations"]
        meaningful = self._m["meaningful_evaluations"]
        if total_evals == 0:
            return {"status": "no_data", "message": "No evaluations yet"}

        now = datetime.now(timezone.utc)
        rolling = {"1h": 0.0, "3h": 0.0, "6h": 0.0}
        for trade in self._shadow_closed:
            try:
                closed_at = datetime.fromisoformat(
                    trade["closed_at"].replace("Z", "+00:00")
                )
                age_hours = (now - closed_at).total_seconds() / 3600
                if age_hours <= 1:
                    rolling["1h"] += trade["pnl"]
                if age_hours <= 3:
                    rolling["3h"] += trade["pnl"]
                if age_hours <= 6:
                    rolling["6h"] += trade["pnl"]
            except (ValueError, TypeError):
                pass

        shadow_edges = [
            e["edge_bps"] for e in self._evaluations if e["shadow_would_trade"]
        ]
        avg_shadow_edge = sum(shadow_edges) / len(shadow_edges) if shadow_edges else 0

        live_edges = [e["edge_bps"] for e in self._evaluations if e["live_traded"]]
        avg_live_edge = sum(live_edges) / len(live_edges) if live_edges else 0

        # Agreement rate on MEANINGFUL evaluations only
        meaningful_agreement_rate = (
            self._m["meaningful_agreements"] / meaningful if meaningful > 0 else 0
        )
        overall_agreement_rate = (
            self._m["agreements"] / total_evals if total_evals > 0 else 0
        )

        # Binary-resolved stats
        binary_closed = [t for t in self._shadow_closed if t.get("is_binary_resolved")]
        binary_wins = sum(1 for t in binary_closed if t["won"])
        binary_win_rate = binary_wins / len(binary_closed) if binary_closed else 0

        unit_size = self._get_live_size()

        return {
            "status": "active",
            "total_evaluations": total_evals,
            "meaningful_evaluations": meaningful,
            "comparison": {
                "live": {
                    "trade_count": self._m["live_traded"],
                    "skip_count": self._m["live_skipped"],
                    "avg_edge_bps": round(avg_live_edge, 1),
                },
                "shadow": {
                    "trade_count": self._m["shadow_would_trade"],
                    "skip_count": self._m["shadow_would_skip"],
                    "avg_edge_bps": round(avg_shadow_edge, 1),
                    "pnl_total": self._m["shadow_pnl"],
                    "win_rate": self._m["shadow_win_rate"],
                    "binary_win_rate": round(binary_win_rate, 4),
                    "binary_resolved_count": len(binary_closed),
                    "closed_trades": self._m["shadow_trade_count"],
                    "open_positions": len(self._shadow_positions),
                },
                "agreement_rate": round(overall_agreement_rate, 4),
                "meaningful_agreement_rate": round(meaningful_agreement_rate, 4),
                "false_positives": self._m["false_positives"],
                "false_negatives": self._m["false_negatives"],
            },
            "rolling_pnl": {k: round(v, 4) for k, v in rolling.items()},
            "sizing": {
                "type": "unit_size",
                "per_signal_size": unit_size,
                "note": f"All PnL is unit-size (${unit_size}/signal). Does not accumulate. Not live-equivalent.",
            },
            "config": {
                "min_ev_ratio": self._config.min_ev_ratio,
                "gamma": self._config.gamma,
                "inventory_decay": self._config.inventory_decay,
            },
            "last_eval_time": self._m["last_eval_time"],
        }

    def get_recent_evaluations(self, limit: int = 50) -> List[dict]:
        return list(reversed(self._evaluations[-limit:]))

    def get_shadow_positions(self) -> List[dict]:
        result = []
        for pos in self._shadow_positions.values():
            market = self._state.get_market(pos["token_id"]) if self._state else None
            current_price = (market.mid_price if market and market.mid_price else None)
            unrealized = (
                (current_price - pos["entry_price"]) * pos["size"]
                if current_price is not None else 0.0
            )
            result.append({
                "token_id": pos["token_id"],
                "condition_id": pos["condition_id"],
                "asset": pos["asset"],
                "side": pos["side"],
                "entry_price": pos["entry_price"],
                "fair_at_entry": pos["fair_at_entry"],
                "ev_ratio": pos["ev_ratio"],
                "reservation_price": pos.get("reservation_price", 0),
                "stoikov_edge_bps": pos["stoikov_edge_bps"],
                "edge_bps": pos["edge_bps"],
                "question": pos["question"],
                "size": pos["size"],
                "notional": pos.get("notional", 0),
                "opened_at": pos["opened_at"],
                "tte_seconds": pos["tte_seconds"],
                "current_price": round(current_price, 6) if current_price else None,
                "unrealized_pnl": round(unrealized, 4),
            })
        return result

    def get_shadow_closed(self, limit: int = 50) -> List[dict]:
        return list(reversed(self._shadow_closed[-limit:]))
