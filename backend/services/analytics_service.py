"""Analytics computation service.

Pure computation layer — reads from StateManager trades, positions, orders.
No new DB collections. All metrics computed on demand from in-memory state.
Returns null for metrics that are not statistically meaningful yet.
"""

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


MIN_TRADES_FOR_SHARPE = 5
MIN_TRADES_FOR_STATS = 2


def _parse_ts(iso: str) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


def _date_key(iso: str) -> str:
    dt = _parse_ts(iso)
    return dt.strftime("%Y-%m-%d") if dt else "unknown"


def compute_portfolio_summary(trades, positions) -> Dict[str, Any]:
    """Compute portfolio-level metrics from trade history."""
    realized_pnl = sum(t.pnl for t in trades)
    unrealized_pnl = sum(p.unrealized_pnl for p in positions.values())
    total_pnl = realized_pnl + unrealized_pnl

    # Closing trades are those with non-zero pnl (or sell-side)
    closing_trades = [t for t in trades if t.pnl != 0]
    wins = [t for t in closing_trades if t.pnl > 0]
    losses = [t for t in closing_trades if t.pnl < 0]

    win_count = len(wins)
    loss_count = len(losses)
    total_closing = win_count + loss_count
    win_rate = (win_count / total_closing * 100) if total_closing > 0 else None

    avg_win = (sum(t.pnl for t in wins) / win_count) if win_count > 0 else None
    avg_loss = (sum(t.pnl for t in losses) / loss_count) if loss_count > 0 else None

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    expectancy = (realized_pnl / total_closing) if total_closing > 0 else None

    # Equity curve for drawdown
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cumulative += t.pnl
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    current_dd = peak - cumulative if peak > 0 else 0.0

    # Sharpe-style: mean return / std return per trade
    pnl_list = [t.pnl for t in closing_trades]
    sharpe = _compute_sharpe(pnl_list)

    # Streaks
    win_streak, loss_streak = _compute_streaks(closing_trades)

    # Total fees
    total_fees = sum(t.fees for t in trades)

    return {
        "total_pnl": round(total_pnl, 4),
        "realized_pnl": round(realized_pnl, 4),
        "unrealized_pnl": round(unrealized_pnl, 4),
        "peak_equity": round(peak, 4),
        "current_drawdown": round(current_dd, 4),
        "max_drawdown": round(max_dd, 4),
        "trade_count": len(trades),
        "closing_trade_count": total_closing,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 2) if win_rate is not None else None,
        "avg_win": round(avg_win, 4) if avg_win is not None else None,
        "avg_loss": round(avg_loss, 4) if avg_loss is not None else None,
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "expectancy": round(expectancy, 4) if expectancy is not None else None,
        "sharpe_ratio": sharpe,
        "longest_win_streak": win_streak,
        "longest_loss_streak": loss_streak,
        "total_fees": round(total_fees, 4),
        "total_volume": round(sum(t.price * t.size for t in trades), 4),
    }


def compute_strategy_metrics(trades, positions) -> Dict[str, Dict]:
    """Compute per-strategy metrics."""
    by_strat: Dict[str, list] = defaultdict(list)
    for t in trades:
        by_strat[t.strategy_id or "unknown"].append(t)

    # Per-strategy position P&L
    pos_pnl: Dict[str, float] = defaultdict(float)
    # We can't attribute positions to strategies easily, skip unrealized for now

    result = {}
    for strat_id, strat_trades in by_strat.items():
        closing = [t for t in strat_trades if t.pnl != 0]
        wins = [t for t in closing if t.pnl > 0]
        losses = [t for t in closing if t.pnl < 0]

        realized = sum(t.pnl for t in strat_trades)
        win_count = len(wins)
        loss_count = len(losses)
        total_closing = win_count + loss_count

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))

        pnl_list = [t.pnl for t in closing]
        sharpe = _compute_sharpe(pnl_list)

        # Edge: average pnl per trade (as bps of trade value)
        avg_edge_bps = None
        values = [(t.pnl / (t.price * t.size) * 10000) for t in strat_trades if t.price * t.size > 0]
        if values:
            avg_edge_bps = round(sum(values) / len(values), 1)

        result[strat_id] = {
            "strategy_id": strat_id,
            "pnl": round(realized, 4),
            "trade_count": len(strat_trades),
            "closing_trades": total_closing,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_count / total_closing * 100, 2) if total_closing > 0 else None,
            "avg_win": round(sum(t.pnl for t in wins) / win_count, 4) if win_count else None,
            "avg_loss": round(sum(t.pnl for t in losses) / loss_count, 4) if loss_count else None,
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
            "expectancy": round(realized / total_closing, 4) if total_closing > 0 else None,
            "sharpe_ratio": sharpe,
            "avg_edge_bps": avg_edge_bps,
            "total_fees": round(sum(t.fees for t in strat_trades), 4),
            "total_volume": round(sum(t.price * t.size for t in strat_trades), 4),
        }

    return result


def compute_execution_quality(orders, live_orders) -> Dict[str, Any]:
    """Compute execution quality metrics from orders and live orders."""
    orders_list = list(orders.values()) if isinstance(orders, dict) else orders

    total_orders = len(orders_list)
    filled = [o for o in orders_list if o.status.value == "filled"]
    rejected = [o for o in orders_list if o.status.value == "rejected"]
    cancelled_count = sum(1 for o in orders_list if o.status.value == "cancelled")

    fill_ratio = (len(filled) / total_orders * 100) if total_orders > 0 else None

    # Slippage from live orders
    slippage_values = [lo.get("slippage_bps", 0) for lo in live_orders if lo.get("slippage_bps") is not None and lo.get("slippage_bps") > 0]
    avg_slippage_bps = round(sum(slippage_values) / len(slippage_values), 2) if slippage_values else None

    # Partial fills from live orders
    partial_fills = [lo for lo in live_orders if lo.get("status") == "partially_filled"]
    partial_ratio = (len(partial_fills) / len(live_orders) * 100) if live_orders else None

    # Latency
    latencies = [o.latency_ms for o in filled if o.latency_ms is not None]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else None

    # Rejection reasons
    reason_counts: Dict[str, int] = defaultdict(int)
    for lo in live_orders:
        if lo.get("status") == "rejected" and lo.get("error"):
            # Simplify reason
            reason = lo["error"]
            if "slippage" in reason.lower():
                reason_counts["slippage_protection"] += 1
            elif "kill switch" in reason.lower():
                reason_counts["kill_switch"] += 1
            elif "size" in reason.lower():
                reason_counts["size_limit"] += 1
            elif "authenticated" in reason.lower():
                reason_counts["not_authenticated"] += 1
            else:
                reason_counts["other"] += 1

    return {
        "total_orders": total_orders,
        "filled_count": len(filled),
        "rejected_count": len(rejected),
        "cancelled_count": cancelled_count,
        "fill_ratio": round(fill_ratio, 2) if fill_ratio is not None else None,
        "partial_fill_count": len(partial_fills),
        "partial_fill_ratio": round(partial_ratio, 2) if partial_ratio is not None else None,
        "avg_slippage_bps": avg_slippage_bps,
        "max_slippage_bps": round(max(slippage_values), 2) if slippage_values else None,
        "avg_latency_ms": avg_latency,
        "rejection_reasons": dict(reason_counts),
        "live_orders_total": len(live_orders),
    }


def compute_timeseries(trades) -> Dict[str, Any]:
    """Compute time-based metrics: daily PnL, rolling metrics, trade frequency."""
    if not trades:
        return {"daily_pnl": [], "equity_curve": [], "drawdown_curve": [], "trade_frequency": [], "rolling_7d_pnl": None, "rolling_30d_pnl": None, "executions_by_strategy": {}}

    # Daily PnL
    daily: Dict[str, float] = defaultdict(float)
    daily_count: Dict[str, int] = defaultdict(int)
    for t in trades:
        dk = _date_key(t.timestamp)
        daily[dk] += t.pnl
        daily_count[dk] += 1

    daily_sorted = sorted(daily.keys())
    daily_pnl = [{"date": d, "pnl": round(daily[d], 4), "trades": daily_count[d]} for d in daily_sorted]

    # Equity curve (cumulative)
    cumulative = 0.0
    peak = 0.0
    equity_curve = []
    drawdown_curve = []
    for d in daily_sorted:
        cumulative += daily[d]
        peak = max(peak, cumulative)
        dd = peak - cumulative
        equity_curve.append({"date": d, "equity": round(cumulative, 4)})
        drawdown_curve.append({"date": d, "drawdown": round(dd, 4)})

    # Trade frequency
    trade_frequency = [{"date": d, "count": daily_count[d]} for d in daily_sorted]

    # Rolling
    rolling_7d = round(sum(daily[d] for d in daily_sorted[-7:]), 4) if len(daily_sorted) >= 1 else None
    rolling_30d = round(sum(daily[d] for d in daily_sorted[-30:]), 4) if len(daily_sorted) >= 7 else None

    # Opportunities vs executions by strategy per day
    strat_daily: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t in trades:
        dk = _date_key(t.timestamp)
        strat_daily[t.strategy_id or "unknown"][dk] += 1

    executions_by_strategy = {}
    for strat_id, date_counts in strat_daily.items():
        executions_by_strategy[strat_id] = [
            {"date": d, "count": date_counts.get(d, 0)} for d in daily_sorted
        ]

    return {
        "daily_pnl": daily_pnl,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "trade_frequency": trade_frequency,
        "rolling_7d_pnl": rolling_7d,
        "rolling_30d_pnl": rolling_30d,
        "executions_by_strategy": executions_by_strategy,
    }


def _compute_sharpe(pnl_list: List[float]) -> Optional[float]:
    """Simplified Sharpe: mean(returns) / std(returns). Null if too few trades."""
    if len(pnl_list) < MIN_TRADES_FOR_SHARPE:
        return None
    mean = sum(pnl_list) / len(pnl_list)
    variance = sum((x - mean) ** 2 for x in pnl_list) / len(pnl_list)
    std = math.sqrt(variance) if variance > 0 else 0
    if std == 0:
        return None
    return round(mean / std, 3)


def _compute_streaks(closing_trades) -> tuple:
    """Compute longest win streak and longest loss streak."""
    if not closing_trades:
        return 0, 0
    max_win = cur_win = 0
    max_loss = cur_loss = 0
    for t in closing_trades:
        if t.pnl > 0:
            cur_win += 1
            cur_loss = 0
            max_win = max(max_win, cur_win)
        elif t.pnl < 0:
            cur_loss += 1
            cur_win = 0
            max_loss = max(max_loss, cur_loss)
        else:
            cur_win = 0
            cur_loss = 0
    return max_win, max_loss
