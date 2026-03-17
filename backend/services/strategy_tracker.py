"""Strategy-level performance tracking and signal rejection diagnostics."""
import logging
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StrategyTracker:
    """Tracks per-strategy PnL, win rate, signal stats, and rejection reasons."""

    def __init__(self):
        self._perf = defaultdict(lambda: {
            "total_pnl": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "trade_count": 0,
            "total_edge": 0.0,
        })
        self._signals = defaultdict(lambda: {
            "generated": 0,
            "executed": 0,
            "rejected": 0,
            "rejection_reasons": defaultdict(int),
        })
        # Watchdog timestamps
        self._last_market_discovered = None
        self._last_trade_opened = None
        self._last_trade_closed = None

    def record_close(self, strategy_id: str, pnl: float, edge: float = 0.0, is_live: bool = True):
        p = self._perf[strategy_id]
        p["trade_count"] += 1
        p["total_pnl"] += pnl
        p["total_edge"] += edge
        if pnl > 0:
            p["win_count"] += 1
        elif pnl < 0:
            p["loss_count"] += 1
        if is_live:
            self._last_trade_closed = datetime.now(timezone.utc).isoformat()

    def record_signal(self, strategy_id: str, executed: bool, rejection_reason: str = ""):
        s = self._signals[strategy_id]
        s["generated"] += 1
        if executed:
            s["executed"] += 1
            self._last_trade_opened = datetime.now(timezone.utc).isoformat()
        else:
            s["rejected"] += 1
            if rejection_reason:
                # Normalize common reasons
                key = rejection_reason.split(":")[0].strip() if ":" in rejection_reason else rejection_reason
                s["rejection_reasons"][key] += 1

    def record_discovery(self):
        self._last_market_discovered = datetime.now(timezone.utc).isoformat()

    def get_performance(self) -> dict:
        out = {}
        for sid, p in self._perf.items():
            closed = p["win_count"] + p["loss_count"]
            out[sid] = {
                "total_pnl": round(p["total_pnl"], 4),
                "win_count": p["win_count"],
                "loss_count": p["loss_count"],
                "trade_count": p["trade_count"],
                "win_rate": round(p["win_count"] / closed * 100, 1) if closed > 0 else 0.0,
                "avg_edge": round(p["total_edge"] / p["trade_count"], 2) if p["trade_count"] > 0 else 0.0,
            }
        return out

    def get_signals(self) -> dict:
        out = {}
        for sid, s in self._signals.items():
            out[sid] = {
                "generated": s["generated"],
                "executed": s["executed"],
                "rejected": s["rejected"],
                "rejection_reasons": dict(s["rejection_reasons"]),
            }
        return out

    def get_watchdog(self) -> dict:
        return {
            "last_market_discovered": self._last_market_discovered,
            "last_trade_opened": self._last_trade_opened,
            "last_trade_closed": self._last_trade_closed,
        }

    def snapshot(self) -> dict:
        return {
            "performance": self.get_performance(),
            "signals": self.get_signals(),
            "watchdog": self.get_watchdog(),
        }
