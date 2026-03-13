"""Demo data generator for Polymarket Edge OS.

Generates realistic 7-day trading history for dashboard preview.
Pure in-memory — no MongoDB writes, no strategy mutations.
All data is regenerated fresh on each call to generate().

SAFETY: This module has ZERO imports from engine/, strategies/, or state.
It only produces plain dicts matching the API response shapes.
"""

import math
import random
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

# ---- Seed / Config ----

STARTING_BALANCE = 4000.0
TARGET_BALANCE = 14746.38
DAYS = 7
STRATEGIES = ["arb_scanner", "crypto_sniper", "weather_trader"]

# Strategy behavior profiles
STRATEGY_PROFILES = {
    "arb_scanner": {
        "name": "Arb Scanner",
        "trades_per_day": (12, 22),  # frequent, small
        "avg_edge_bps": 180,
        "edge_std": 90,
        "avg_size": 8.0,
        "size_std": 4.0,
        "win_rate": 0.72,
        "avg_win_mult": 1.0,
        "avg_loss_mult": 0.7,
    },
    "crypto_sniper": {
        "name": "Crypto Sniper",
        "trades_per_day": (5, 12),
        "avg_edge_bps": 350,
        "edge_std": 200,
        "avg_size": 15.0,
        "size_std": 8.0,
        "win_rate": 0.63,
        "avg_win_mult": 1.3,
        "avg_loss_mult": 0.9,
    },
    "weather_trader": {
        "name": "Weather Trader",
        "trades_per_day": (2, 5),
        "avg_edge_bps": 600,
        "edge_std": 300,
        "avg_size": 20.0,
        "size_std": 10.0,
        "win_rate": 0.68,
        "avg_win_mult": 1.5,
        "avg_loss_mult": 1.1,
    },
}

# Weather cities for demo
WEATHER_CITIES = [
    ("KLGA", "New York City"),
    ("KORD", "Chicago"),
    ("KATL", "Atlanta"),
    ("KDFW", "Dallas"),
    ("KMIA", "Miami"),
]

CRYPTO_ASSETS = ["BTC", "ETH"]
ARB_QUESTIONS = [
    "Will Bitcoin exceed $100,000 by end of March 2026?",
    "Will Ethereum exceed $4,000 by April 2026?",
    "Will the Fed cut rates in Q2 2026?",
    "Will US GDP growth exceed 3% in Q1 2026?",
    "Will gold hit $3,000/oz by June 2026?",
    "Will S&P 500 close above 6,000 by March 31?",
    "Will BTC dominance exceed 55% by April?",
    "Will inflation drop below 2.5% in March CPI?",
]


class DemoDataService:
    """Generates and caches a complete set of demo data."""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._seed: int = 42
        self.generate()

    def generate(self, seed: int = None):
        """Generate a fresh set of demo data."""
        self._seed = seed or random.randint(1, 999999)
        rng = random.Random(self._seed)
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=DAYS)

        trades = self._gen_trades(rng, start, now)
        positions = self._gen_positions(rng, now, trades)
        orders = self._gen_orders(rng, trades)
        pnl_history = self._build_pnl_history(trades)
        ticker = self._gen_ticker(rng, trades, now)
        analytics_summary = self._build_analytics_summary(trades, positions)
        analytics_strategies = self._build_strategy_metrics(trades, positions)
        analytics_execution = self._build_execution_quality(orders)
        analytics_timeseries = self._build_timeseries(trades)
        arb_data = self._gen_arb_data(rng, now, trades)
        sniper_data = self._gen_sniper_data(rng, now, trades)
        weather_data = self._gen_weather_data(rng, now, trades)

        self._data = {
            "trades": trades,
            "positions": positions,
            "orders": orders,
            "pnl_history": pnl_history,
            "ticker": ticker,
            "analytics_summary": analytics_summary,
            "analytics_strategies": analytics_strategies,
            "analytics_execution": analytics_execution,
            "analytics_timeseries": analytics_timeseries,
            "arb": arb_data,
            "sniper": sniper_data,
            "weather": weather_data,
            "config": self._gen_config(),
            "status": self._gen_status(now, positions, trades),
            "wallet": {
                "mode": "paper",
                "authenticated": False,
                "balance_usdc": round(TARGET_BALANCE, 2),
                "live_ready": False,
                "warnings": [],
            },
            "markets": self._gen_markets(rng, now),
            "feed_health": self._gen_feed_health(now),
            "seed": self._seed,
            "generated_at": now.isoformat(),
        }

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    @property
    def data(self) -> Dict:
        return self._data

    # ---- Trade Generation ----

    def _gen_trades(self, rng: random.Random, start: datetime, end: datetime) -> List[Dict]:
        trades = []
        total_target_pnl = TARGET_BALANCE - STARTING_BALANCE  # ~$10,746

        # Generate all trades first with natural PnLs
        for day_idx in range(DAYS):
            day_start = start + timedelta(days=day_idx)
            for strat_id, profile in STRATEGY_PROFILES.items():
                n = rng.randint(*profile["trades_per_day"])
                for _ in range(n):
                    t = self._gen_single_trade(rng, strat_id, profile, day_start, day_idx)
                    offset_hours = rng.uniform(0.5, 23.5)
                    t["timestamp"] = (day_start + timedelta(hours=offset_hours)).isoformat()
                    trades.append(t)

        # Sort by timestamp
        trades.sort(key=lambda t: t["timestamp"])

        # Scale all PnLs globally to hit the target, preserving win/loss direction
        raw_total = sum(t["pnl"] for t in trades)
        if abs(raw_total) > 0.01:
            global_scale = total_target_pnl / raw_total
            for t in trades:
                t["pnl"] = round(t["pnl"] * global_scale, 4)
                t["fees"] = round(t["fees"] * abs(global_scale), 4)
                t["size"] = round(t["size"] * abs(global_scale) ** 0.5, 2)

        # Now redistribute to create realistic equity curve shape (drawdowns)
        # Group trades by day
        day_trades = {}
        for t in trades:
            day = t["timestamp"][:10]
            day_trades.setdefault(day, []).append(t)

        # Generate target daily PnL curve with drawdowns
        daily_targets = self._gen_equity_curve(rng, len(day_trades), total_target_pnl)
        sorted_days = sorted(day_trades.keys())

        for i, day in enumerate(sorted_days):
            dt = day_trades[day]
            day_raw = sum(t["pnl"] for t in dt)
            if abs(day_raw) > 0.01 and i < len(daily_targets):
                day_scale = daily_targets[i] / day_raw
                day_scale = max(-2.0, min(4.0, day_scale))
                for t in dt:
                    t["pnl"] = round(t["pnl"] * day_scale, 4)

        return trades

    def _gen_equity_curve(self, rng: random.Random, days: int, target: float) -> List[float]:
        """Generate a realistic equity curve with drawdowns."""
        # Raw random walk biased upward
        raw = []
        cumulative = 0.0
        for i in range(days):
            # Bias toward positive with occasional drawdown days
            if rng.random() < 0.25:  # 25% chance of drawdown day
                daily = rng.uniform(-0.04, -0.005) * target
            else:
                daily = rng.uniform(0.01, 0.25) * target / days * 2
            raw.append(daily)
            cumulative += daily

        # Scale to hit target
        current_total = sum(raw)
        if abs(current_total) > 0.01:
            scale = target / current_total
            raw = [r * scale for r in raw]

        return raw

    def _gen_single_trade(self, rng, strat_id, profile, day_start, day_idx):
        is_win = rng.random() < profile["win_rate"]
        edge_bps = max(50, rng.gauss(profile["avg_edge_bps"], profile["edge_std"]))
        size = max(1.0, rng.gauss(profile["avg_size"], profile["size_std"]))
        price = round(rng.uniform(0.15, 0.85), 4)
        fees = round(price * size * 0.002, 4)

        if is_win:
            pnl = round(size * (edge_bps / 10000) * profile["avg_win_mult"] * rng.uniform(0.5, 2.0), 4)
        else:
            pnl = round(-size * (edge_bps / 10000) * profile["avg_loss_mult"] * rng.uniform(0.3, 1.5), 4)

        # Question generation
        if strat_id == "arb_scanner":
            question = rng.choice(ARB_QUESTIONS)
            outcome = rng.choice(["Yes", "No"])
        elif strat_id == "crypto_sniper":
            asset = rng.choice(CRYPTO_ASSETS)
            strike = rng.randint(90000, 110000) if asset == "BTC" else rng.randint(3000, 5000)
            question = f"Will {asset} be above ${strike:,} at next checkpoint?"
            outcome = "Yes" if is_win else "No"
        else:
            city = rng.choice(WEATHER_CITIES)
            temp = rng.randint(30, 95)
            question = f"Highest temperature in {city[1]} — {temp}-{temp+2}°F bucket?"
            outcome = "Yes"

        return {
            "order_id": str(uuid.uuid4()),
            "token_id": f"demo-{uuid.uuid4().hex[:12]}",
            "market_question": question,
            "outcome": outcome,
            "side": rng.choice(["buy", "sell"]),
            "price": price,
            "size": round(size, 2),
            "fees": fees,
            "pnl": pnl,
            "strategy_id": strat_id,
            "signal_reason": f"demo_{strat_id}",
            "timestamp": "",  # filled later
        }

    # ---- Position Generation ----

    def _gen_positions(self, rng, now, trades) -> List[Dict]:
        positions = []
        num_positions = rng.randint(9, 14)

        for i in range(num_positions):
            strat_id = rng.choice(STRATEGIES)
            profile = STRATEGY_PROFILES[strat_id]
            size = round(max(2.0, rng.gauss(profile["avg_size"], profile["size_std"] / 2)), 2)
            avg_cost = round(rng.uniform(0.20, 0.75), 4)
            current = round(avg_cost + rng.uniform(-0.15, 0.20), 4)
            current = max(0.01, min(0.99, current))
            unrealized = round((current - avg_cost) * size, 4)

            entry_time = now - timedelta(hours=rng.uniform(1, 120))

            if strat_id == "arb_scanner":
                question = rng.choice(ARB_QUESTIONS)
            elif strat_id == "crypto_sniper":
                asset = rng.choice(CRYPTO_ASSETS)
                question = f"Will {asset} exceed ${rng.randint(90000, 110000):,}?"
            else:
                city = rng.choice(WEATHER_CITIES)
                question = f"Temperature in {city[1]} — bucket market"

            positions.append({
                "token_id": f"demo-pos-{uuid.uuid4().hex[:8]}",
                "condition_id": f"demo-cond-{uuid.uuid4().hex[:8]}",
                "question": question,
                "outcome": rng.choice(["Yes", "No"]),
                "side": "buy",
                "size": size,
                "avg_cost": avg_cost,
                "current_price": current,
                "unrealized_pnl": unrealized,
                "strategy_id": strat_id,
                "opened_at": entry_time.isoformat(),
                "updated_at": now.isoformat(),
            })

        return positions

    # ---- Order Generation ----

    def _gen_orders(self, rng, trades) -> List[Dict]:
        orders = []
        statuses = ["filled"] * 7 + ["rejected"] * 2 + ["cancelled"]
        for i, t in enumerate(trades[-80:]):
            status = rng.choice(statuses)
            orders.append({
                "id": f"demo-ord-{uuid.uuid4().hex[:8]}",
                "token_id": t["token_id"],
                "side": t["side"],
                "price": t["price"],
                "size": t["size"],
                "status": status,
                "strategy_id": t["strategy_id"],
                "latency_ms": round(rng.uniform(8, 85), 2) if status == "filled" else None,
                "created_at": t["timestamp"],
                "fill_price": round(t["price"] + rng.uniform(-0.005, 0.005), 4) if status == "filled" else None,
                "slippage_bps": round(rng.uniform(-5, 15), 1) if status == "filled" else None,
            })
        return orders

    # ---- PnL History ----

    def _build_pnl_history(self, trades) -> Dict:
        points = []
        cumulative = STARTING_BALANCE
        peak = cumulative
        trough = cumulative

        for t in trades:
            cumulative += t["pnl"]
            peak = max(peak, cumulative)
            trough = min(trough, cumulative)
            points.append({
                "timestamp": t["timestamp"],
                "cumulative_pnl": round(cumulative - STARTING_BALANCE, 4),
                "trade_pnl": t["pnl"],
                "strategy": t["strategy_id"],
            })

        current = cumulative - STARTING_BALANCE
        return {
            "points": points,
            "current_pnl": round(current, 4),
            "peak_pnl": round(peak - STARTING_BALANCE, 4),
            "trough_pnl": round(trough - STARTING_BALANCE, 4),
            "max_drawdown": round(peak - trough, 4),
            "total_trades": len(trades),
        }

    # ---- Ticker ----

    def _gen_ticker(self, rng, trades, now) -> List[Dict]:
        recent = trades[-30:]
        items = []
        for t in reversed(recent):
            strat_map = {"arb_scanner": "ARB", "crypto_sniper": "SNIPER", "weather_trader": "WEATHER"}
            asset = "BTC" if "BTC" in t.get("market_question", "") else (
                "ETH" if "ETH" in t.get("market_question", "") else (
                    "TEMP" if "temperature" in t.get("market_question", "").lower() else "MKT"
                )
            )
            items.append({
                "id": t["order_id"],
                "strategy": strat_map.get(t["strategy_id"], "MKT"),
                "asset": asset,
                "side": t["side"].upper(),
                "size": t["size"],
                "price": t["price"],
                "edge_bps": round(abs(t["pnl"]) / max(t["size"], 0.01) * 10000, 0),
                "timestamp": t["timestamp"],
            })
        return items

    # ---- Analytics Summary ----

    def _build_analytics_summary(self, trades, positions) -> Dict:
        realized = sum(t["pnl"] for t in trades)
        unrealized = sum(p["unrealized_pnl"] for p in positions)
        total = realized + unrealized

        closing = [t for t in trades if t["pnl"] != 0]
        wins = [t for t in closing if t["pnl"] > 0]
        losses = [t for t in closing if t["pnl"] < 0]

        win_count = len(wins)
        loss_count = len(losses)
        total_closing = win_count + loss_count
        win_rate = (win_count / total_closing * 100) if total_closing > 0 else 0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

        avg_win = (gross_profit / win_count) if win_count else 0
        avg_loss = (gross_loss / loss_count) if loss_count else 0
        expectancy = (realized / total_closing) if total_closing else 0

        fees = sum(t["fees"] for t in trades)
        volume = sum(t["size"] * t["price"] for t in trades)

        # Drawdown from equity curve
        cumul = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            cumul += t["pnl"]
            peak = max(peak, cumul)
            dd = peak - cumul
            max_dd = max(max_dd, dd)

        # Streaks
        streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        for t in closing:
            if t["pnl"] > 0:
                streak = streak + 1 if streak > 0 else 1
                max_win_streak = max(max_win_streak, streak)
            else:
                streak = streak - 1 if streak < 0 else -1
                max_loss_streak = max(max_loss_streak, abs(streak))

        # Sharpe (approximate daily)
        daily_pnls = {}
        for t in trades:
            day = t["timestamp"][:10]
            daily_pnls[day] = daily_pnls.get(day, 0) + t["pnl"]
        pnl_values = list(daily_pnls.values())
        if len(pnl_values) >= 3:
            mean_d = sum(pnl_values) / len(pnl_values)
            var_d = sum((p - mean_d) ** 2 for p in pnl_values) / len(pnl_values)
            std_d = math.sqrt(var_d) if var_d > 0 else 0.01
            sharpe = round((mean_d / std_d) * math.sqrt(252), 2)
        else:
            sharpe = None

        return {
            "total_pnl": round(total, 2),
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unrealized, 2),
            "trade_count": len(trades),
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(expectancy, 4),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd / STARTING_BALANCE * 100, 2) if STARTING_BALANCE else 0,
            "sharpe_ratio": sharpe,
            "total_fees": round(fees, 2),
            "total_volume": round(volume, 2),
            "best_trade": round(max((t["pnl"] for t in trades), default=0), 4),
            "worst_trade": round(min((t["pnl"] for t in trades), default=0), 4),
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
        }

    # ---- Strategy Metrics ----

    def _build_strategy_metrics(self, trades, positions) -> Dict:
        result = {}
        for strat_id in STRATEGIES:
            strat_trades = [t for t in trades if t["strategy_id"] == strat_id]
            if not strat_trades:
                continue

            realized = sum(t["pnl"] for t in strat_trades)
            closing = [t for t in strat_trades if t["pnl"] != 0]
            wins = [t for t in closing if t["pnl"] > 0]
            losses = [t for t in closing if t["pnl"] < 0]

            result[strat_id] = {
                "trade_count": len(strat_trades),
                "realized_pnl": round(realized, 2),
                "win_count": len(wins),
                "loss_count": len(losses),
                "win_rate": round(len(wins) / len(closing) * 100, 1) if closing else 0,
                "avg_edge_bps": round(sum(abs(t["pnl"]) / max(t["size"], 0.01) * 10000 for t in strat_trades) / len(strat_trades), 0),
                "profit_factor": round(sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in losses)), 2) if losses else 0,
                "total_volume": round(sum(t["size"] * t["price"] for t in strat_trades), 2),
            }
        return result

    # ---- Execution Quality ----

    def _build_execution_quality(self, orders) -> Dict:
        filled = [o for o in orders if o["status"] == "filled"]
        rejected = [o for o in orders if o["status"] == "rejected"]
        cancelled = [o for o in orders if o["status"] == "cancelled"]

        latencies = [o["latency_ms"] for o in filled if o.get("latency_ms")]
        slippages = [o["slippage_bps"] for o in filled if o.get("slippage_bps") is not None]

        return {
            "total_orders": len(orders),
            "filled": len(filled),
            "rejected": len(rejected),
            "cancelled": len(cancelled),
            "fill_rate": round(len(filled) / len(orders) * 100, 1) if orders else 0,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 1),
            "avg_slippage_bps": round(sum(slippages) / len(slippages), 1) if slippages else 0,
            "rejection_reasons": {
                "insufficient_liquidity": len(rejected) // 3,
                "edge_below_threshold": len(rejected) - len(rejected) // 3,
            },
            "partial_fills": 0,
        }

    # ---- Timeseries ----

    def _build_timeseries(self, trades) -> Dict:
        daily = {}
        for t in trades:
            day = t["timestamp"][:10]
            if day not in daily:
                daily[day] = {"pnl": 0.0, "trades": 0, "volume": 0.0}
            daily[day]["pnl"] += t["pnl"]
            daily[day]["trades"] += 1
            daily[day]["volume"] += t["size"] * t["price"]

        sorted_days = sorted(daily.keys())
        daily_pnl = []
        equity = [STARTING_BALANCE]
        drawdown_curve = []
        trade_frequency = []
        rolling_7d = []
        rolling_30d = []
        executions_by_strategy = []

        cumulative = STARTING_BALANCE
        peak = STARTING_BALANCE

        for i, day in enumerate(sorted_days):
            d = daily[day]
            cumulative += d["pnl"]
            peak = max(peak, cumulative)
            dd = (peak - cumulative) / peak * 100 if peak > 0 else 0

            daily_pnl.append({"date": day, "pnl": round(d["pnl"], 2)})
            equity.append(round(cumulative, 2))
            drawdown_curve.append({"date": day, "drawdown": round(-dd, 2)})
            trade_frequency.append({"date": day, "count": d["trades"]})

            # Rolling PnL
            window_7 = sum(daily.get(sorted_days[max(0, j)], {}).get("pnl", 0)
                          for j in range(max(0, i - 6), i + 1))
            rolling_7d.append({"date": day, "pnl": round(window_7, 2)})
            rolling_30d.append({"date": day, "pnl": round(window_7, 2)})  # same for 7-day demo

            # Per-strategy count
            day_trades = [t for t in trades if t["timestamp"][:10] == day]
            strat_counts = {}
            for t in day_trades:
                strat_counts[t["strategy_id"]] = strat_counts.get(t["strategy_id"], 0) + 1
            executions_by_strategy.append({"date": day, **strat_counts})

        equity_curve = [{"date": sorted_days[i] if i < len(sorted_days) else "", "equity": e}
                        for i, e in enumerate(equity[1:])]

        return {
            "daily_pnl": daily_pnl,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "trade_frequency": trade_frequency,
            "rolling_7d_pnl": rolling_7d,
            "rolling_30d_pnl": rolling_30d,
            "executions_by_strategy": executions_by_strategy,
        }

    # ---- Arb Strategy Data ----

    def _gen_arb_data(self, rng, now, trades) -> Dict:
        arb_trades = [t for t in trades if t["strategy_id"] == "arb_scanner"]
        recent = arb_trades[-20:]

        tradable = []
        rejected = []
        for i, t in enumerate(recent):
            sig = {
                "id": str(uuid.uuid4()),
                "condition_id": f"demo-arb-{uuid.uuid4().hex[:8]}",
                "question": t["market_question"],
                "yes_token_id": f"demo-yes-{uuid.uuid4().hex[:8]}",
                "no_token_id": f"demo-no-{uuid.uuid4().hex[:8]}",
                "yes_price": round(rng.uniform(0.3, 0.7), 4),
                "no_price": round(rng.uniform(0.3, 0.7), 4),
                "gross_edge_bps": round(rng.uniform(100, 500)),
                "net_edge_bps": round(rng.uniform(50, 400)),
                "is_tradable": i < 8,
                "rejection_reason": None if i < 8 else rng.choice(["edge_below_min", "low_liquidity", "stale_data"]),
                "detected_at": (now - timedelta(minutes=rng.randint(1, 120))).isoformat(),
            }
            if sig["is_tradable"]:
                tradable.append(sig)
            else:
                rejected.append(sig)

        executions = []
        for t in arb_trades[-10:]:
            executions.append({
                "id": str(uuid.uuid4()),
                "condition_id": f"demo-arb-{uuid.uuid4().hex[:8]}",
                "question": t["market_question"],
                "yes_fill_price": round(t["price"], 4),
                "no_fill_price": round(1 - t["price"], 4),
                "target_edge_bps": round(rng.uniform(100, 400)),
                "realized_edge_bps": round(rng.uniform(80, 350)),
                "size": t["size"],
                "status": "completed",
                "submitted_at": t["timestamp"],
                "completed_at": t["timestamp"],
            })

        return {
            "opportunities": {
                "tradable": tradable,
                "rejected": rejected,
                "total_tradable": len(tradable),
                "total_rejected": len(rejected),
            },
            "executions": {
                "active": [],
                "completed": executions,
            },
            "health": {
                "total_scans": rng.randint(5000, 12000),
                "last_scan_time": now.isoformat(),
                "last_scan_duration_ms": round(rng.uniform(1.5, 8.0), 2),
                "markets_scanned": rng.randint(300, 600),
                "pairs_evaluated": rng.randint(100, 300),
                "opportunities_found": len(tradable),
                "running": True,
            },
        }

    # ---- Sniper Strategy Data ----

    def _gen_sniper_data(self, rng, now, trades) -> Dict:
        sniper_trades = [t for t in trades if t["strategy_id"] == "crypto_sniper"]
        recent = sniper_trades[-15:]

        tradable = []
        rejected = []
        for i, t in enumerate(recent):
            asset = "BTC" if "BTC" in t["market_question"] else "ETH"
            sig = {
                "id": str(uuid.uuid4()),
                "condition_id": f"demo-sniper-{uuid.uuid4().hex[:8]}",
                "asset": asset,
                "question": t["market_question"],
                "fair_price": round(rng.uniform(0.35, 0.75), 4),
                "market_price": t["price"],
                "edge_bps": round(rng.uniform(200, 800)),
                "confidence": round(rng.uniform(0.6, 0.95), 3),
                "is_tradable": i < 6,
                "rejection_reason": None if i < 6 else rng.choice(["edge_below_min", "confidence_low", "cooldown"]),
                "detected_at": (now - timedelta(minutes=rng.randint(1, 60))).isoformat(),
            }
            if sig["is_tradable"]:
                tradable.append(sig)
            else:
                rejected.append(sig)

        executions = []
        for t in sniper_trades[-8:]:
            executions.append({
                "id": str(uuid.uuid4()),
                "signal_id": str(uuid.uuid4()),
                "condition_id": f"demo-sniper-{uuid.uuid4().hex[:8]}",
                "asset": "BTC" if "BTC" in t["market_question"] else "ETH",
                "target_edge_bps": round(rng.uniform(200, 600)),
                "size": t["size"],
                "entry_price": t["price"],
                "status": "filled",
                "submitted_at": t["timestamp"],
                "filled_at": t["timestamp"],
                "side": t["side"],
            })

        return {
            "signals": {
                "tradable": tradable,
                "rejected": rejected,
                "total_tradable": len(tradable),
                "total_rejected": len(rejected),
            },
            "executions": {
                "active": [],
                "completed": executions,
            },
            "health": {
                "total_scans": rng.randint(8000, 20000),
                "last_scan_time": now.isoformat(),
                "last_scan_duration_ms": round(rng.uniform(2.0, 12.0), 2),
                "markets_classified": rng.randint(15, 30),
                "signals_generated": rng.randint(200, 500),
                "signals_executed": rng.randint(80, 200),
                "signals_filled": rng.randint(60, 180),
                "running": True,
            },
        }

    # ---- Weather Strategy Data ----

    def _gen_weather_data(self, rng, now, trades) -> Dict:
        weather_trades = [t for t in trades if t["strategy_id"] == "weather_trader"]

        tradable = []
        rejected = []
        for i, t in enumerate(weather_trades[-12:]):
            city = rng.choice(WEATHER_CITIES)
            temp = rng.randint(35, 90)
            sig = {
                "id": str(uuid.uuid4()),
                "condition_id": f"weather-event:{city[0]}:{(now + timedelta(days=rng.randint(0,2))).strftime('%Y-%m-%d')}",
                "station_id": city[0],
                "target_date": (now + timedelta(days=rng.randint(0, 2))).strftime("%Y-%m-%d"),
                "bucket_label": f"{temp}-{temp+2}°F",
                "token_id": f"demo-weather-{uuid.uuid4().hex[:8]}",
                "forecast_high_f": round(temp + rng.uniform(-3, 5), 1),
                "sigma": round(rng.uniform(1.5, 4.0), 2),
                "lead_hours": round(rng.uniform(6, 54), 1),
                "model_prob": round(rng.uniform(0.05, 0.40), 4),
                "market_price": t["price"],
                "edge_bps": round(rng.uniform(300, 2000)),
                "confidence": round(rng.uniform(0.5, 0.9), 3),
                "recommended_size": t["size"],
                "is_tradable": i < 5,
                "rejection_reason": None if i < 5 else rng.choice([
                    "stale_market (185s)", "edge 245bps < 300bps",
                    "sigma_too_high (8.5F)", "low_liquidity (150)"
                ]),
                "detected_at": (now - timedelta(minutes=rng.randint(5, 180))).isoformat(),
            }
            if sig["is_tradable"]:
                tradable.append(sig)
            else:
                rejected.append(sig)

        executions = []
        for t in weather_trades[-6:]:
            city = rng.choice(WEATHER_CITIES)
            executions.append({
                "id": str(uuid.uuid4()),
                "signal_id": str(uuid.uuid4()),
                "condition_id": f"weather-event:{city[0]}:{now.strftime('%Y-%m-%d')}",
                "station_id": city[0],
                "target_date": now.strftime("%Y-%m-%d"),
                "bucket_label": f"{rng.randint(35, 85)}-{rng.randint(36, 87)}°F",
                "order_id": str(uuid.uuid4()),
                "status": "filled",
                "entry_price": t["price"],
                "target_edge_bps": round(rng.uniform(300, 1500)),
                "size": t["size"],
                "submitted_at": t["timestamp"],
                "filled_at": t["timestamp"],
            })

        # Forecasts
        forecasts = {}
        for city_id, city_name in WEATHER_CITIES:
            for d in range(3):
                target = (now + timedelta(days=d)).strftime("%Y-%m-%d")
                key = f"{city_id}:{target}"
                forecasts[key] = {
                    "station_id": city_id,
                    "target_date": target,
                    "forecast_high_f": round(rng.uniform(35, 90), 1),
                    "forecast_low_f": None,
                    "source": "open_meteo",
                    "fetched_at": now.isoformat(),
                    "lead_hours": round(d * 24 + rng.uniform(4, 20), 1),
                    "raw_hourly": [round(rng.uniform(30, 95), 1) for _ in range(24)],
                }

        return {
            "signals": {
                "tradable": tradable,
                "rejected": rejected,
                "total_tradable": len(tradable),
                "total_rejected": len(rejected),
            },
            "executions": {
                "active": [],
                "completed": executions,
            },
            "health": {
                "total_scans": rng.randint(500, 2000),
                "last_scan_time": now.isoformat(),
                "last_scan_duration_ms": round(rng.uniform(1.0, 5.0), 2),
                "markets_classified": rng.randint(10, 20),
                "classification_failures": 0,
                "classification_failure_reasons": {},
                "forecasts_fetched": 15,
                "forecasts_missing": 0,
                "signals_generated": rng.randint(30, 80),
                "signals_executed": rng.randint(10, 30),
                "signals_filled": rng.randint(8, 25),
                "running": True,
                "config": {
                    "scan_interval": 60.0,
                    "min_edge_bps": 300.0,
                    "min_liquidity": 200.0,
                    "kelly_scale": 0.25,
                },
                "feed_health": {
                    "open_meteo_errors": 0,
                    "nws_errors": 0,
                    "forecast_cache_size": 15,
                },
                "calibration_status": {
                    "using_defaults": True,
                    "calibrated_stations": [],
                    "total_stations": 8,
                    "note": "Using default NWS MOS sigma table",
                },
                "stations": ["KLGA", "KORD", "KLAX", "KATL", "KDFW", "KMIA", "KDEN", "KSFO"],
                "classified_markets": rng.randint(10, 20),
                "classifications": {},
                "rejection_reasons": {
                    "stale_market": rng.randint(200, 500),
                    "edge": rng.randint(50, 200),
                    "risk": rng.randint(5, 30),
                },
            },
            "forecasts": forecasts,
            "stations": [
                {"station_id": "KLGA", "city": "New York City", "state": "NY", "latitude": 40.7769, "longitude": -73.874, "timezone": "America/New_York", "station_type": "coastal", "aliases": ["NYC", "New York"]},
                {"station_id": "KORD", "city": "Chicago", "state": "IL", "latitude": 41.9742, "longitude": -87.9073, "timezone": "America/Chicago", "station_type": "inland", "aliases": ["Chicago"]},
                {"station_id": "KATL", "city": "Atlanta", "state": "GA", "latitude": 33.6407, "longitude": -84.4277, "timezone": "America/New_York", "station_type": "inland", "aliases": ["Atlanta"]},
                {"station_id": "KDFW", "city": "Dallas", "state": "TX", "latitude": 32.8998, "longitude": -97.0403, "timezone": "America/Chicago", "station_type": "inland", "aliases": ["Dallas"]},
                {"station_id": "KMIA", "city": "Miami", "state": "FL", "latitude": 25.7959, "longitude": -80.287, "timezone": "America/New_York", "station_type": "coastal", "aliases": ["Miami"]},
            ],
        }

    # ---- Config ----

    def _gen_config(self) -> Dict:
        return {
            "trading_mode": "paper",
            "risk": {
                "max_order_size": 50,
                "max_position_size": 100,
                "max_market_exposure": 200,
                "max_concurrent_positions": 15,
                "max_daily_loss": 500,
                "kill_switch_active": False,
                "max_live_slippage_bps": 50,
                "allow_aggressive_live": False,
            },
            "strategies": {
                "arb_scanner": {"strategy_id": "arb_scanner", "name": "Arb Scanner", "enabled": True, "status": "active"},
                "crypto_sniper": {"strategy_id": "crypto_sniper", "name": "Crypto Sniper", "enabled": True, "status": "active"},
                "weather_trader": {"strategy_id": "weather_trader", "name": "Weather Trader", "enabled": True, "status": "active"},
            },
            "strategy_configs": {
                "arb_scanner": {"scan_interval": 10.0, "min_edge_bps": 100.0},
                "crypto_sniper": {"scan_interval": 5.0, "min_edge_bps": 200.0},
                "weather_trader": {"scan_interval": 60.0, "min_edge_bps": 300.0},
            },
            "credentials_present": {"polymarket": False, "telegram": False},
            "telegram": {},
            "persisted": True,
        }

    # ---- Status (WebSocket snapshot shape) ----

    def _gen_status(self, now, positions, trades) -> Dict:
        closing = [t for t in trades if t["pnl"] != 0]
        wins = [t for t in closing if t["pnl"] > 0]
        losses = [t for t in closing if t["pnl"] < 0]
        daily_trades = [t for t in trades if t["timestamp"][:10] == now.strftime("%Y-%m-%d")]
        daily_pnl = sum(t["pnl"] for t in daily_trades)

        return {
            "status": "running",
            "mode": "paper",
            "uptime_seconds": DAYS * 86400 + 3247,
            "components": [
                {"name": "MarketDataFeed", "status": "running"},
                {"name": "PriceFeedManager", "status": "running"},
                {"name": "PersistenceService", "status": "running"},
            ],
            "strategies": [
                {"strategy_id": "arb_scanner", "name": "Arb Scanner", "enabled": True, "status": "active"},
                {"strategy_id": "crypto_sniper", "name": "Crypto Sniper", "enabled": True, "status": "active"},
                {"strategy_id": "weather_trader", "name": "Weather Trader", "enabled": True, "status": "active"},
            ],
            "risk": {
                "kill_switch_active": False,
                "max_concurrent_positions": 15,
            },
            "stats": {
                "daily_pnl": round(daily_pnl, 4),
                "total_trades": len(trades),
                "win_count": len(wins),
                "loss_count": len(losses),
                "win_rate": round(len(wins) / len(closing) * 100, 1) if closing else 0,
                "open_positions": len(positions),
                "open_orders": 0,
                "markets_tracked": 487,
                "spot_prices": {"BTC": 98742.50, "ETH": 3847.20, "BTCUSDT": 98742.50, "ETHUSDT": 3847.20},
                "health": {
                    "polymarket_connected": True,
                    "binance_connected": True,
                    "market_data_stale": False,
                    "last_order_latency_ms": 23.4,
                },
            },
        }

    # ---- Markets ----

    def _gen_markets(self, rng, now) -> List[Dict]:
        markets = []
        questions = ARB_QUESTIONS + [
            f"Will {a} be above ${p:,} at next 5m checkpoint?"
            for a in CRYPTO_ASSETS for p in [95000, 100000, 105000, 3500, 4000, 4500]
        ]
        for i, q in enumerate(questions[:30]):
            mid = round(rng.uniform(0.15, 0.85), 4)
            markets.append({
                "token_id": f"demo-mkt-{i}",
                "condition_id": f"demo-cond-{i}",
                "question": q,
                "outcome": rng.choice(["Yes", "No"]),
                "mid_price": mid,
                "last_price": round(mid + rng.uniform(-0.02, 0.02), 4),
                "volume_24h": round(rng.uniform(5000, 500000), 2),
                "liquidity": round(rng.uniform(1000, 50000), 2),
            })
        return sorted(markets, key=lambda m: -m["volume_24h"])

    # ---- Feed Health ----

    def _gen_feed_health(self, now) -> Dict:
        return {
            "polymarket_connected": True,
            "binance_connected": True,
            "market_data_stale": False,
            "last_polymarket_update": now.isoformat(),
            "last_binance_update": now.isoformat(),
            "markets_tracked": 487,
        }
