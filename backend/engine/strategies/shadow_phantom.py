"""Phantom Spread Shadow — detects YES+NO pricing dislocations + Gabagool both-sides arb.

Two modes tracked in parallel:
  1. One-Side: Buy cheaper side when spread > threshold (original)
  2. Gabagool Both-Sides: Buy YES AND NO when sum < 0.96 (guaranteed structural arb)

100% shadow — no live orders.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models import utc_now
from engine.strategies.arb_pricing import compute_data_age

logger = logging.getLogger(__name__)


class PhantomSpreadEngine:

    def __init__(self):
        self._state = None
        self._running = False
        self._adaptive_shadow = None  # AdaptiveEdgeShadow (injected from server.py)

        self._min_spread_bps = 80.0
        self._gabagool_threshold = 0.985  # buy both when sum < this (matches live executor)
        self._max_stale_seconds = 60.0
        self._scan_interval = 15.0
        self._signal_size = 3.0

        self._evaluations: List[dict] = []
        self._max_evaluations = 1500

        # One-side positions (original)
        self._unit_positions: Dict[str, dict] = {}
        self._unit_closed: List[dict] = []
        self._unit_pnl = 0.0
        self._unit_wins = 0
        self._unit_losses = 0

        # Gabagool both-sides pairs: keyed by condition_id
        self._gaba_pairs: Dict[str, dict] = {}
        self._gaba_closed: List[dict] = []
        self._gaba_pnl = 0.0
        self._gaba_wins = 0
        self._gaba_losses = 0

        self._cooldown: Dict[str, float] = {}
        self._cooldown_seconds = 120.0

        self._m = {
            "total_scans": 0,
            "pairs_scanned": 0,
            "dislocations_found": 0,
            "hypothetical_trades": 0,
            "gabagool_pairs_found": 0,
            "gabagool_trades": 0,
            "last_scan_time": None,
        }

    async def start(self, state):
        self._state = state
        self._running = True
        asyncio.create_task(self._scan_loop())
        asyncio.create_task(self._resolution_loop())
        logger.info("[PHANTOM] Started — spread dislocation + Gabagool both-sides shadow")

    async def stop(self):
        self._running = False

    async def _scan_loop(self):
        await asyncio.sleep(10)
        while self._running:
            try:
                self._scan()
            except Exception as e:
                logger.error(f"[PHANTOM] Scan error: {e}")
            await asyncio.sleep(self._scan_interval)

    def _scan(self):
        if not self._state:
            return

        self._m["total_scans"] += 1
        now_ts = datetime.now(timezone.utc)
        now_mono = now_ts.timestamp()
        now = utc_now()

        self._cooldown = {k: v for k, v in self._cooldown.items()
                          if now_mono - v < self._cooldown_seconds}

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

        pairs_scanned = 0
        for cid, pair in by_condition.items():
            if "yes" not in pair or "no" not in pair:
                continue

            yes_snap, no_snap = pair["yes"], pair["no"]
            yp, np_ = yes_snap.mid_price, no_snap.mid_price
            if not yp or not np_ or yp <= 0 or np_ <= 0:
                continue

            y_age = compute_data_age(yes_snap.updated_at)
            n_age = compute_data_age(no_snap.updated_at)
            if max(y_age, n_age) > self._max_stale_seconds:
                continue

            pairs_scanned += 1
            price_sum = yp + np_
            spread = abs(1.0 - price_sum)
            spread_bps = spread * 10000

            # --- Gabagool both-sides check ---
            gabagool_eligible = price_sum < self._gabagool_threshold
            gabagool_edge = 1.0 - price_sum if gabagool_eligible else 0.0
            gabagool_edge_pct = gabagool_edge * 100

            if gabagool_eligible:
                self._m["gabagool_pairs_found"] += 1

            # --- One-side spread check ---
            one_side_eligible = spread_bps >= self._min_spread_bps

            if one_side_eligible:
                self._m["dislocations_found"] += 1

            if not one_side_eligible and not gabagool_eligible:
                continue

            # Determine one-side trade
            if price_sum < 1.0:
                if yp < np_:
                    side, token_id, entry_price = "buy_yes", yes_snap.token_id, yp
                else:
                    side, token_id, entry_price = "buy_no", no_snap.token_id, np_
                trade_type = "underpriced_pair"
            else:
                if yp < np_:
                    side, token_id, entry_price = "buy_yes", yes_snap.token_id, yp
                else:
                    side, token_id, entry_price = "buy_no", no_snap.token_id, np_
                trade_type = "overpriced_pair"

            on_cooldown = cid in self._cooldown
            question = yes_snap.question or ""

            record = {
                "timestamp": now,
                "condition_id": cid,
                "question": question[:80],
                "yes_price": round(yp, 6),
                "no_price": round(np_, 6),
                "price_sum": round(price_sum, 6),
                "spread_bps": round(spread_bps, 1),
                "trade_type": trade_type,
                "side": side,
                "token_id": token_id,
                "entry_price": round(entry_price, 6),
                "would_trade": one_side_eligible,
                "gabagool_eligible": gabagool_eligible,
                "gabagool_edge_pct": round(gabagool_edge_pct, 2),
            }
            self._evaluations.append(record)
            if len(self._evaluations) > self._max_evaluations:
                self._evaluations = self._evaluations[-self._max_evaluations:]

            # Feed dynamic Gabagool shadow — tests different thresholds per window
            if self._adaptive_shadow:
                try:
                    # Extract window from question (e.g., "5m", "15m", "1h")
                    import re
                    w_match = re.search(r'\b(5m|15m|1h|4h)\b', question, re.IGNORECASE)
                    window = w_match.group(1).lower() if w_match else None
                    self._adaptive_shadow.evaluate_gabagool_pair(
                        yes_price=yp, no_price=np_,
                        condition_id=cid, question=question,
                        window=window,
                    )
                except Exception:
                    pass

            if on_cooldown:
                continue

            # Open one-side position
            if one_side_eligible and token_id not in self._unit_positions:
                self._unit_positions[token_id] = {
                    "token_id": token_id, "condition_id": cid,
                    "question": question, "side": side,
                    "entry_price": entry_price, "avg_entry": entry_price,
                    "spread_bps_at_entry": round(spread_bps, 1),
                    "trade_type": trade_type,
                    "size": self._signal_size, "fills": 1,
                    "notional": round(self._signal_size * entry_price, 4),
                    "opened_at": now,
                }
                self._m["hypothetical_trades"] += 1

            # Open Gabagool both-sides pair
            if gabagool_eligible and cid not in self._gaba_pairs:
                pair_cost = yp + np_
                guaranteed_profit = (1.0 - pair_cost) * self._signal_size
                self._gaba_pairs[cid] = {
                    "condition_id": cid,
                    "question": question,
                    "yes_token_id": yes_snap.token_id,
                    "no_token_id": no_snap.token_id,
                    "yes_entry": round(yp, 6),
                    "no_entry": round(np_, 6),
                    "pair_cost": round(pair_cost, 6),
                    "guaranteed_edge_pct": round(gabagool_edge_pct, 2),
                    "guaranteed_profit": round(guaranteed_profit, 4),
                    "size": self._signal_size,
                    "notional": round(self._signal_size * pair_cost, 4),
                    "opened_at": now,
                }
                self._m["gabagool_trades"] += 1

            self._cooldown[cid] = now_mono

        self._m["pairs_scanned"] = pairs_scanned
        self._m["last_scan_time"] = now

    # ---- Resolution ----

    async def _resolution_loop(self):
        await asyncio.sleep(90)
        while self._running:
            try:
                self._resolve_one_side()
                self._resolve_gabagool()
            except Exception as e:
                logger.error(f"[PHANTOM] Resolution error: {e}")
            await asyncio.sleep(120)

    def _resolve_one_side(self):
        if not self._state:
            return
        now = datetime.now(timezone.utc)
        to_close = []
        for token_id, pos in self._unit_positions.items():
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
                elif elapsed > 86400:
                    to_close.append((token_id, cp, "expired_mtm"))
            elif elapsed > 86400:
                to_close.append((token_id, 0.5, "no_data"))

        for token_id, exit_price, res_type in to_close:
            pos = self._unit_positions.pop(token_id)
            entry = pos.get("avg_entry", pos["entry_price"])
            pnl = round((exit_price - entry) * pos["size"], 4)
            rec = {
                **pos, "exit_price": round(exit_price, 6), "pnl": pnl,
                "closed_at": utc_now(), "won": pnl > 0,
                "resolution_type": res_type,
                "is_binary_resolved": res_type.startswith("resolved"),
            }
            self._unit_closed.append(rec)
            if len(self._unit_closed) > 500:
                del self._unit_closed[:len(self._unit_closed) - 500]
            self._unit_pnl += pnl
            if pnl > 0:
                self._unit_wins += 1
            else:
                self._unit_losses += 1

    def _resolve_gabagool(self):
        """Resolve both-sides pairs. One side resolves to $1, the other to $0.
        Profit = size * (1.0 - pair_cost)."""
        if not self._state:
            return
        now = datetime.now(timezone.utc)
        to_close = []

        for cid, pair in self._gaba_pairs.items():
            yes_market = self._state.get_market(pair["yes_token_id"])
            no_market = self._state.get_market(pair["no_token_id"])
            yp = (yes_market.mid_price if yes_market else None)
            np_ = (no_market.mid_price if no_market else None)

            try:
                opened = datetime.fromisoformat(pair["opened_at"].replace("Z", "+00:00"))
                elapsed = (now - opened).total_seconds()
            except (ValueError, TypeError):
                elapsed = 0

            resolved = False
            if yp is not None and (yp >= 0.92 or yp <= 0.08):
                resolved = True
            elif np_ is not None and (np_ >= 0.92 or np_ <= 0.08):
                resolved = True
            elif elapsed > 86400:
                resolved = True

            if resolved:
                # Guaranteed profit: bought both sides for pair_cost, one resolves to $1
                # PnL = size * (1.0 - pair_cost)
                pnl = round(pair["size"] * (1.0 - pair["pair_cost"]), 4)
                if elapsed > 86400 and yp is not None and np_ is not None:
                    # Expired: mark to market both sides
                    pnl = round(pair["size"] * ((yp + np_) - pair["pair_cost"]), 4)

                to_close.append((cid, pnl, "resolved" if elapsed <= 86400 else "expired_mtm"))

        for cid, pnl, res_type in to_close:
            pair = self._gaba_pairs.pop(cid)
            rec = {
                **pair, "pnl": pnl, "closed_at": utc_now(),
                "won": pnl > 0, "resolution_type": res_type,
                "is_binary_resolved": res_type == "resolved",
                "hours_to_resolve": 0,
            }
            try:
                opened = datetime.fromisoformat(pair["opened_at"].replace("Z", "+00:00"))
                rec["hours_to_resolve"] = round((datetime.now(timezone.utc) - opened).total_seconds() / 3600, 2)
            except (ValueError, TypeError):
                pass

            self._gaba_closed.append(rec)
            if len(self._gaba_closed) > 500:
                del self._gaba_closed[:len(self._gaba_closed) - 500]
            self._gaba_pnl += pnl
            if pnl > 0:
                self._gaba_wins += 1
            else:
                self._gaba_losses += 1

            logger.info(
                f"[PHANTOM-GABA] Resolved: {pair.get('question','')[:40]}.. "
                f"pair_cost={pair['pair_cost']:.4f} edge={pair['guaranteed_edge_pct']:.1f}% "
                f"pnl=${pnl:.4f} hours={rec['hours_to_resolve']:.1f}"
            )

    # ---- Report ----

    def _mode_stats(self, positions, closed, total_pnl, wins, losses):
        total = wins + losses
        now = datetime.now(timezone.utc)
        rolling = {"1h": 0.0, "3h": 0.0, "6h": 0.0}
        for t in closed:
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

        binary = [t for t in closed if t.get("is_binary_resolved")]
        binary_wins = sum(1 for t in binary if t["won"])
        if isinstance(positions, dict):
            open_exp = sum(p.get("notional", 0) for p in positions.values())
            open_count = len(positions)
        else:
            open_exp = sum(p.get("notional", 0) for p in positions)
            open_count = len(positions)

        return {
            "pnl_total": round(total_pnl, 4),
            "win_rate": round(wins / total if total else 0, 4),
            "binary_win_rate": round(binary_wins / len(binary) if binary else 0, 4),
            "binary_resolved": len(binary),
            "closed_trades": total,
            "open_positions": open_count,
            "open_exposure": round(open_exp, 2),
            "pnl_per_trade": round(total_pnl / total if total else 0, 4),
            "rolling_pnl": {k: round(v, 4) for k, v in rolling.items()},
            "resolved_count": len(binary),
            "unresolved_count": open_count,
        }

    def get_report(self):
        return {
            "status": "active" if self._m["total_scans"] > 0 else "collecting",
            "experiment": "phantom_spread",
            "description": "Spread dislocation detection + Gabagool both-sides structural arb",
            "metrics": self._m,
            "config": {
                "min_spread_bps": self._min_spread_bps,
                "gabagool_threshold": self._gabagool_threshold,
                "scan_interval": self._scan_interval,
                "signal_size": self._signal_size,
            },
            "unit_size": self._mode_stats(
                self._unit_positions, self._unit_closed,
                self._unit_pnl, self._unit_wins, self._unit_losses,
            ),
            "gabagool": self._mode_stats(
                self._gaba_pairs, self._gaba_closed,
                self._gaba_pnl, self._gaba_wins, self._gaba_losses,
            ),
            "sample_size_sufficient": (self._unit_wins + self._unit_losses) >= 20,
            "last_scan_time": self._m["last_scan_time"],
        }

    def get_evaluations(self, limit=50):
        return list(reversed(self._evaluations[-limit:]))

    def get_positions(self, mode="unit"):
        if mode == "gabagool":
            return list(self._gaba_pairs.values())
        result = []
        for pos in self._unit_positions.values():
            market = self._state.get_market(pos["token_id"]) if self._state else None
            cp = (market.mid_price if market and market.mid_price else None)
            entry = pos.get("avg_entry", pos["entry_price"])
            unrealized = (cp - entry) * pos["size"] if cp is not None else 0.0
            result.append({**pos, "current_price": round(cp, 6) if cp else None,
                           "unrealized_pnl": round(unrealized, 4)})
        return result

    def get_closed(self, mode="unit", limit=50):
        cl = self._gaba_closed if mode == "gabagool" else self._unit_closed
        return list(reversed(cl[-limit:]))
