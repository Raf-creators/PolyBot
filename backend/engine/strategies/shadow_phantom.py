"""Phantom Spread Shadow — detects short-window YES+NO pricing dislocations.

Scans binary crypto pairs for cases where YES_mid + NO_mid deviates
significantly from 1.0, indicating a spread opportunity.
Logs hypothetical trades when the dislocation exceeds a threshold.
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

        # Config
        self._min_spread_bps = 80.0    # 0.8% minimum spread dislocation to flag
        self._max_stale_seconds = 60.0
        self._scan_interval = 15.0     # seconds between scans
        self._signal_size = 3.0        # unit size

        self._evaluations: List[dict] = []
        self._max_evaluations = 1500

        # Unit-size positions
        self._unit_positions: Dict[str, dict] = {}
        self._unit_closed: List[dict] = []
        self._unit_pnl = 0.0
        self._unit_wins = 0
        self._unit_losses = 0

        self._cooldown: Dict[str, float] = {}
        self._cooldown_seconds = 120.0

        self._m = {
            "total_scans": 0,
            "pairs_scanned": 0,
            "dislocations_found": 0,
            "hypothetical_trades": 0,
            "last_scan_time": None,
        }

    async def start(self, state):
        self._state = state
        self._running = True
        asyncio.create_task(self._scan_loop())
        asyncio.create_task(self._resolution_loop())
        logger.info("[PHANTOM] Started — spread dislocation shadow scanner")

    async def stop(self):
        self._running = False

    # ---- Scan Loop ----

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

        # Expire cooldowns
        self._cooldown = {k: v for k, v in self._cooldown.items()
                          if now_mono - v < self._cooldown_seconds}

        # Group markets by condition_id into binary pairs
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

            yes_snap = pair["yes"]
            no_snap = pair["no"]

            yp = yes_snap.mid_price
            np_ = no_snap.mid_price
            if not yp or not np_ or yp <= 0 or np_ <= 0:
                continue

            # Freshness
            y_age = compute_data_age(yes_snap.updated_at)
            n_age = compute_data_age(no_snap.updated_at)
            if max(y_age, n_age) > self._max_stale_seconds:
                continue

            pairs_scanned += 1
            price_sum = yp + np_
            spread = abs(1.0 - price_sum)
            spread_bps = spread * 10000

            if spread_bps < self._min_spread_bps:
                continue

            self._m["dislocations_found"] += 1

            # Determine trade direction:
            # If sum < 1.0, both sides are cheap → buy the cheaper side (more upside)
            # If sum > 1.0, both sides are expensive → theoretical sell (we log but don't short)
            if price_sum < 1.0:
                # Underpriced pair: buy the side with more room
                if yp < np_:
                    side, token_id, entry_price = "buy_yes", yes_snap.token_id, yp
                else:
                    side, token_id, entry_price = "buy_no", no_snap.token_id, np_
                trade_type = "underpriced_pair"
            else:
                # Overpriced pair: log but favor the cheaper side as less overpriced
                if yp < np_:
                    side, token_id, entry_price = "buy_yes", yes_snap.token_id, yp
                else:
                    side, token_id, entry_price = "buy_no", no_snap.token_id, np_
                trade_type = "overpriced_pair"

            # Cooldown check
            if cid in self._cooldown:
                continue

            would_trade = spread_bps >= self._min_spread_bps
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
                "would_trade": would_trade,
            }
            self._evaluations.append(record)
            if len(self._evaluations) > self._max_evaluations:
                self._evaluations = self._evaluations[-self._max_evaluations:]

            # Open hypothetical position (unit-size only for phantom)
            if would_trade and token_id not in self._unit_positions:
                self._unit_positions[token_id] = {
                    "token_id": token_id,
                    "condition_id": cid,
                    "question": question,
                    "side": side,
                    "entry_price": entry_price,
                    "avg_entry": entry_price,
                    "spread_bps_at_entry": round(spread_bps, 1),
                    "trade_type": trade_type,
                    "size": self._signal_size,
                    "fills": 1,
                    "notional": round(self._signal_size * entry_price, 4),
                    "opened_at": now,
                }
                self._cooldown[cid] = now_mono
                self._m["hypothetical_trades"] += 1

        self._m["pairs_scanned"] = pairs_scanned
        self._m["last_scan_time"] = now

    # ---- Resolution ----

    async def _resolution_loop(self):
        await asyncio.sleep(90)
        while self._running:
            try:
                self._resolve()
            except Exception as e:
                logger.error(f"[PHANTOM] Resolution error: {e}")
            await asyncio.sleep(120)

    def _resolve(self):
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
                elif elapsed > 86400:  # 24h max hold
                    to_close.append((token_id, cp, "expired_mtm"))
            elif elapsed > 86400:
                to_close.append((token_id, 0.5, "no_data"))

        for token_id, exit_price, res_type in to_close:
            pos = self._unit_positions.pop(token_id)
            entry = pos.get("avg_entry", pos["entry_price"])
            pnl = (exit_price - entry) * pos["size"]
            won = pnl > 0

            rec = {
                **{k: v for k, v in pos.items() if k != "notional"},
                "notional": pos.get("notional", 0),
                "exit_price": round(exit_price, 6),
                "pnl": round(pnl, 4),
                "closed_at": utc_now(),
                "won": won,
                "resolution_type": res_type,
                "is_binary_resolved": res_type.startswith("resolved"),
            }
            self._unit_closed.append(rec)
            if len(self._unit_closed) > 500:
                del self._unit_closed[:len(self._unit_closed) - 500]

            self._unit_pnl += pnl
            if won:
                self._unit_wins += 1
            else:
                self._unit_losses += 1

            logger.info(
                f"[PHANTOM] Resolved ({res_type}): {pos.get('question','')[:40]}.. "
                f"spread={pos.get('spread_bps_at_entry',0):.0f}bps pnl=${pnl:.4f}"
            )

    # ---- Report ----

    def get_report(self):
        total_trades = self._unit_wins + self._unit_losses
        now = datetime.now(timezone.utc)
        rolling = {"1h": 0.0, "3h": 0.0, "6h": 0.0}
        for t in self._unit_closed:
            try:
                ca = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
                age_h = (now - ca).total_seconds() / 3600
                if age_h <= 1: rolling["1h"] += t["pnl"]
                if age_h <= 3: rolling["3h"] += t["pnl"]
                if age_h <= 6: rolling["6h"] += t["pnl"]
            except (ValueError, TypeError):
                pass

        binary_closed = [t for t in self._unit_closed if t.get("is_binary_resolved")]
        binary_wins = sum(1 for t in binary_closed if t["won"])
        open_exposure = sum(p["size"] * p.get("avg_entry", p["entry_price"]) for p in self._unit_positions.values())

        return {
            "status": "active" if self._m["total_scans"] > 0 else "collecting",
            "experiment": "phantom_spread",
            "description": "Shadow detection for YES+NO pricing dislocations",
            "metrics": self._m,
            "config": {
                "min_spread_bps": self._min_spread_bps,
                "scan_interval": self._scan_interval,
                "signal_size": self._signal_size,
            },
            "unit_size": {
                "pnl_total": round(self._unit_pnl, 4),
                "win_rate": round(self._unit_wins / total_trades if total_trades else 0, 4),
                "binary_win_rate": round(binary_wins / len(binary_closed) if binary_closed else 0, 4),
                "binary_resolved": len(binary_closed),
                "closed_trades": total_trades,
                "open_positions": len(self._unit_positions),
                "open_exposure": round(open_exposure, 2),
                "pnl_per_trade": round(self._unit_pnl / total_trades if total_trades else 0, 4),
                "rolling_pnl": {k: round(v, 4) for k, v in rolling.items()},
                "resolved_count": len(binary_closed),
                "unresolved_count": len(self._unit_positions),
            },
            "sample_size_sufficient": total_trades >= 20,
            "last_scan_time": self._m["last_scan_time"],
        }

    def get_evaluations(self, limit=50):
        return list(reversed(self._evaluations[-limit:]))

    def get_positions(self):
        result = []
        for pos in self._unit_positions.values():
            market = self._state.get_market(pos["token_id"]) if self._state else None
            cp = (market.mid_price if market and market.mid_price else None)
            entry = pos.get("avg_entry", pos["entry_price"])
            unrealized = (cp - entry) * pos["size"] if cp is not None else 0.0
            result.append({**pos, "current_price": round(cp, 6) if cp else None,
                           "unrealized_pnl": round(unrealized, 4)})
        return result

    def get_closed(self, limit=50):
        return list(reversed(self._unit_closed[-limit:]))
