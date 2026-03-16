"""Global Analytics Service — aggregates shadow-mode strategy quality metrics.

Pulls from:
  - WeatherTrader health / signal / execution state
  - ForecastAccuracyService (MongoDB forecast_accuracy)
  - LiquidityService (in-memory scores)
  - ArbScanner / CryptoSniper health
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GlobalAnalyticsService:
    def __init__(
        self,
        state,
        weather_trader=None,
        arb_scanner=None,
        crypto_sniper=None,
        forecast_accuracy_service=None,
    ):
        self._state = state
        self._weather = weather_trader
        self._arb = arb_scanner
        self._sniper = crypto_sniper
        self._accuracy_svc = forecast_accuracy_service

    # ---- Strategy Performance ----

    def get_strategy_performance(self) -> dict:
        by_strategy = {}

        # Weather Trader
        if self._weather:
            wh = self._weather.get_health()
            signals = self._weather.get_signals(limit=500)
            completed = self._weather.get_completed_executions(limit=500)
            active = self._weather.get_active_executions()

            tradable = [s for s in signals if s.get("is_tradable")]
            filled = [e for e in completed if e.get("status") == "filled"]
            rejected_exec = [e for e in completed if e.get("status") == "rejected"]

            edges = [s["edge_bps"] for s in tradable if s.get("edge_bps")]
            fill_prices = [e.get("entry_price", 0) for e in filled if e.get("entry_price")]

            by_strategy["weather_trader"] = {
                "total_signals": wh.get("signals_generated", 0),
                "total_executed": wh.get("signals_executed", 0),
                "total_filled": wh.get("signals_filled", 0),
                "active_executions": len(active),
                "avg_expected_edge_bps": round(sum(edges) / len(edges), 1) if edges else 0,
                "tradable_signals": len(tradable),
                "rejection_reasons": wh.get("rejection_reasons", {}),
                "total_scans": wh.get("total_scans", 0),
                "classified_markets": wh.get("classified_markets", 0),
            }

        # Arb Scanner
        if self._arb:
            ah = self._arb.get_health()
            by_strategy["arb_scanner"] = {
                "total_signals": ah.get("opportunities_evaluated", 0),
                "total_executed": ah.get("executions_submitted", 0),
                "total_filled": ah.get("executions_completed", 0),
                "active_executions": len(self._arb.get_active_executions()),
            }

        # Crypto Sniper
        if self._sniper:
            sh = self._sniper.get_health()
            by_strategy["crypto_sniper"] = {
                "total_signals": sh.get("signals_evaluated", 0),
                "total_executed": sh.get("signals_executed", 0),
                "total_filled": sh.get("signals_filled", 0),
                "active_executions": len(self._sniper.get_active_executions()),
            }

        # Aggregate trades from state
        trades = self._state.trades
        total_pnl = sum(t.pnl for t in trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        total_signals = sum(s.get("total_signals", 0) for s in by_strategy.values())
        total_executed = sum(s.get("total_executed", 0) for s in by_strategy.values())
        total_filled = sum(s.get("total_filled", 0) for s in by_strategy.values())

        return {
            "total_signals": total_signals,
            "total_executions": total_executed,
            "total_filled": total_filled,
            "total_trades": len(trades),
            "realized_pnl": round(total_pnl, 4),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
            "avg_win": round(sum(t.pnl for t in wins) / len(wins), 4) if wins else 0,
            "avg_loss": round(sum(t.pnl for t in losses) / len(losses), 4) if losses else 0,
            "by_strategy": by_strategy,
        }

    # ---- Forecast Quality ----

    async def get_forecast_quality(self) -> dict:
        if not self._accuracy_svc:
            return {
                "global_mae_f": None,
                "global_bias_f": None,
                "total_forecasts": 0,
                "resolved_forecasts": 0,
                "error_distribution": [],
                "station_metrics": {},
            }

        cal_health = await self._accuracy_svc.get_calibration_health()
        station_summary = cal_health.get("station_summaries", {})

        # Build error distribution histogram from resolved forecasts
        history = await self._accuracy_svc.get_history(limit=500)
        resolved = [r for r in history if r.get("resolved")]

        error_bins = defaultdict(int)
        errors_list = []
        for r in resolved:
            err = r.get("forecast_error_f")
            if err is not None:
                errors_list.append(err)
                # Bin into 1F buckets
                bucket = int(round(err))
                error_bins[bucket] += 1

        # Convert to sorted histogram
        error_distribution = []
        if error_bins:
            min_b = min(error_bins.keys())
            max_b = max(error_bins.keys())
            for b in range(min_b, max_b + 1):
                error_distribution.append({
                    "error_f": b,
                    "count": error_bins.get(b, 0),
                })

        return {
            "global_mae_f": cal_health.get("global_mae_f"),
            "global_bias_f": cal_health.get("global_bias_f"),
            "total_forecasts": cal_health.get("total_records", 0),
            "resolved_forecasts": cal_health.get("resolved_records", 0),
            "pending_resolution": cal_health.get("pending_resolution", 0),
            "calibration_status": cal_health.get("calibration_status", "no_data"),
            "error_distribution": error_distribution,
            "station_metrics": station_summary,
        }

    # ---- Liquidity Insights ----

    def get_liquidity_insights(self) -> dict:
        rejection_breakdown = {}
        liquidity_stats = {
            "avg_traded_liquidity_score": 0,
            "min_traded_liquidity_score": 0,
            "max_traded_liquidity_score": 0,
            "markets_with_scores": 0,
        }

        if self._weather:
            wh = self._weather.get_health()
            rejection_breakdown = wh.get("rejection_reasons", {})

            # Get liquidity scores from cached data
            scores = list(self._weather._liquidity_scores.values())
            if scores:
                liquidity_stats["avg_traded_liquidity_score"] = round(sum(scores) / len(scores), 1)
                liquidity_stats["min_traded_liquidity_score"] = round(min(scores), 1)
                liquidity_stats["max_traded_liquidity_score"] = round(max(scores), 1)
                liquidity_stats["markets_with_scores"] = len(scores)

        total_rejections = sum(rejection_breakdown.values())

        # Also gather arb/sniper rejections
        arb_rejections = {}
        sniper_rejections = {}
        if self._arb:
            ah = self._arb.get_health()
            arb_rejections = ah.get("rejection_breakdown", {})
        if self._sniper:
            sh = self._sniper.get_health()
            sniper_rejections = sh.get("rejection_reasons", {})

        return {
            **liquidity_stats,
            "weather_rejections": rejection_breakdown,
            "arb_rejections": arb_rejections,
            "sniper_rejections": sniper_rejections,
            "total_weather_rejections": total_rejections,
        }

    # ---- Timeseries ----

    def get_signal_timeseries(self) -> dict:
        """Build signal frequency and cumulative PnL timeseries from trade data."""
        trades = self._state.trades
        if not trades:
            return {"cumulative_pnl": [], "signal_frequency": []}

        # Build daily buckets
        daily_pnl = defaultdict(float)
        daily_count = defaultdict(int)
        daily_by_strategy = defaultdict(lambda: defaultdict(int))

        for t in trades:
            ts = t.timestamp
            if isinstance(ts, str):
                day = ts[:10]
            else:
                day = ts.strftime("%Y-%m-%d") if hasattr(ts, 'strftime') else str(ts)[:10]
            daily_pnl[day] += t.pnl
            daily_count[day] += 1
            daily_by_strategy[day][t.strategy_id] += 1

        # Build cumulative PnL
        days = sorted(daily_pnl.keys())
        cumulative = 0
        cum_pnl_series = []
        for d in days:
            cumulative += daily_pnl[d]
            cum_pnl_series.append({
                "date": d,
                "daily_pnl": round(daily_pnl[d], 4),
                "cumulative_pnl": round(cumulative, 4),
            })

        # Signal frequency
        freq_series = []
        for d in days:
            entry = {"date": d, "total": daily_count[d]}
            for sid, cnt in daily_by_strategy[d].items():
                entry[sid] = cnt
            freq_series.append(entry)

        return {
            "cumulative_pnl": cum_pnl_series,
            "signal_frequency": freq_series,
        }

    # ---- Full Report ----

    async def get_full_report(self) -> dict:
        perf = self.get_strategy_performance()
        forecast = await self.get_forecast_quality()
        liquidity = self.get_liquidity_insights()
        timeseries = self.get_signal_timeseries()

        return {
            "strategy_performance": perf,
            "forecast_quality": forecast,
            "liquidity_insights": liquidity,
            "timeseries": timeseries,
        }
