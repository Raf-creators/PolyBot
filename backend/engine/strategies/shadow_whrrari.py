"""Whrrari Fair-Value / LMSR Arb Shadow — multi-outcome fair-value heuristic.

For multi-outcome market groups (3+ outcomes), computes a model fair-value
probability distribution using an LMSR-inspired heuristic and flags
hypothetical arb opportunities when crowd prices deviate materially.
100% shadow — no live orders, research heuristic only.

Three sizing modes tracked in parallel:
  1. Unit-Size        — flat $3/signal, normalized research comparison
  2. Sandbox Notional — edge-tiered bands ($3/$8/$15), realistic arb sizing
  3. Crypto-Mirrored  — $3/signal accumulating to $25 cap, stress test only
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional

from models import utc_now
from engine.strategies.arb_pricing import compute_data_age

logger = logging.getLogger(__name__)

# ---- Sandbox Notional sizing bands ----
SANDBOX_BANDS = [
    (900.0, 15.0),   # edge >= 900bps → $15 high conviction
    (600.0, 8.0),    # edge >= 600bps → $8  moderate
    (300.0, 3.0),    # edge >= 300bps → $3  conservative (floor = min_edge_bps)
]

CRYPTO_SIGNAL_SIZE = 3.0
CRYPTO_MAX_POSITION = 25.0


def _lmsr_fair_probs(prices: List[float], liquidity_param: float = 2.0) -> List[float]:
    """Compute LMSR-inspired fair probabilities from market prices.

    Uses a softmax-like transformation to derive a probability distribution
    from observed prices, with a liquidity parameter controlling sharpness.
    """
    if not prices or all(p <= 0 for p in prices):
        n = len(prices) if prices else 1
        return [1.0 / n] * n

    clamped = [max(0.01, min(0.99, p)) for p in prices]
    log_odds = [math.log(p / (1.0 - p)) for p in clamped]

    scaled = [lo / liquidity_param for lo in log_odds]
    max_s = max(scaled)
    exps = [math.exp(s - max_s) for s in scaled]
    total = sum(exps)

    return [e / total for e in exps]


def _sandbox_size(edge_bps: float) -> float:
    """Determine sandbox notional size from edge magnitude."""
    for threshold, size in SANDBOX_BANDS:
        if edge_bps >= threshold:
            return size
    return 0.0  # below floor — no trade


class _ModeTracker:
    """Tracks positions + PnL for a single sizing mode."""

    __slots__ = ('positions', 'closed', 'pnl', 'wins', 'losses')

    def __init__(self):
        self.positions: Dict[str, dict] = {}
        self.closed: List[dict] = []
        self.pnl = 0.0
        self.wins = 0
        self.losses = 0

    def record_close(self, rec: dict):
        self.closed.append(rec)
        if len(self.closed) > 500:
            del self.closed[:len(self.closed) - 500]
        self.pnl += rec["pnl"]
        if rec["won"]:
            self.wins += 1
        else:
            self.losses += 1


class WhrrariShadowEngine:

    def __init__(self):
        self._state = None
        self._running = False

        # Config
        self._min_edge_bps = 300.0
        self._min_outcomes = 3
        self._max_stale_seconds = 120.0
        self._scan_interval = 30.0
        self._liquidity_param = 2.0
        self._min_liquidity = 100.0

        self._evaluations: List[dict] = []
        self._max_evaluations = 1500

        # Three parallel mode trackers
        self._unit = _ModeTracker()
        self._sandbox = _ModeTracker()
        self._crypto = _ModeTracker()

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
        logger.info("[WHRRARI] Started — LMSR fair-value shadow (3 sizing modes)")

    async def stop(self):
        self._running = False

    def _tracker(self, mode: str) -> _ModeTracker:
        if mode == "sandbox":
            return self._sandbox
        if mode == "crypto":
            return self._crypto
        return self._unit

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

            weather_m = re.search(
                r'(?:highest|high)\s+temp.*?in\s+(.+?)\s+be\s+.*?on\s+(.+?)[\?$]',
                q, re.IGNORECASE,
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

        self._cooldown = {k: v for k, v in self._cooldown.items()
                          if now_mono - v < self._cooldown_seconds}

        groups = self._find_multi_outcome_groups()
        self._m["groups_found"] = len(groups)

        for event_key, outcomes in groups.items():
            self._m["groups_evaluated"] += 1

            prices, token_ids = [], []
            max_age, min_liq = 0.0, float("inf")
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

            fair_probs = _lmsr_fair_probs(prices, self._liquidity_param)
            price_sum = sum(prices)

            best_edge_bps, best_idx = 0.0, -1
            deviations = []

            for i, (fp, mp) in enumerate(zip(fair_probs, prices)):
                edge_bps = (fp - mp) * 10000
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

            sandbox_sz = _sandbox_size(best_edge_bps)

            record = {
                "timestamp": now,
                "event_key": event_key[:60],
                "question": question[:80],
                "outcome_count": len(prices),
                "price_sum": round(price_sum, 4),
                "best_edge_bps": round(best_edge_bps, 1),
                "best_token": token_ids[best_idx] if best_idx >= 0 else "",
                "deviations": deviations[:8],
                "would_trade": best_edge_bps >= self._min_edge_bps,
                "sandbox_size": sandbox_sz,
            }
            self._evaluations.append(record)
            if len(self._evaluations) > self._max_evaluations:
                self._evaluations = self._evaluations[-self._max_evaluations:]

            # ---- Open positions across all 3 modes ----
            if best_edge_bps >= self._min_edge_bps and best_idx >= 0:
                tid = token_ids[best_idx]
                entry_price = prices[best_idx]
                on_cooldown = event_key in self._cooldown

                if not on_cooldown:
                    base = {
                        "token_id": tid, "event_key": event_key,
                        "question": question, "outcome_count": len(prices),
                        "entry_price": entry_price, "avg_entry": entry_price,
                        "fair_prob_at_entry": round(fair_probs[best_idx], 6),
                        "edge_bps_at_entry": round(best_edge_bps, 1),
                        "price_sum_at_entry": round(price_sum, 4),
                        "opened_at": now, "fills": 1,
                    }

                    # 1) Unit-Size: flat $3, one entry per token
                    if tid not in self._unit.positions:
                        self._unit.positions[tid] = {
                            **base, "size": 3.0,
                            "notional": round(3.0 * entry_price, 4),
                        }

                    # 2) Sandbox Notional: edge-tiered, one entry per token
                    if tid not in self._sandbox.positions and sandbox_sz > 0:
                        self._sandbox.positions[tid] = {
                            **base, "size": sandbox_sz,
                            "sandbox_band": f"${int(sandbox_sz)}",
                            "notional": round(sandbox_sz * entry_price, 4),
                        }

                    # 3) Crypto-Mirrored: $3/signal, accumulates to $25 cap
                    if tid in self._crypto.positions:
                        pos = self._crypto.positions[tid]
                        new_sz = pos["size"] + CRYPTO_SIGNAL_SIZE
                        if new_sz <= CRYPTO_MAX_POSITION:
                            old_cost = pos["size"] * pos["avg_entry"]
                            new_cost = CRYPTO_SIGNAL_SIZE * entry_price
                            pos["avg_entry"] = round((old_cost + new_cost) / new_sz, 6)
                            pos["size"] = round(new_sz, 2)
                            pos["notional"] = round(new_sz * pos["avg_entry"], 4)
                            pos["fills"] += 1
                    else:
                        self._crypto.positions[tid] = {
                            **base, "size": CRYPTO_SIGNAL_SIZE,
                            "notional": round(CRYPTO_SIGNAL_SIZE * entry_price, 4),
                        }

                    self._cooldown[event_key] = now_mono
                    self._m["hypothetical_trades"] += 1

        self._m["last_scan_time"] = now

    # ---- Resolution ----

    async def _resolution_loop(self):
        await asyncio.sleep(90)
        while self._running:
            try:
                self._resolve_all()
            except Exception as e:
                logger.error(f"[WHRRARI] Resolution error: {e}")
            await asyncio.sleep(180)

    def _resolve_all(self):
        if not self._state:
            return
        now = datetime.now(timezone.utc)
        for label, tracker in [("unit", self._unit), ("sandbox", self._sandbox), ("crypto", self._crypto)]:
            self._resolve_mode(tracker, label, now)

    def _resolve_mode(self, tracker: _ModeTracker, label: str, now: datetime):
        to_close = []
        for token_id, pos in tracker.positions.items():
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
                elif elapsed > 172800:
                    to_close.append((token_id, cp, "expired_mtm"))
            elif elapsed > 172800:
                to_close.append((token_id, 0.5, "no_data"))

        for token_id, exit_price, res_type in to_close:
            pos = tracker.positions.pop(token_id)
            entry = pos.get("avg_entry", pos["entry_price"])
            pnl = round((exit_price - entry) * pos["size"], 4)

            rec = {
                **pos,
                "exit_price": round(exit_price, 6),
                "pnl": pnl,
                "closed_at": utc_now(),
                "won": pnl > 0,
                "resolution_type": res_type,
                "is_binary_resolved": res_type.startswith("resolved"),
            }
            tracker.record_close(rec)
            logger.info(
                f"[WHRRARI] {label.upper()} resolved ({res_type}): "
                f"{pos.get('question','')[:40]}.. sz=${pos['size']} pnl=${pnl:.4f}"
            )

    # ---- Report ----

    def _mode_stats(self, tracker: _ModeTracker) -> dict:
        total = tracker.wins + tracker.losses
        now = datetime.now(timezone.utc)
        rolling = {"1h": 0.0, "3h": 0.0, "6h": 0.0}
        for t in tracker.closed:
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

        binary = [t for t in tracker.closed if t.get("is_binary_resolved")]
        binary_wins = sum(1 for t in binary if t["won"])
        open_exp = sum(p["size"] * p.get("avg_entry", p["entry_price"]) for p in tracker.positions.values())

        return {
            "pnl_total": round(tracker.pnl, 4),
            "win_rate": round(tracker.wins / total if total else 0, 4),
            "binary_win_rate": round(binary_wins / len(binary) if binary else 0, 4),
            "binary_resolved": len(binary),
            "closed_trades": total,
            "open_positions": len(tracker.positions),
            "open_exposure": round(open_exp, 2),
            "pnl_per_trade": round(tracker.pnl / total if total else 0, 4),
            "rolling_pnl": {k: round(v, 4) for k, v in rolling.items()},
            "resolved_count": len(binary),
            "unresolved_count": len(tracker.positions),
        }

    def get_report(self):
        unit_total = self._unit.wins + self._unit.losses
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
                "sandbox_bands": "$3 (300-599bps) / $8 (600-899bps) / $15 (900+bps)",
                "crypto_mirror_cap": f"${CRYPTO_SIGNAL_SIZE}/signal → ${CRYPTO_MAX_POSITION} max",
            },
            "unit_size": self._mode_stats(self._unit),
            "sandbox_notional": self._mode_stats(self._sandbox),
            "crypto_mirrored": self._mode_stats(self._crypto),
            "sample_size_sufficient": unit_total >= 15,
            "last_scan_time": self._m["last_scan_time"],
        }

    def get_evaluations(self, limit=50):
        return list(reversed(self._evaluations[-limit:]))

    def _enrich(self, positions: Dict[str, dict]) -> List[dict]:
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
        return self._enrich(self._tracker(mode).positions)

    def get_closed(self, mode="unit", limit=50):
        cl = self._tracker(mode).closed
        return list(reversed(cl[-limit:]))
