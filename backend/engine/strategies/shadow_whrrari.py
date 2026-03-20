"""Whrrari Fair-Value / LMSR Arb Shadow — multi-outcome fair-value heuristic.

For multi-outcome market groups (3+ outcomes), computes a model fair-value
probability distribution using an LMSR-inspired heuristic and flags
hypothetical arb opportunities when crowd prices deviate materially.
100% shadow — no live orders, research heuristic only.
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models import utc_now
from engine.strategies.arb_pricing import compute_data_age

logger = logging.getLogger(__name__)


def _lmsr_fair_probs(prices: List[float], liquidity_param: float = 2.0) -> List[float]:
    """Compute LMSR-inspired fair probabilities from market prices.

    Uses a softmax-like transformation to derive a probability distribution
    from observed prices, with a liquidity parameter controlling sharpness.
    This treats the market as an LMSR market maker with parameter b.
    """
    if not prices or all(p <= 0 for p in prices):
        n = len(prices) if prices else 1
        return [1.0 / n] * n

    # Log-odds from prices, clamp to avoid log(0)
    clamped = [max(0.01, min(0.99, p)) for p in prices]
    log_odds = [math.log(p / (1.0 - p)) for p in clamped]

    # Softmax with liquidity scaling
    scaled = [lo / liquidity_param for lo in log_odds]
    max_s = max(scaled)
    exps = [math.exp(s - max_s) for s in scaled]
    total = sum(exps)

    return [e / total for e in exps]


class WhrrariShadowEngine:

    def __init__(self):
        self._state = None
        self._running = False

        # Config
        self._min_edge_bps = 300.0          # 3% min deviation to flag
        self._min_outcomes = 3              # minimum outcomes per group
        self._max_stale_seconds = 120.0
        self._scan_interval = 30.0          # seconds between scans
        self._signal_size = 3.0
        self._liquidity_param = 2.0         # LMSR b parameter
        self._min_liquidity = 100.0

        self._evaluations: List[dict] = []
        self._max_evaluations = 1500

        # Unit-size positions
        self._unit_positions: Dict[str, dict] = {}
        self._unit_closed: List[dict] = []
        self._unit_pnl = 0.0
        self._unit_wins = 0
        self._unit_losses = 0

        self._cooldown: Dict[str, float] = {}
        self._cooldown_seconds = 300.0

        self._m = {
            "total_scans": 0,
            "groups_found": 0,
            "groups_evaluated": 0,
            "deviations_found": 0,
            "hypothetical_trades": 0,
            "last_scan_time": None,
        }

    async def start(self, state):
        self._state = state
        self._running = True
        asyncio.create_task(self._scan_loop())
        asyncio.create_task(self._resolution_loop())
        logger.info("[WHRRARI] Started — LMSR fair-value shadow scanner")

    async def stop(self):
        self._running = False

    # ---- Scan Loop ----

    async def _scan_loop(self):
        await asyncio.sleep(15)
        while self._running:
            try:
                self._scan()
            except Exception as e:
                logger.error(f"[WHRRARI] Scan error: {e}")
            await asyncio.sleep(self._scan_interval)

    def _find_multi_outcome_groups(self) -> Dict[str, List]:
        """Group markets into multi-outcome events (same as arb_scanner pattern)."""
        import re
        by_event: Dict[str, List] = {}

        for snap in self._state.markets.values():
            if not snap.mid_price or snap.mid_price <= 0 or snap.mid_price >= 1.0:
                continue
            out = (snap.outcome or "").upper()
            if "NO" in out and "YES" not in out:
                continue

            q = snap.question or ""
            if not q:
                continue

            # Weather pattern
            weather_m = re.search(
                r'(?:highest|high)\s+temp.*?in\s+(.+?)\s+be\s+.*?on\s+(.+?)[\?$]',
                q, re.IGNORECASE
            )
            if weather_m:
                city = weather_m.group(1).strip().lower()
                date_str = weather_m.group(2).strip().lower().rstrip("?")
                event_key = f"weather|{city}|{date_str}"
            else:
                normalized = q.lower().strip().rstrip("?")
                normalized = re.sub(r'[\$\u20ac\u00a3]\s*[\d,]+\.?\d*', 'X', normalized)
                normalized = re.sub(r'\d+[\u00b0\u2109\u2103]?\s*[-\u2013]\s*\d+[\u00b0\u2109\u2103]?', 'X', normalized)
                normalized = re.sub(r'(?:above|below|over|under|between|exactly)\s+[\d,.]+', 'X', normalized)
                event_key = f"universal|{normalized[:80]}"

            if event_key not in by_event:
                by_event[event_key] = []
            by_event[event_key].append(snap)

        return {key: snaps for key, snaps in by_event.items()
                if len(snaps) >= self._min_outcomes}

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

        groups = self._find_multi_outcome_groups()
        self._m["groups_found"] = len(groups)

        for event_key, outcomes in groups.items():
            self._m["groups_evaluated"] += 1

            # Collect prices and check staleness
            prices = []
            token_ids = []
            max_age = 0.0
            min_liq = float("inf")
            question = ""

            for snap in outcomes:
                price = snap.mid_price or 0
                if price <= 0:
                    continue
                prices.append(price)
                token_ids.append(snap.token_id)
                max_age = max(max_age, compute_data_age(snap.updated_at))
                min_liq = min(min_liq, snap.liquidity)
                if not question:
                    question = snap.question or ""

            if len(prices) < self._min_outcomes:
                continue
            if max_age > self._max_stale_seconds:
                continue
            if min_liq < self._min_liquidity:
                continue

            # Compute LMSR fair values
            fair_probs = _lmsr_fair_probs(prices, self._liquidity_param)
            price_sum = sum(prices)

            # Find deviations: where model fair value differs from market price
            best_edge_bps = 0.0
            best_idx = -1
            deviations = []

            for i, (fp, mp) in enumerate(zip(fair_probs, prices)):
                edge = fp - mp
                edge_bps = edge * 10000
                deviations.append({
                    "token_id": token_ids[i],
                    "market_price": round(mp, 6),
                    "fair_prob": round(fp, 6),
                    "edge_bps": round(edge_bps, 1),
                })
                if edge_bps > best_edge_bps:
                    best_edge_bps = edge_bps
                    best_idx = i

            if best_edge_bps >= self._min_edge_bps:
                self._m["deviations_found"] += 1

            record = {
                "timestamp": now,
                "event_key": event_key[:60],
                "question": question[:80],
                "outcome_count": len(prices),
                "price_sum": round(price_sum, 4),
                "best_edge_bps": round(best_edge_bps, 1),
                "best_token": token_ids[best_idx] if best_idx >= 0 else "",
                "deviations": deviations[:8],  # limit for payload size
                "would_trade": best_edge_bps >= self._min_edge_bps,
            }
            self._evaluations.append(record)
            if len(self._evaluations) > self._max_evaluations:
                self._evaluations = self._evaluations[-self._max_evaluations:]

            # Open hypothetical position on the most underpriced outcome
            if best_edge_bps >= self._min_edge_bps and best_idx >= 0:
                tid = token_ids[best_idx]
                if tid not in self._unit_positions and event_key not in self._cooldown:
                    self._unit_positions[tid] = {
                        "token_id": tid,
                        "event_key": event_key,
                        "question": question,
                        "outcome_count": len(prices),
                        "entry_price": prices[best_idx],
                        "avg_entry": prices[best_idx],
                        "fair_prob_at_entry": round(fair_probs[best_idx], 6),
                        "edge_bps_at_entry": round(best_edge_bps, 1),
                        "price_sum_at_entry": round(price_sum, 4),
                        "size": self._signal_size,
                        "fills": 1,
                        "notional": round(self._signal_size * prices[best_idx], 4),
                        "opened_at": now,
                    }
                    self._cooldown[event_key] = now_mono
                    self._m["hypothetical_trades"] += 1

        self._m["last_scan_time"] = now

    # ---- Resolution ----

    async def _resolution_loop(self):
        await asyncio.sleep(90)
        while self._running:
            try:
                self._resolve()
            except Exception as e:
                logger.error(f"[WHRRARI] Resolution error: {e}")
            await asyncio.sleep(180)

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
                elif elapsed > 172800:  # 48h max hold for multi-outcome
                    to_close.append((token_id, cp, "expired_mtm"))
            elif elapsed > 172800:
                to_close.append((token_id, 0.5, "no_data"))

        for token_id, exit_price, res_type in to_close:
            pos = self._unit_positions.pop(token_id)
            entry = pos.get("avg_entry", pos["entry_price"])
            pnl = (exit_price - entry) * pos["size"]
            won = pnl > 0

            rec = {
                **{k: v for k, v in pos.items()},
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
                f"[WHRRARI] Resolved ({res_type}): {pos.get('question','')[:40]}.. "
                f"edge={pos.get('edge_bps_at_entry',0):.0f}bps pnl=${pnl:.4f}"
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
            "experiment": "whrrari_lmsr",
            "description": "LMSR fair-value model for multi-outcome arb detection",
            "metrics": self._m,
            "config": {
                "min_edge_bps": self._min_edge_bps,
                "liquidity_param": self._liquidity_param,
                "min_outcomes": self._min_outcomes,
                "scan_interval": self._scan_interval,
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
            "sample_size_sufficient": total_trades >= 15,
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
