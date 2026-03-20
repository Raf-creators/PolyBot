"""Shadow Crypto Sniper — EV-gap + pseudo-Stoikov evaluation layer.

Evaluates the SAME BTC/ETH opportunities as the live CryptoSniper, but:
  - No live fills, no live promotion, no auto-enable
  - Adds EV-gap filter and Stoikov reservation price adjustment
  - Logs side-by-side comparison vs live sniper decisions
  - Tracks hypothetical PnL for shadow trades

Fully isolated from live production.
"""

import asyncio
import logging
import math
import time
from collections import deque, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models import utc_now

logger = logging.getLogger(__name__)


class ShadowSniperConfig:
    """Shadow-layer tuning parameters."""
    # EV-gap filter: minimum expected-value ratio (EV / capital_at_risk)
    min_ev_ratio: float = 0.04          # 4% minimum EV/risk ratio
    # Stoikov reservation price parameters
    gamma: float = 0.1                   # risk aversion (higher = more conservative)
    inventory_decay: float = 0.8         # how fast inventory pressure decays with time


class ShadowSniperEngine:
    """Shadow evaluation engine that mirrors live sniper decisions."""

    def __init__(self):
        self._config = ShadowSniperConfig()
        self._live_sniper = None          # reference to live CryptoSniper
        self._state = None                # reference to live StateManager
        self._running = False

        # Shadow trade log: list of evaluation records
        self._evaluations: List[dict] = []
        self._max_evaluations = 2000

        # Shadow hypothetical positions: token_id -> entry record
        self._shadow_positions: Dict[str, dict] = {}
        # Shadow closed trades
        self._shadow_closed: List[dict] = []
        self._max_closed = 500

        # Rolling PnL tracking
        self._shadow_pnl_total = 0.0
        self._shadow_trades_won = 0
        self._shadow_trades_lost = 0

        # Metrics
        self._m = {
            "total_evaluations": 0,
            "shadow_would_trade": 0,
            "shadow_would_skip": 0,
            "live_traded": 0,
            "live_skipped": 0,
            "agreements": 0,       # both agree
            "false_positives": 0,  # shadow says yes, outcome was loss
            "false_negatives": 0,  # shadow says no, live traded and won
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

    # ---- Core evaluation (called after live sniper evaluates a market) ----

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
        live_decision: str,      # "trade_yes", "trade_no", "skip"
        live_rejection: str,     # reason if skipped
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

        # Shadow decision: would trade if BOTH filters pass AND basic edge > 0
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

        # Track agreements/disagreements
        if shadow_would_trade and live_traded:
            self._m["agreements"] += 1
        elif not shadow_would_trade and not live_traded:
            self._m["agreements"] += 1

        if shadow_would_trade:
            self._m["shadow_would_trade"] += 1
        else:
            self._m["shadow_would_skip"] += 1

        if live_traded:
            self._m["live_traded"] += 1
        else:
            self._m["live_skipped"] += 1

        # Open shadow position if shadow would trade
        if shadow_would_trade and token_id and token_id not in self._shadow_positions:
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
                "size": 3.0,  # hypothetical standard size
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
            # Live decision
            "live_decision": live_decision,
            "live_rejection": live_rejection,
            "live_traded": live_traded,
            # Shadow EV-gap
            "ev_ratio": round(ev_ratio, 6),
            "ev_pass": ev_pass,
            # Shadow Stoikov
            "inventory": round(inventory, 2),
            "reservation_price": round(reservation_price, 6),
            "stoikov_edge_bps": round(stoikov_adjusted_edge, 1),
            "stoikov_pass": stoikov_pass,
            # Shadow decision
            "shadow_would_trade": shadow_would_trade,
            "shadow_rejection": shadow_rejection,
            "shadow_side": side if shadow_would_trade else "none",
            "question": question[:80],
        }

        self._evaluations.append(record)
        if len(self._evaluations) > self._max_evaluations:
            self._evaluations = self._evaluations[-self._max_evaluations:]

        self._m["last_eval_time"] = now

        return record

    # ---- EV-gap computation ----

    def _compute_ev_ratio(self, fair_prob: float, market_price: float) -> float:
        """Expected value per unit of capital at risk.

        EV = fair_prob * payout - (1 - fair_prob) * cost
           = fair_prob * (1 - market_price) - (1 - fair_prob) * market_price
           = fair_prob - market_price

        EV ratio = EV / capital_at_risk = (fair - market) / market
        """
        if market_price <= 0.001:
            return 0.0
        ev = fair_prob - market_price
        return ev / market_price

    # ---- Pseudo-Stoikov reservation price ----

    def _compute_inventory(self, asset: str) -> float:
        """Net shadow inventory for this asset (positive = long exposure)."""
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
        """Avellaneda-Stoikov reservation price adjustment.

        r = s - q * gamma * sigma^2 * tau
        where:
          s = fair probability (our model output)
          q = net inventory in this asset
          gamma = risk aversion parameter
          sigma = annualized volatility
          tau = time to expiry in years
        """
        tau = max(tte_seconds / 31_536_000.0, 1e-8)
        sigma = max(volatility, 0.10)
        adjustment = inventory * self._config.gamma * (sigma ** 2) * tau
        # Decay the adjustment for longer TTEs (position pressure matters less far out)
        decay = math.exp(-self._config.inventory_decay * tau * 365)
        return fair - adjustment * decay

    # ---- Resolution loop: close shadow positions when markets resolve ----

    async def _resolution_loop(self):
        """Periodically check if shadow positions have resolved."""
        await asyncio.sleep(60)
        while self._running:
            try:
                self._resolve_expired_positions()
            except Exception as e:
                logger.error(f"[SHADOW-SNIPER] Resolution error: {e}")
            await asyncio.sleep(120)  # check every 2 minutes

    def _resolve_expired_positions(self):
        """Check shadow positions against current market prices for resolution."""
        if not self._state:
            return

        to_close = []
        now = datetime.now(timezone.utc)

        for token_id, pos in self._shadow_positions.items():
            # Check if market still exists and has resolved
            market = self._state.get_market(token_id)
            current_price = None
            if market:
                current_price = market.mid_price or market.last_price

            # Check if position is expired (past TTE)
            try:
                opened = datetime.fromisoformat(pos["opened_at"].replace("Z", "+00:00"))
                elapsed = (now - opened).total_seconds()
            except (ValueError, TypeError):
                elapsed = 0

            if elapsed > pos["tte_seconds"] + 300:  # 5 min buffer past expiry
                # Position expired — resolve at current price or 0/1
                exit_price = current_price if current_price is not None else 0.5
                # If price is very close to 0 or 1, it's resolved
                if exit_price > 0.95:
                    exit_price = 1.0
                elif exit_price < 0.05:
                    exit_price = 0.0

                pnl = (exit_price - pos["entry_price"]) * pos["size"]
                to_close.append((token_id, exit_price, pnl))

        for token_id, exit_price, pnl in to_close:
            pos = self._shadow_positions.pop(token_id)
            closed = {
                **pos,
                "exit_price": round(exit_price, 6),
                "pnl": round(pnl, 4),
                "closed_at": utc_now(),
                "won": pnl > 0,
            }
            self._shadow_closed.append(closed)
            if len(self._shadow_closed) > self._max_closed:
                self._shadow_closed = self._shadow_closed[-self._max_closed:]

            self._shadow_pnl_total += pnl
            if pnl > 0:
                self._shadow_trades_won += 1
            else:
                self._shadow_trades_lost += 1

            total_trades = self._shadow_trades_won + self._shadow_trades_lost
            self._m["shadow_pnl"] = round(self._shadow_pnl_total, 4)
            self._m["shadow_trade_count"] = total_trades
            self._m["shadow_win_rate"] = round(
                self._shadow_trades_won / total_trades if total_trades > 0 else 0, 4
            )

            logger.info(
                f"[SHADOW-SNIPER] Resolved: {pos['asset']} {pos['side']} "
                f"entry={pos['entry_price']:.4f} exit={exit_price:.4f} "
                f"pnl=${pnl:.4f} (total=${self._shadow_pnl_total:.2f})"
            )

    # ---- Comparison metrics ----

    def get_comparison_report(self) -> dict:
        """Build side-by-side comparison of live vs shadow performance."""
        total_evals = self._m["total_evaluations"]
        if total_evals == 0:
            return {"status": "no_data", "message": "No evaluations yet"}

        # Compute rolling PnL windows from closed trades
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

        # Average edge for shadow-would-trade signals
        shadow_edges = [
            e["edge_bps"] for e in self._evaluations if e["shadow_would_trade"]
        ]
        avg_shadow_edge = sum(shadow_edges) / len(shadow_edges) if shadow_edges else 0

        # Average edge for live trades
        live_edges = [e["edge_bps"] for e in self._evaluations if e["live_traded"]]
        avg_live_edge = sum(live_edges) / len(live_edges) if live_edges else 0

        agreement_rate = self._m["agreements"] / total_evals if total_evals > 0 else 0

        return {
            "status": "active",
            "total_evaluations": total_evals,
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
                    "closed_trades": self._m["shadow_trade_count"],
                    "open_positions": len(self._shadow_positions),
                },
                "agreement_rate": round(agreement_rate, 4),
                "false_positives": self._m["false_positives"],
                "false_negatives": self._m["false_negatives"],
            },
            "rolling_pnl": {k: round(v, 4) for k, v in rolling.items()},
            "config": {
                "min_ev_ratio": self._config.min_ev_ratio,
                "gamma": self._config.gamma,
                "inventory_decay": self._config.inventory_decay,
            },
            "last_eval_time": self._m["last_eval_time"],
        }

    def get_recent_evaluations(self, limit: int = 50) -> List[dict]:
        """Return recent shadow evaluations for monitoring."""
        return list(reversed(self._evaluations[-limit:]))

    def get_shadow_positions(self) -> List[dict]:
        """Return current shadow open positions."""
        result = []
        for pos in self._shadow_positions.values():
            market = self._state.get_market(pos["token_id"]) if self._state else None
            current_price = (market.mid_price if market and market.mid_price else None)
            unrealized = (
                (current_price - pos["entry_price"]) * pos["size"]
                if current_price is not None else 0.0
            )
            result.append({
                **pos,
                "current_price": round(current_price, 6) if current_price else None,
                "unrealized_pnl": round(unrealized, 4),
            })
        return result

    def get_shadow_closed(self, limit: int = 50) -> List[dict]:
        """Return recently closed shadow trades."""
        return list(reversed(self._shadow_closed[-limit:]))
