"""Shadow Crypto Sniper — EV-gap + pseudo-Stoikov evaluation layer.

TWO parallel shadow modes, both fully isolated from live production:

1. UNIT-SIZE: $default_size/signal, no accumulation. Clean research comparison.
2. LIVE-EQUIVALENT: Same sizing/accumulation/cap path as live sniper.
   Simulates position building across multiple scan cycles.
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models import utc_now

logger = logging.getLogger(__name__)


class ShadowSniperConfig:
    min_ev_ratio: float = 0.04
    gamma: float = 0.1
    inventory_decay: float = 0.8


class ShadowSniperEngine:

    def __init__(self):
        self._config = ShadowSniperConfig()
        self._live_sniper = None
        self._state = None
        self._running = False

        self._evaluations: List[dict] = []
        self._max_evaluations = 2000

        # ---- Unit-Size mode ----
        self._unit_positions: Dict[str, dict] = {}
        self._unit_closed: List[dict] = []
        self._unit_pnl = 0.0
        self._unit_wins = 0
        self._unit_losses = 0

        # ---- Live-Equivalent mode ----
        self._le_positions: Dict[str, dict] = {}
        self._le_closed: List[dict] = []
        self._le_pnl = 0.0
        self._le_wins = 0
        self._le_losses = 0

        # Disagreement tracking for FP/FN
        self._disagreements: Dict[str, dict] = {}

        self._m = {
            "total_evaluations": 0,
            "meaningful_evaluations": 0,
            "shadow_would_trade": 0,
            "shadow_would_skip": 0,
            "live_traded": 0,
            "live_skipped": 0,
            "agreements": 0,
            "meaningful_agreements": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "last_eval_time": None,
        }

    async def start(self, state, live_sniper):
        self._state = state
        self._live_sniper = live_sniper
        self._running = True
        asyncio.create_task(self._resolution_loop())
        logger.info("[SHADOW-SNIPER] Started — dual mode (unit-size + live-equivalent)")

    async def stop(self):
        self._running = False

    def _get_live_size(self) -> float:
        try:
            return self._live_sniper.config.default_size
        except Exception:
            return 3.0

    def _get_max_position_size(self) -> float:
        try:
            return self._state.risk_config.max_position_size
        except Exception:
            return 25.0

    # ---- Core evaluation ----

    def evaluate_signal(
        self, condition_id, asset, direction, spot, fair_prob,
        yes_price, no_price, edge_bps_yes, edge_bps_no,
        tte_seconds, volatility, live_decision, live_rejection,
        token_id_yes, token_id_no, question,
    ):
        self._m["total_evaluations"] += 1
        now = utc_now()

        # Pick better side
        if edge_bps_yes >= edge_bps_no and edge_bps_yes > 0:
            side, edge_bps, market_price = "buy_yes", edge_bps_yes, yes_price
            token_id, fair = token_id_yes, fair_prob
        elif edge_bps_no > 0:
            side, edge_bps, market_price = "buy_no", edge_bps_no, no_price
            token_id, fair = token_id_no, 1.0 - fair_prob
        else:
            side, edge_bps, market_price = "none", max(edge_bps_yes, edge_bps_no), yes_price
            token_id, fair = "", fair_prob

        # EV-gap
        ev_ratio = self._compute_ev_ratio(fair, market_price)
        ev_pass = ev_ratio >= self._config.min_ev_ratio

        # Stoikov
        inventory = self._compute_inventory(asset)
        res_price = self._compute_reservation_price(fair, inventory, volatility, tte_seconds)
        stoikov_edge = (res_price - market_price) * 10_000
        stoikov_pass = stoikov_edge > 0

        shadow_would_trade = ev_pass and stoikov_pass and edge_bps > 0
        shadow_rejection = None
        if not shadow_would_trade:
            reasons = []
            if edge_bps <= 0:
                reasons.append("no_edge")
            if not ev_pass:
                reasons.append(f"ev_ratio={ev_ratio:.4f}<{self._config.min_ev_ratio}")
            if not stoikov_pass:
                reasons.append(f"stoikov_edge={stoikov_edge:.0f}bps<0")
            shadow_rejection = "; ".join(reasons)

        live_traded = live_decision.startswith("trade")
        is_meaningful = (edge_bps > 0) or live_traded
        if is_meaningful:
            self._m["meaningful_evaluations"] += 1

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

        if not both_agree and token_id:
            self._disagreements[token_id] = {
                "shadow_would_trade": shadow_would_trade,
                "live_traded": live_traded,
            }

        # ---- Position management for both modes ----
        signal_size = self._get_live_size()
        max_pos = self._get_max_position_size()
        le_action = None

        if shadow_would_trade and token_id:
            # Unit-size: one entry per token, no accumulation
            if token_id not in self._unit_positions:
                self._unit_positions[token_id] = self._make_position(
                    token_id, condition_id, asset, side, market_price,
                    fair, ev_ratio, res_price, stoikov_edge, edge_bps,
                    tte_seconds, now, question, signal_size,
                )

            # Live-equivalent: accumulate up to max_position_size
            if token_id in self._le_positions:
                pos = self._le_positions[token_id]
                new_size = pos["size"] + signal_size
                if new_size <= max_pos:
                    old_cost = pos["size"] * pos["avg_entry"]
                    new_cost = signal_size * market_price
                    pos["avg_entry"] = round((old_cost + new_cost) / new_size, 6)
                    pos["size"] = round(new_size, 2)
                    pos["notional"] = round(new_size * pos["avg_entry"], 4)
                    pos["fills"] += 1
                    le_action = f"accum:{pos['fills']}fills,size={pos['size']}"
                else:
                    le_action = f"cap_blocked:projected={new_size:.0f}>max={max_pos:.0f}"
            else:
                self._le_positions[token_id] = self._make_position(
                    token_id, condition_id, asset, side, market_price,
                    fair, ev_ratio, res_price, stoikov_edge, edge_bps,
                    tte_seconds, now, question, signal_size,
                )
                self._le_positions[token_id]["avg_entry"] = market_price
                self._le_positions[token_id]["fills"] = 1
                le_action = "new_le_position"

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
            "reservation_price": round(res_price, 6),
            "stoikov_edge_bps": round(stoikov_edge, 1),
            "stoikov_pass": stoikov_pass,
            "shadow_would_trade": shadow_would_trade,
            "shadow_rejection": shadow_rejection,
            "shadow_side": side if shadow_would_trade else "none",
            "le_action": le_action,
            "question": question[:80],
            "is_meaningful": is_meaningful,
        }
        self._evaluations.append(record)
        if len(self._evaluations) > self._max_evaluations:
            self._evaluations = self._evaluations[-self._max_evaluations:]
        self._m["last_eval_time"] = now
        return record

    @staticmethod
    def _make_position(token_id, condition_id, asset, side, price, fair,
                       ev_ratio, res_price, stoikov_edge, edge_bps,
                       tte_seconds, now, question, size):
        return {
            "token_id": token_id, "condition_id": condition_id,
            "asset": asset, "side": side,
            "entry_price": price, "avg_entry": price,
            "fair_at_entry": fair, "ev_ratio": ev_ratio,
            "reservation_price": res_price,
            "stoikov_edge_bps": stoikov_edge, "edge_bps": edge_bps,
            "tte_seconds": tte_seconds, "opened_at": now,
            "question": question, "size": size, "fills": 1,
            "notional": round(size * price, 4),
        }

    # ---- Math ----

    def _compute_ev_ratio(self, fair, price):
        return (fair - price) / price if price > 0.001 else 0.0

    def _compute_inventory(self, asset):
        return sum(p["size"] for p in self._le_positions.values() if p["asset"] == asset)

    def _compute_reservation_price(self, fair, inventory, vol, tte):
        tau = max(tte / 31_536_000.0, 1e-8)
        sigma = max(vol, 0.10)
        adj = inventory * self._config.gamma * (sigma ** 2) * tau
        decay = math.exp(-self._config.inventory_decay * tau * 365)
        return fair - adj * decay

    # ---- Resolution ----

    async def _resolution_loop(self):
        await asyncio.sleep(60)
        while self._running:
            try:
                self._resolve_all()
            except Exception as e:
                logger.error(f"[SHADOW-SNIPER] Resolution error: {e}")
            await asyncio.sleep(120)

    def _resolve_all(self):
        if not self._state:
            return
        now = datetime.now(timezone.utc)
        self._resolve_mode(self._unit_positions, self._unit_closed, "unit", now)
        self._resolve_mode(self._le_positions, self._le_closed, "le", now)

    def _resolve_mode(self, positions, closed_list, mode, now):
        to_close = []
        for token_id, pos in positions.items():
            market = self._state.get_market(token_id)
            cp = (market.mid_price or market.last_price) if market else None

            try:
                opened = datetime.fromisoformat(pos["opened_at"].replace("Z", "+00:00"))
                elapsed = (now - opened).total_seconds()
            except (ValueError, TypeError):
                elapsed = 0

            if cp is not None:
                if cp >= 0.92:
                    to_close.append((token_id, 1.0, "resolved_yes"))
                elif cp <= 0.08:
                    to_close.append((token_id, 0.0, "resolved_no"))
                elif elapsed > pos["tte_seconds"] + 7200:
                    to_close.append((token_id, cp, "expired_mtm"))
            elif elapsed > pos["tte_seconds"] + 14400:
                to_close.append((token_id, 0.5, "no_data"))

        for token_id, exit_price, res_type in to_close:
            pos = positions.pop(token_id)
            entry = pos.get("avg_entry", pos["entry_price"])
            pnl = (exit_price - entry) * pos["size"]
            is_binary = res_type.startswith("resolved")
            won = pnl > 0

            rec = {
                "token_id": pos["token_id"],
                "condition_id": pos["condition_id"],
                "asset": pos["asset"],
                "side": pos["side"],
                "entry_price": pos["entry_price"],
                "avg_entry": round(entry, 6),
                "fair_at_entry": pos["fair_at_entry"],
                "ev_ratio": pos["ev_ratio"],
                "stoikov_edge_bps": pos["stoikov_edge_bps"],
                "edge_bps": pos["edge_bps"],
                "question": pos["question"],
                "size": pos["size"],
                "fills": pos.get("fills", 1),
                "notional": pos.get("notional", 0),
                "opened_at": pos["opened_at"],
                "exit_price": round(exit_price, 6),
                "pnl": round(pnl, 4),
                "closed_at": utc_now(),
                "won": won,
                "resolution_type": res_type,
                "is_binary_resolved": is_binary,
            }
            closed_list.append(rec)
            if len(closed_list) > 500:
                del closed_list[:len(closed_list) - 500]

            if mode == "unit":
                self._unit_pnl += pnl
                if won:
                    self._unit_wins += 1
                else:
                    self._unit_losses += 1
            else:
                self._le_pnl += pnl
                if won:
                    self._le_wins += 1
                else:
                    self._le_losses += 1

                # FP/FN only from LE mode (represents real decision impact)
                disagree = self._disagreements.pop(token_id, None)
                if disagree and is_binary:
                    if disagree["shadow_would_trade"] and not won:
                        self._m["false_positives"] += 1
                    elif not disagree["shadow_would_trade"] and disagree["live_traded"] and won:
                        self._m["false_negatives"] += 1

            logger.info(
                f"[SHADOW-SNIPER] {mode.upper()} resolved ({res_type}): {pos['asset']} {pos['side']} "
                f"size={pos['size']} entry={entry:.4f} exit={exit_price:.4f} "
                f"pnl=${pnl:.4f}"
            )

    # ---- Report ----

    def _mode_stats(self, positions, closed_list, total_pnl, wins, losses):
        total_trades = wins + losses
        now = datetime.now(timezone.utc)
        rolling = {"1h": 0.0, "3h": 0.0, "6h": 0.0}
        for t in closed_list:
            try:
                ca = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                age_h = (now - ca).total_seconds() / 3600
                if age_h <= 1:
                    rolling["1h"] += t["pnl"]
                if age_h <= 3:
                    rolling["3h"] += t["pnl"]
                if age_h <= 6:
                    rolling["6h"] += t["pnl"]
            except (ValueError, TypeError):
                pass

        binary_closed = [t for t in closed_list if t.get("is_binary_resolved")]
        binary_wins = sum(1 for t in binary_closed if t["won"])

        open_exposure = sum(p["size"] * (p.get("avg_entry", p["entry_price"])) for p in positions.values())
        total_size = sum(p["size"] for p in positions.values())

        return {
            "pnl_total": round(total_pnl, 4),
            "win_rate": round(wins / total_trades if total_trades else 0, 4),
            "binary_win_rate": round(binary_wins / len(binary_closed) if binary_closed else 0, 4),
            "binary_resolved": len(binary_closed),
            "closed_trades": total_trades,
            "open_positions": len(positions),
            "open_exposure": round(open_exposure, 2),
            "open_total_size": round(total_size, 2),
            "pnl_per_trade": round(total_pnl / total_trades if total_trades else 0, 4),
            "rolling_pnl": {k: round(v, 4) for k, v in rolling.items()},
        }

    def get_comparison_report(self):
        total = self._m["total_evaluations"]
        meaningful = self._m["meaningful_evaluations"]
        if total == 0:
            return {"status": "no_data", "message": "No evaluations yet"}

        shadow_edges = [e["edge_bps"] for e in self._evaluations if e["shadow_would_trade"]]
        live_edges = [e["edge_bps"] for e in self._evaluations if e["live_traded"]]

        unit_size = self._get_live_size()
        max_pos = self._get_max_position_size()

        return {
            "status": "active",
            "total_evaluations": total,
            "meaningful_evaluations": meaningful,
            "comparison": {
                "live": {
                    "trade_count": self._m["live_traded"],
                    "skip_count": self._m["live_skipped"],
                    "avg_edge_bps": round(sum(live_edges) / len(live_edges) if live_edges else 0, 1),
                },
                "agreement_rate": round(self._m["agreements"] / total if total else 0, 4),
                "meaningful_agreement_rate": round(
                    self._m["meaningful_agreements"] / meaningful if meaningful else 0, 4),
                "false_positives": self._m["false_positives"],
                "false_negatives": self._m["false_negatives"],
                "shadow_signals": {
                    "trade_count": self._m["shadow_would_trade"],
                    "skip_count": self._m["shadow_would_skip"],
                    "avg_edge_bps": round(
                        sum(shadow_edges) / len(shadow_edges) if shadow_edges else 0, 1),
                },
            },
            "unit_size": self._mode_stats(
                self._unit_positions, self._unit_closed,
                self._unit_pnl, self._unit_wins, self._unit_losses,
            ),
            "live_equivalent": self._mode_stats(
                self._le_positions, self._le_closed,
                self._le_pnl, self._le_wins, self._le_losses,
            ),
            "sizing": {
                "unit": {
                    "per_signal": unit_size,
                    "accumulation": False,
                    "max_size": unit_size,
                    "note": f"${unit_size}/signal, one entry per market, no accumulation",
                },
                "live_equivalent": {
                    "per_signal": unit_size,
                    "accumulation": True,
                    "max_size": max_pos,
                    "note": f"${unit_size}/signal, accumulates up to {max_pos} shares per market (same as live)",
                },
            },
            "config": {
                "min_ev_ratio": self._config.min_ev_ratio,
                "gamma": self._config.gamma,
                "inventory_decay": self._config.inventory_decay,
            },
            "last_eval_time": self._m["last_eval_time"],
        }

    def get_recent_evaluations(self, limit=50):
        return list(reversed(self._evaluations[-limit:]))

    def _enrich_positions(self, positions):
        result = []
        for pos in positions.values():
            market = self._state.get_market(pos["token_id"]) if self._state else None
            cp = (market.mid_price if market and market.mid_price else None)
            entry = pos.get("avg_entry", pos["entry_price"])
            unrealized = (cp - entry) * pos["size"] if cp is not None else 0.0
            result.append({
                "token_id": pos["token_id"],
                "condition_id": pos["condition_id"],
                "asset": pos["asset"],
                "side": pos["side"],
                "entry_price": pos["entry_price"],
                "avg_entry": round(entry, 6),
                "fair_at_entry": pos["fair_at_entry"],
                "ev_ratio": pos["ev_ratio"],
                "stoikov_edge_bps": pos["stoikov_edge_bps"],
                "edge_bps": pos["edge_bps"],
                "question": pos["question"],
                "size": pos["size"],
                "fills": pos.get("fills", 1),
                "notional": pos.get("notional", 0),
                "opened_at": pos["opened_at"],
                "tte_seconds": pos["tte_seconds"],
                "current_price": round(cp, 6) if cp else None,
                "unrealized_pnl": round(unrealized, 4),
            })
        return result

    def get_unit_positions(self):
        return self._enrich_positions(self._unit_positions)

    def get_le_positions(self):
        return self._enrich_positions(self._le_positions)

    def get_unit_closed(self, limit=50):
        return list(reversed(self._unit_closed[-limit:]))

    def get_le_closed(self, limit=50):
        return list(reversed(self._le_closed[-limit:]))
