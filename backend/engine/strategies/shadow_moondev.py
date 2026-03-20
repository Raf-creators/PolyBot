"""MoonDev Short-Window Shadow — 5m/15m only crypto sniper shadow.

Receives the same signal feed as the main shadow sniper but ONLY
evaluates markets with 5-minute or 15-minute windows.
100% shadow — no live orders, no live config changes.
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models import utc_now

logger = logging.getLogger(__name__)

ALLOWED_WINDOWS = {"5m", "15m"}


class MoonDevShadowEngine:

    def __init__(self):
        self._state = None
        self._live_sniper = None
        self._running = False

        self._evaluations: List[dict] = []
        self._max_evaluations = 1500

        # Unit-size mode
        self._unit_positions: Dict[str, dict] = {}
        self._unit_closed: List[dict] = []
        self._unit_pnl = 0.0
        self._unit_wins = 0
        self._unit_losses = 0

        # Live-equivalent mode
        self._le_positions: Dict[str, dict] = {}
        self._le_closed: List[dict] = []
        self._le_pnl = 0.0
        self._le_wins = 0
        self._le_losses = 0

        self._m = {
            "total_signals_received": 0,
            "window_filtered_out": 0,
            "evaluated": 0,
            "would_trade": 0,
            "would_skip": 0,
            "last_eval_time": None,
        }

    async def start(self, state, live_sniper):
        self._state = state
        self._live_sniper = live_sniper
        self._running = True
        asyncio.create_task(self._resolution_loop())
        logger.info("[MOONDEV] Started — short-window shadow (5m/15m only)")

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

    # ---- Core: called from crypto_sniper._evaluate_all() ----

    def evaluate_signal(
        self, condition_id, asset, direction, spot, fair_prob,
        yes_price, no_price, edge_bps_yes, edge_bps_no,
        tte_seconds, volatility, live_decision, live_rejection,
        token_id_yes, token_id_no, question, window,
    ):
        self._m["total_signals_received"] += 1

        # WINDOW GATE: only 5m and 15m
        if window not in ALLOWED_WINDOWS:
            self._m["window_filtered_out"] += 1
            return None

        self._m["evaluated"] += 1
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

        # Simple edge threshold for short windows: tighter than live
        min_edge = 150.0  # 1.5% min edge for short windows
        would_trade = edge_bps >= min_edge and side != "none"

        if would_trade:
            self._m["would_trade"] += 1
        else:
            self._m["would_skip"] += 1

        # Position management
        signal_size = self._get_live_size()
        max_pos = self._get_max_position_size()

        if would_trade and token_id:
            # Unit-size: one entry per token
            if token_id not in self._unit_positions:
                self._unit_positions[token_id] = self._make_position(
                    token_id, condition_id, asset, side, market_price,
                    fair, edge_bps, tte_seconds, now, question, window, signal_size,
                )

            # Live-equivalent: accumulate
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
            else:
                self._le_positions[token_id] = self._make_position(
                    token_id, condition_id, asset, side, market_price,
                    fair, edge_bps, tte_seconds, now, question, window, signal_size,
                )

        live_traded = live_decision.startswith("trade")
        record = {
            "timestamp": now,
            "condition_id": condition_id,
            "asset": asset,
            "window": window,
            "spot": round(spot, 2),
            "fair_prob": round(fair, 6),
            "market_price": round(market_price, 6),
            "edge_bps": round(edge_bps, 1),
            "tte_seconds": round(tte_seconds, 1),
            "live_decision": live_decision,
            "live_traded": live_traded,
            "moondev_would_trade": would_trade,
            "side": side if would_trade else "none",
            "question": question[:80],
        }
        self._evaluations.append(record)
        if len(self._evaluations) > self._max_evaluations:
            self._evaluations = self._evaluations[-self._max_evaluations:]
        self._m["last_eval_time"] = now
        return record

    @staticmethod
    def _make_position(token_id, condition_id, asset, side, price,
                       fair, edge_bps, tte_seconds, now, question, window, size):
        return {
            "token_id": token_id, "condition_id": condition_id,
            "asset": asset, "side": side, "window": window,
            "entry_price": price, "avg_entry": price,
            "fair_at_entry": fair, "edge_bps": edge_bps,
            "tte_seconds": tte_seconds, "opened_at": now,
            "question": question, "size": size, "fills": 1,
            "notional": round(size * price, 4),
        }

    # ---- Resolution ----

    async def _resolution_loop(self):
        await asyncio.sleep(60)
        while self._running:
            try:
                self._resolve_all()
            except Exception as e:
                logger.error(f"[MOONDEV] Resolution error: {e}")
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
            won = pnl > 0

            rec = {
                "token_id": pos["token_id"],
                "condition_id": pos["condition_id"],
                "asset": pos["asset"],
                "side": pos["side"],
                "window": pos.get("window", ""),
                "entry_price": pos["entry_price"],
                "avg_entry": round(entry, 6),
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
                "is_binary_resolved": res_type.startswith("resolved"),
            }
            closed_list.append(rec)
            if len(closed_list) > 500:
                del closed_list[:len(closed_list) - 500]

            if mode == "unit":
                self._unit_pnl += pnl
                if won: self._unit_wins += 1
                else: self._unit_losses += 1
            else:
                self._le_pnl += pnl
                if won: self._le_wins += 1
                else: self._le_losses += 1

            logger.info(
                f"[MOONDEV] {mode.upper()} resolved ({res_type}): {pos['asset']} {pos['side']} "
                f"window={pos.get('window','')} pnl=${pnl:.4f}"
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
                if age_h <= 1: rolling["1h"] += t["pnl"]
                if age_h <= 3: rolling["3h"] += t["pnl"]
                if age_h <= 6: rolling["6h"] += t["pnl"]
            except (ValueError, TypeError):
                pass

        binary_closed = [t for t in closed_list if t.get("is_binary_resolved")]
        binary_wins = sum(1 for t in binary_closed if t["won"])
        open_exposure = sum(p["size"] * p.get("avg_entry", p["entry_price"]) for p in positions.values())

        return {
            "pnl_total": round(total_pnl, 4),
            "win_rate": round(wins / total_trades if total_trades else 0, 4),
            "binary_win_rate": round(binary_wins / len(binary_closed) if binary_closed else 0, 4),
            "binary_resolved": len(binary_closed),
            "closed_trades": total_trades,
            "open_positions": len(positions),
            "open_exposure": round(open_exposure, 2),
            "pnl_per_trade": round(total_pnl / total_trades if total_trades else 0, 4),
            "rolling_pnl": {k: round(v, 4) for k, v in rolling.items()},
            "resolved_count": len(binary_closed),
            "unresolved_count": len(positions),
        }

    def get_report(self):
        total = self._m["evaluated"]
        return {
            "status": "active" if total > 0 else "collecting",
            "experiment": "moondev_short_window",
            "description": "Shadow sniper restricted to 5m/15m windows only",
            "metrics": self._m,
            "unit_size": self._mode_stats(
                self._unit_positions, self._unit_closed,
                self._unit_pnl, self._unit_wins, self._unit_losses,
            ),
            "live_equivalent": self._mode_stats(
                self._le_positions, self._le_closed,
                self._le_pnl, self._le_wins, self._le_losses,
            ),
            "sample_size_sufficient": total >= 30,
            "last_eval_time": self._m["last_eval_time"],
        }

    def get_evaluations(self, limit=50):
        return list(reversed(self._evaluations[-limit:]))

    def _enrich_positions(self, positions):
        result = []
        for pos in positions.values():
            market = self._state.get_market(pos["token_id"]) if self._state else None
            cp = (market.mid_price if market and market.mid_price else None)
            entry = pos.get("avg_entry", pos["entry_price"])
            unrealized = (cp - entry) * pos["size"] if cp is not None else 0.0
            result.append({**pos, "current_price": round(cp, 6) if cp else None,
                           "unrealized_pnl": round(unrealized, 4)})
        return result

    def get_positions(self, mode="unit"):
        if mode == "le":
            return self._enrich_positions(self._le_positions)
        return self._enrich_positions(self._unit_positions)

    def get_closed(self, mode="unit", limit=50):
        cl = self._le_closed if mode == "le" else self._unit_closed
        return list(reversed(cl[-limit:]))
