"""Shadow SOL/XRP Sniper — separate shadow tracker for non-BTC/ETH crypto markets.

Receives signals from the crypto sniper classifier (once SOL/XRP are added)
and tracks performance independently. Does NOT share positions/PnL with BTC/ETH.

100% shadow — no live orders.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List

from models import utc_now

logger = logging.getLogger(__name__)


class AltcoinShadowEngine:

    TRACKED_ASSETS = {"SOL", "XRP"}

    def __init__(self):
        self._state = None
        self._running = False

        self._positions: Dict[str, dict] = {}
        self._closed: List[dict] = []
        self._pnl = 0.0
        self._wins = 0
        self._losses = 0

        # Per-asset tracking
        self._asset_stats: Dict[str, dict] = {
            a: {"pnl": 0.0, "wins": 0, "losses": 0, "trades": 0, "signals": 0}
            for a in self.TRACKED_ASSETS
        }

        self._m = {
            "signals_received": 0,
            "positions_opened": 0,
            "sol_signals": 0,
            "xrp_signals": 0,
            "last_eval_time": None,
        }

    async def start(self, state):
        self._state = state
        self._running = True
        asyncio.create_task(self._resolution_loop())
        logger.info("[ALTCOIN] Shadow engine started — SOL/XRP tracking")

    async def stop(self):
        self._running = False

    def evaluate_signal(self, condition_id, asset, direction, spot,
                        fair_prob, yes_price, no_price, edge_bps,
                        tte_seconds, side, token_id, size, question,
                        is_tradable, window=None, **kwargs):
        """Called from crypto_sniper for SOL/XRP signals only."""
        if asset not in self.TRACKED_ASSETS:
            return

        self._m["signals_received"] += 1
        self._m["last_eval_time"] = utc_now()
        self._m[f"{asset.lower()}_signals"] = self._m.get(f"{asset.lower()}_signals", 0) + 1
        self._asset_stats.setdefault(asset, {"pnl": 0, "wins": 0, "losses": 0, "trades": 0, "signals": 0})
        self._asset_stats[asset]["signals"] += 1

        if not is_tradable:
            return

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
            "window": window,
            "entry_price": round(entry_price, 6),
            "size": size,
            "invested": round(size * entry_price, 4),
            "edge_bps": round(edge_bps, 1),
            "opened_at": utc_now(),
        }
        self._m["positions_opened"] += 1

    async def _resolution_loop(self):
        await asyncio.sleep(30)
        while self._running:
            try:
                self._check_resolution()
            except Exception as e:
                logger.error(f"[ALTCOIN] Resolution error: {e}")
            await asyncio.sleep(30)

    def _check_resolution(self):
        if not self._state:
            return

        now = utc_now()
        to_close = []

        for token_id, pos in self._positions.items():
            market = self._state.get_market(token_id)
            if not market:
                continue

            cp = market.mid_price or market.last_price
            if cp is None:
                continue

            # Binary resolution
            if cp >= 0.95 or cp <= 0.05:
                won = cp >= 0.95
                entry = pos["entry_price"]
                pnl = (1.0 - entry) * pos["size"] if won else -entry * pos["size"]
                to_close.append((token_id, won, pnl, cp))
                continue

            # Timeout (8h)
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

            asset = pos["asset"]
            closed = {
                **pos,
                "exit_price": round(exit_price, 6),
                "pnl": round(pnl, 4),
                "won": won,
                "profit_multiple": round(exit_price / pos["entry_price"], 4) if pos["entry_price"] > 0 else 0,
                "closed_at": now,
            }
            self._closed.append(closed)
            self._pnl += pnl
            if won:
                self._wins += 1
            else:
                self._losses += 1

            self._asset_stats.setdefault(asset, {"pnl": 0, "wins": 0, "losses": 0, "trades": 0, "signals": 0})
            self._asset_stats[asset]["pnl"] += pnl
            self._asset_stats[asset]["trades"] += 1
            if won:
                self._asset_stats[asset]["wins"] += 1
            else:
                self._asset_stats[asset]["losses"] += 1

    # ---- Reporting ----

    def get_report(self):
        total = self._wins + self._losses
        return {
            "status": "active" if self._m["signals_received"] > 0 else "waiting",
            "experiment": "altcoin_sniper",
            "description": "SOL/XRP shadow sniper — independent tracking from BTC/ETH",
            "performance": {
                "pnl": round(self._pnl, 4),
                "win_rate": round(self._wins / total, 4) if total else 0,
                "wins": self._wins,
                "losses": self._losses,
                "total": total,
                "open_positions": len(self._positions),
            },
            "per_asset": {
                asset: {
                    "pnl": round(stats["pnl"], 4),
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "trades": stats["trades"],
                    "signals": stats["signals"],
                    "win_rate": round(stats["wins"] / stats["trades"], 4) if stats["trades"] else 0,
                }
                for asset, stats in self._asset_stats.items()
            },
            "metrics": self._m,
            "sample_size_sufficient": total >= 10,
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
