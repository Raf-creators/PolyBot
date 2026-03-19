"""Rolling-window PnL calculator.

Computes PnL/hour over 1h, 3h, and 6h windows using actual trade timestamps.
No uptime-based calculations — purely trade-data driven.
"""

from datetime import datetime, timezone, timedelta
from typing import List

# Standard windows
WINDOWS = {"1h": 1, "3h": 3, "6h": 6}

# Strategy bucket classifier (duplicated from risk.py to avoid circular import)
_CRYPTO_KW = ("bitcoin", "btc", "ethereum", "eth", "up or down")
_WEATHER_KW = ("temperature", "highest temp", "weather", "°f", "°c")


def _bucket(strategy_id: str, question: str = "") -> str:
    sid = (strategy_id or "").lower()
    if "crypto" in sid or "sniper" in sid:
        return "crypto"
    if "weather" in sid:
        return "weather"
    if "arb" in sid:
        return "arb"
    # Fallback: classify by question text
    ql = (question or "").lower()
    if any(kw in ql for kw in _CRYPTO_KW):
        return "crypto"
    if any(kw in ql for kw in _WEATHER_KW):
        return "weather"
    return "other"


def _parse_ts(ts_str: str) -> datetime:
    """Parse an ISO timestamp string to a timezone-aware datetime."""
    if not ts_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def compute_rolling_pnl(trades: List, windows: dict = None) -> dict:
    """Compute PnL/hour over rolling time windows from trade timestamps.

    Args:
        trades: List of trade objects (must have .timestamp, .pnl, .strategy_id)
        windows: Dict of {label: hours}, defaults to {"1h": 1, "3h": 3, "6h": 6}

    Returns:
        {
            "total": {"1h": X, "3h": Y, "6h": Z},
            "crypto": {"1h": X, "3h": Y, "6h": Z},
            "weather": {"1h": X, "3h": Y, "6h": Z},
            "arb": {"1h": X, "3h": Y, "6h": Z},
        }
    """
    if windows is None:
        windows = WINDOWS

    now = datetime.now(timezone.utc)
    result = {}
    buckets = ["total", "crypto", "weather", "arb"]

    for label, hours in windows.items():
        cutoff = now - timedelta(hours=hours)
        pnl_by_bucket = {b: 0.0 for b in buckets}
        trade_count_by_bucket = {b: 0 for b in buckets}

        for t in trades:
            ts = _parse_ts(getattr(t, "timestamp", "") or "")
            if ts < cutoff:
                continue

            pnl = getattr(t, "pnl", 0) or 0
            sid = getattr(t, "strategy_id", "") or ""
            question = getattr(t, "market_question", "") or ""
            bucket = _bucket(sid, question)

            pnl_by_bucket["total"] += pnl
            trade_count_by_bucket["total"] += 1
            if bucket in pnl_by_bucket:
                pnl_by_bucket[bucket] += pnl
                trade_count_by_bucket[bucket] += 1

        for b in buckets:
            if b not in result:
                result[b] = {}
            result[b][label] = {
                "pnl": round(pnl_by_bucket[b], 4),
                "pnl_per_h": round(pnl_by_bucket[b] / hours, 2),
                "trades": trade_count_by_bucket[b],
                "trades_per_h": round(trade_count_by_bucket[b] / hours, 1),
            }

    return result


def format_rolling_pnl_text(rolling: dict) -> str:
    """Format rolling PnL data for Telegram display."""
    lines = []

    for bucket_label, display_name in [("crypto", "CRYPTO"), ("weather", "WEATHER"), ("arb", "ARB")]:
        data = rolling.get(bucket_label, {})
        if not data:
            continue
        has_activity = any(d.get("trades", 0) > 0 for d in data.values())
        if not has_activity and bucket_label != "crypto":
            continue
        vals = []
        for window in ["1h", "3h", "6h"]:
            d = data.get(window, {})
            vals.append(f"${d.get('pnl_per_h', 0):.2f}/h ({d.get('trades', 0)}t)")
        lines.append(f"<b>{display_name}:</b>")
        lines.append(f"  1h: {vals[0]}")
        lines.append(f"  3h: {vals[1]}")
        lines.append(f"  6h: {vals[2]}")

    # Total
    total = rolling.get("total", {})
    vals = []
    for window in ["1h", "3h", "6h"]:
        d = total.get(window, {})
        vals.append(f"${d.get('pnl_per_h', 0):.2f}/h ({d.get('trades', 0)}t)")
    lines.append("<b>TOTAL:</b>")
    lines.append(f"  1h: {vals[0]}")
    lines.append(f"  3h: {vals[1]}")
    lines.append(f"  6h: {vals[2]}")

    return "\n".join(lines)
