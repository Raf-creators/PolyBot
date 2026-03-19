import asyncio
import logging
import time
from typing import Dict, List, Optional
from collections import defaultdict

from models import (
    Event, EventType, OrderRecord, OrderSide, TradeRecord,
    StrategyConfig, StrategyStatusEnum, utc_now, new_id,
)
from engine.strategies.base import BaseStrategy
from engine.strategies.arb_models import (
    ArbConfig, ArbOpportunity, ArbExecution, ArbPairStatus,
)
from engine.strategies.arb_pricing import (
    estimate_fees, estimate_slippage, estimate_execution_penalty,
    compute_confidence, compute_data_age,
)

logger = logging.getLogger(__name__)


class ArbScanner(BaseStrategy):
    """Universal arbitrage engine.

    Scans ALL loaded markets for:
    1. Binary complement arb (YES_ask + NO_ask < 1.00) — PRIMARY
    2. Multi-outcome sum arb (sum of all outcome prices < 1.00)
    3. Cross-market price discrepancies

    Executes BOTH sides of each arb trade.
    Binary arb has higher priority and gets majority of capital.
    """

    def __init__(self, config: Optional[ArbConfig] = None):
        super().__init__(strategy_id="arb_scanner", name="Structural Arbitrage")
        self.config = config or ArbConfig()
        self._risk_engine = None
        self._execution_engine = None
        self._scan_task: Optional[asyncio.Task] = None

        # Opportunity + execution state
        self._opportunities: List[ArbOpportunity] = []
        self._active_executions: Dict[str, ArbExecution] = {}
        self._completed_executions: List[ArbExecution] = []
        self._order_to_execution: Dict[str, str] = {}
        self._cooldown: Dict[str, float] = {}
        self._cooldown_seconds = 120.0

        # Safety: consecutive failure tracking
        self._consecutive_failures = 0
        self._failure_pause_until = 0.0

        # Per-market exposure tracking
        self._market_exposure: Dict[str, float] = {}

        # Diagnostics — raw scan data from last pass
        self._diag = {
            "markets_scanned": 0,
            "binary_pairs_found": 0,
            "multi_outcome_groups_found": 0,
            "multi_outcome_weather_groups": 0,
            "multi_outcome_universal_groups": 0,
            "combinations_generated": 0,
            "raw_edges": [],
            "rejection_log": [],
        }

        # Metrics
        self._m = {
            "last_scan_time": None,
            "total_scans": 0,
            "pairs_scanned": 0,
            "multi_groups_scanned": 0,
            "raw_edges_found": 0,
            "eligible_count": 0,
            "executed_count": 0,
            "rejected_count": 0,
            "completed_count": 0,
            "invalidated_count": 0,
            "rejection_reasons": {},
            "last_execution_time": None,
            # Performance tracking
            "binary_executed": 0,
            "multi_executed": 0,
            "total_realized_edge_bps": 0.0,
            "total_capital_deployed": 0.0,
            "execution_start_time": None,
        }

    # ---- Lifecycle ----

    def set_execution_context(self, risk_engine, execution_engine):
        self._risk_engine = risk_engine
        self._execution_engine = execution_engine

    async def start(self, state, bus):
        await super().start(state, bus)
        self._bus.on(EventType.ORDER_UPDATE, self._on_order_update)
        self._scan_task = asyncio.create_task(self._scan_loop())
        self._m["execution_start_time"] = time.time()
        logger.info(
            f"ArbScanner started "
            f"(interval={self.config.scan_interval}s, "
            f"edge_floor={self.config.min_net_edge_bps}bps, "
            f"staleness_base={self.config.staleness_edge_base_bps}bps+"
            f"{self.config.staleness_edge_per_minute_bps}bps/min, "
            f"hard_stale={self.config.hard_max_stale_seconds}s, "
            f"max_concurrent={self.config.max_concurrent_arbs})"
        )

    async def stop(self):
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        if self._bus:
            self._bus.off(EventType.ORDER_UPDATE, self._on_order_update)
        await super().stop()
        logger.info("ArbScanner stopped")

    async def on_market_update(self, event):
        pass

    # ---- Scan Loop ----

    async def _scan_loop(self):
        await asyncio.sleep(8)
        while self._running:
            try:
                # Safety: check failure pause
                if time.time() < self._failure_pause_until:
                    await asyncio.sleep(self.config.scan_interval)
                    continue

                scan_results = self._run_scan()
                eligible = [o for o in scan_results if o.is_tradable]

                # BINARY FIRST — execute binary arbs before multi-outcome
                binary_eligible = [o for o in eligible if o.arb_type == "binary"]
                multi_eligible = [o for o in eligible if o.arb_type != "binary"]

                # Sort by net_edge descending (best opportunities first)
                binary_eligible.sort(key=lambda o: o.net_edge_bps, reverse=True)
                multi_eligible.sort(key=lambda o: o.net_edge_bps, reverse=True)

                for opp in binary_eligible:
                    if len(self._active_executions) >= self.config.max_concurrent_arbs:
                        break
                    await self._execute_arb(opp)

                for opp in multi_eligible:
                    if len(self._active_executions) >= self.config.max_concurrent_arbs:
                        break
                    await self._execute_multi_arb(opp)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Arb scan error: {e}", exc_info=True)
            await asyncio.sleep(self.config.scan_interval)

    def _run_scan(self) -> List[ArbOpportunity]:
        self._m["total_scans"] += 1
        self._m["last_scan_time"] = utc_now()

        # Expire old cooldowns
        now = time.time()
        self._cooldown = {
            cid: ts for cid, ts in self._cooldown.items()
            if now - ts < self._cooldown_seconds
        }

        # Update per-market exposure from current positions
        self._update_market_exposure()

        raw_edges = []
        rejection_log = []

        # ---- 1. Binary complement scan (PRIORITY) ----
        binary_pairs = self._find_binary_pairs()
        self._m["pairs_scanned"] = len(binary_pairs)

        results = []
        for condition_id, (yes_snap, no_snap) in binary_pairs.items():
            opp = self._evaluate_pair(condition_id, yes_snap, no_snap, raw_edges, rejection_log)
            if opp:
                results.append(opp)

        # ---- 2. Multi-outcome sum scan ----
        multi_groups = self._find_multi_outcome_groups()
        self._m["multi_groups_scanned"] = len(multi_groups)

        for condition_id, outcomes in multi_groups.items():
            opp = self._evaluate_multi_outcome(condition_id, outcomes, raw_edges, rejection_log)
            if opp:
                results.append(opp)

        # ---- 3. Cross-market scan ----
        cross_opps = self._find_cross_market_arbs(raw_edges, rejection_log)
        results.extend(cross_opps)

        # Diagnostics
        total_combos = len(binary_pairs) + len(multi_groups)
        self._diag["markets_scanned"] = len(self._state.markets)
        self._diag["combinations_generated"] = total_combos
        self._diag["binary_pairs_found"] = len(binary_pairs)
        self._diag["multi_outcome_groups_found"] = len(multi_groups)
        weather_groups = sum(1 for k in multi_groups if k.startswith("weather|"))
        universal_groups = sum(1 for k in multi_groups if k.startswith("universal|"))
        self._diag["multi_outcome_weather_groups"] = weather_groups
        self._diag["multi_outcome_universal_groups"] = universal_groups
        self._diag["raw_edges"] = raw_edges[-50:]
        self._diag["rejection_log"] = rejection_log[-50:]

        self._opportunities = results + self._opportunities
        if len(self._opportunities) > 300:
            self._opportunities = self._opportunities[:300]

        return results

    # ---- Market Grouping ----

    def _find_binary_pairs(self) -> Dict:
        """Find YES/NO binary pairs by condition_id across ALL markets."""
        by_condition: Dict[str, Dict] = {}

        for snap in self._state.markets.values():
            cid = snap.condition_id
            if not cid:
                continue
            if cid not in by_condition:
                by_condition[cid] = {}

            out = (snap.outcome or "").upper()
            if "YES" in out:
                by_condition[cid]["yes"] = snap
            elif "NO" in out:
                by_condition[cid]["no"] = snap

        return {
            cid: (d["yes"], d["no"])
            for cid, d in by_condition.items()
            if "yes" in d and "no" in d
        }

    def _find_multi_outcome_groups(self) -> Dict:
        """Find multi-outcome markets by grouping related YES tokens."""
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
                q, re.IGNORECASE
            )
            if weather_m:
                city = weather_m.group(1).strip().lower()
                date_str = weather_m.group(2).strip().lower().rstrip("?")
                event_key = f"weather|{city}|{date_str}"
            else:
                normalized = q.lower().strip().rstrip("?")
                normalized = re.sub(r'[\$€£]\s*[\d,]+\.?\d*', 'X', normalized)
                normalized = re.sub(r'\d+[°℉℃]?\s*[-–]\s*\d+[°℉℃]?', 'X', normalized)
                normalized = re.sub(r'(?:above|below|over|under|between|exactly)\s+[\d,.]+', 'X', normalized)
                event_key = f"universal|{normalized[:80]}"

            if event_key not in by_event:
                by_event[event_key] = []
            by_event[event_key].append(snap)

        return {
            key: snaps for key, snaps in by_event.items()
            if len(snaps) >= 3
        }

    def _find_cross_market_arbs(self, raw_edges, rejection_log) -> List[ArbOpportunity]:
        """Detect duplicate markets with same question but different prices."""
        by_question: Dict[str, List] = defaultdict(list)
        for snap in self._state.markets.values():
            q = (snap.question or "").strip().lower()
            if q and snap.mid_price and snap.mid_price > 0:
                by_question[q].append(snap)

        results = []
        for question, snaps in by_question.items():
            if len(snaps) < 2:
                continue
            by_outcome: Dict[str, List] = defaultdict(list)
            for s in snaps:
                key = (s.outcome or "").strip().lower()
                by_outcome[key].append(s)

            for outcome, group in by_outcome.items():
                if len(group) < 2:
                    continue
                sorted_g = sorted(group, key=lambda x: x.mid_price or 0)
                low = sorted_g[0]
                high = sorted_g[-1]
                spread = (high.mid_price or 0) - (low.mid_price or 0)
                spread_bps = round(spread * 10000, 2)

                if spread_bps > 50:
                    raw_edges.append({
                        "type": "cross_market",
                        "question": question[:60],
                        "outcome": outcome,
                        "low_price": low.mid_price,
                        "high_price": high.mid_price,
                        "spread_bps": spread_bps,
                    })
        return results

    # ---- Per-market Exposure ----

    def _update_market_exposure(self):
        """Track how much capital is deployed per condition_id."""
        self._market_exposure.clear()
        for pos in self._state.positions.values():
            sid = getattr(pos, "strategy_id", "") or ""
            if "arb" not in sid:
                continue
            cid = getattr(pos, "condition_id", "") or ""
            if not cid:
                # Infer from token_id matching
                for pair_cid, (y, n) in self._find_binary_pairs().items():
                    if pos.token_id in (y.token_id, n.token_id):
                        cid = pair_cid
                        break
            if cid:
                exp = pos.size * (pos.current_price or pos.avg_cost or 0)
                self._market_exposure[cid] = self._market_exposure.get(cid, 0) + exp

    def _compute_dynamic_min_edge_bps(self, stale_age_s: float, liquidity: float) -> tuple:
        """Compute required min net edge based on staleness and liquidity.

        Returns (effective_min_bps, hard_reject_reason_or_None).
        If hard_reject_reason is not None, the opportunity is an absolute reject.
        """
        cfg = self.config

        # Hard reject: data too stale regardless of edge
        if stale_age_s > cfg.hard_max_stale_seconds:
            return -1, f"hard_stale_reject ({stale_age_s:.0f}s > {cfg.hard_max_stale_seconds:.0f}s max)"

        # Hard reject: liquidity below absolute floor
        if liquidity < cfg.min_liquidity:
            return -1, f"hard_liquidity_reject ({liquidity:.0f} < {cfg.min_liquidity:.0f} min)"

        # Staleness component: linear ramp — fresher = lower bar
        staleness_bps = cfg.staleness_edge_base_bps + (stale_age_s / 60.0) * cfg.staleness_edge_per_minute_bps

        # Liquidity component: tiered buffer — thinner = bigger buffer
        if liquidity >= cfg.liquidity_deep_threshold:
            liq_bps = 0.0
        elif liquidity >= cfg.liquidity_mid_threshold:
            liq_bps = cfg.liquidity_buffer_thin_bps * 0.5
        else:
            liq_bps = cfg.liquidity_buffer_thin_bps

        dynamic_min = staleness_bps + liq_bps

        # Never below the absolute floor
        effective_min = max(dynamic_min, cfg.min_net_edge_bps)
        return round(effective_min, 2), None

    def _compute_edge_scaled_size(self, net_edge_bps: float, liquidity: float) -> float:
        """Compute position size scaled by edge magnitude and constrained by liquidity."""
        cfg = self.config
        # Base: min_size + edge_bps * scale_factor / 100
        raw_size = cfg.min_size + abs(net_edge_bps) * cfg.edge_scale_factor / 100.0
        # Constrain by max size and liquidity
        max_liq_size = liquidity * 0.1 if liquidity > 0 else cfg.min_size  # max 10% of liquidity
        size = min(raw_size, cfg.max_arb_size, max_liq_size)
        return max(size, cfg.min_size)

    # ---- Opportunity Evaluation ----

    def _evaluate_pair(self, condition_id, yes_snap, no_snap, raw_edges, rejection_log):
        """Evaluate binary arb: YES_ask + NO_ask < 1.0 after fees."""
        # Use best_ask if available, fall back to mid_price
        yes_price = yes_snap.best_ask or yes_snap.mid_price
        no_price = no_snap.best_ask or no_snap.mid_price

        if not yes_price or not no_price:
            return None
        if yes_price <= 0 or no_price <= 0:
            return None
        if yes_price >= 1.0 or no_price >= 1.0:
            return None

        if condition_id in self._cooldown:
            return None

        total_cost = yes_price + no_price
        gross_edge = 1.0 - total_cost
        gross_edge_bps = round(gross_edge * 10000, 2)

        # Data freshness + liquidity (computed early for diagnostics)
        yes_age = compute_data_age(yes_snap.updated_at)
        no_age = compute_data_age(no_snap.updated_at)
        max_age = max(yes_age, no_age)
        liquidity = min(yes_snap.liquidity, no_snap.liquidity)

        # Log ALL raw edges for diagnostics
        if abs(gross_edge_bps) > 5:
            raw_edges.append({
                "type": "binary",
                "condition_id": condition_id[:16],
                "question": (yes_snap.question or "")[:60],
                "yes_price": round(yes_price, 4),
                "no_price": round(no_price, 4),
                "total_cost": round(total_cost, 4),
                "gross_edge_bps": gross_edge_bps,
                "expected_profit_per_share": round(gross_edge, 4),
                "stale_age_s": round(max_age, 1),
                "liquidity": round(liquidity, 2),
            })

        # STRICT: reject if total_cost >= 1.0
        if total_cost >= 1.0:
            return None

        self._m["raw_edges_found"] += 1

        # Volume
        volume = min(yes_snap.volume_24h, no_snap.volume_24h)

        # Confidence
        spread_proxy = abs(gross_edge)
        confidence = compute_confidence(liquidity, max_age, spread_proxy, volume)

        # Edge-scaled sizing
        size = self._compute_edge_scaled_size(gross_edge_bps, liquidity)

        # Cost modeling
        fees_bps = estimate_fees(
            yes_price, no_price, size,
            self.config.maker_taker_rate, self.config.resolution_fee_rate,
        )
        slippage_bps = estimate_slippage(
            liquidity, volume, size, self.config.slippage_base_bps,
        )
        penalty_bps = estimate_execution_penalty(
            max_age, confidence, self.config.execution_penalty_base_bps,
        )

        net_edge_bps = round(gross_edge_bps - fees_bps - slippage_bps - penalty_bps, 2)

        # Tradability filters — hybrid staleness + liquidity dynamic threshold
        is_tradable = True
        rejection_reason = None

        # 1. Dynamic min-edge (staleness + liquidity adjusted)
        effective_min_edge, hard_reject = self._compute_dynamic_min_edge_bps(max_age, liquidity)
        if hard_reject:
            is_tradable = False
            rejection_reason = hard_reject
        elif net_edge_bps < effective_min_edge:
            is_tradable = False
            rejection_reason = (
                f"net_edge {net_edge_bps:.1f}bps < dynamic_min {effective_min_edge:.1f}bps "
                f"(age={max_age:.0f}s, liq={liquidity:.0f})"
            )
        elif confidence < self.config.min_confidence:
            is_tradable = False
            rejection_reason = f"confidence {confidence:.3f} < min {self.config.min_confidence}"
        elif self._state.risk_config.kill_switch_active:
            is_tradable = False
            rejection_reason = "kill_switch active"
        # Per-market exposure cap
        elif self._market_exposure.get(condition_id, 0) + (size * total_cost) > self.config.max_exposure_per_market:
            is_tradable = False
            rejection_reason = f"market_exposure {self._market_exposure.get(condition_id, 0):.2f} > max {self.config.max_exposure_per_market}"

        if is_tradable:
            self._m["eligible_count"] += 1
        else:
            self._m["rejected_count"] += 1
            bucket = (rejection_reason or "unknown").split(" ")[0]
            self._m["rejection_reasons"][bucket] = self._m["rejection_reasons"].get(bucket, 0) + 1
            rejection_log.append({
                "type": "binary",
                "condition_id": condition_id[:16],
                "question": (yes_snap.question or "")[:60],
                "total_cost": round(total_cost, 4),
                "gross_edge_bps": gross_edge_bps,
                "fees_bps": fees_bps,
                "slippage_bps": slippage_bps,
                "net_edge_bps": net_edge_bps,
                "stale_age_s": round(max_age, 1),
                "liquidity": round(liquidity, 2),
                "dynamic_min_edge_bps": effective_min_edge if effective_min_edge > 0 else None,
                "reason": rejection_reason,
            })

        expected_profit = max(1.0 - total_cost, 0)

        opp = ArbOpportunity(
            arb_type="binary",
            condition_id=condition_id,
            question=yes_snap.question,
            yes_token_id=yes_snap.token_id,
            no_token_id=no_snap.token_id,
            yes_price=round(yes_price, 6),
            no_price=round(no_price, 6),
            total_cost=round(total_cost, 6),
            expected_profit=round(expected_profit, 6),
            gross_edge_bps=gross_edge_bps,
            estimated_fees_bps=fees_bps,
            estimated_slippage_bps=slippage_bps,
            execution_penalty_bps=penalty_bps,
            net_edge_bps=net_edge_bps,
            liquidity_estimate=liquidity,
            confidence_score=confidence,
            recommended_size=size,
            is_tradable=is_tradable,
            rejection_reason=rejection_reason,
        )

        if hasattr(self._state, "arb_opportunities_log"):
            self._state.arb_opportunities_log.append(opp.model_dump())

        return opp

    def _evaluate_multi_outcome(self, condition_id, outcomes, raw_edges, rejection_log):
        """Evaluate multi-outcome arb: sum(all YES prices) < 1.0."""
        if condition_id in self._cooldown:
            return None

        total_cost = 0.0
        min_liquidity = float("inf")
        min_volume = float("inf")
        max_age = 0.0
        valid_outcomes = []

        for snap in outcomes:
            price = snap.best_ask or snap.mid_price or 0
            if price <= 0 or price >= 1.0:
                continue
            total_cost += price
            min_liquidity = min(min_liquidity, snap.liquidity)
            min_volume = min(min_volume, snap.volume_24h)
            max_age = max(max_age, compute_data_age(snap.updated_at))
            valid_outcomes.append(snap)

        if len(valid_outcomes) < 3:
            return None

        gross_edge = 1.0 - total_cost
        gross_edge_bps = round(gross_edge * 10000, 2)

        question = valid_outcomes[0].question if valid_outcomes else ""
        raw_edges.append({
            "type": "multi_outcome",
            "condition_id": condition_id[:16],
            "question": (question or "")[:60],
            "outcome_count": len(valid_outcomes),
            "total_cost": round(total_cost, 4),
            "gross_edge_bps": gross_edge_bps,
            "stale_age_s": round(max_age, 1),
            "liquidity": round(min_liquidity, 2),
        })

        # STRICT: reject if total_cost >= 1.0
        if total_cost >= 1.0:
            return None

        self._m["raw_edges_found"] += 1

        size = self._compute_edge_scaled_size(gross_edge_bps, min_liquidity)
        trading_fees_bps = round(total_cost * self.config.maker_taker_rate * 10000, 2)
        slippage_bps = estimate_slippage(
            min_liquidity, min_volume, size, self.config.slippage_base_bps,
        )
        net_edge_bps = round(gross_edge_bps - trading_fees_bps - slippage_bps, 2)

        # Tradability filters — hybrid staleness + liquidity dynamic threshold
        is_tradable = True
        rejection_reason = None

        effective_min_edge, hard_reject = self._compute_dynamic_min_edge_bps(max_age, min_liquidity)
        if hard_reject:
            is_tradable = False
            rejection_reason = hard_reject
        elif net_edge_bps < effective_min_edge:
            is_tradable = False
            rejection_reason = (
                f"net_edge {net_edge_bps:.1f}bps < dynamic_min {effective_min_edge:.1f}bps "
                f"(age={max_age:.0f}s, liq={min_liquidity:.0f})"
            )
        elif self._state.risk_config.kill_switch_active:
            is_tradable = False
            rejection_reason = "kill_switch active"

        if is_tradable:
            self._m["eligible_count"] += 1
            logger.info(
                f"[ARB-MULTI] {question[:50]}... "
                f"{len(valid_outcomes)} outcomes, cost={total_cost:.4f} "
                f"net_edge={net_edge_bps:.1f}bps size={size:.1f}"
            )
        else:
            self._m["rejected_count"] += 1
            bucket = (rejection_reason or "unknown").split(" ")[0]
            self._m["rejection_reasons"][bucket] = self._m["rejection_reasons"].get(bucket, 0) + 1
            rejection_log.append({
                "type": "multi_outcome",
                "condition_id": condition_id[:16],
                "question": (question or "")[:60],
                "outcomes": len(valid_outcomes),
                "total_cost": round(total_cost, 4),
                "gross_edge_bps": gross_edge_bps,
                "fees_bps": trading_fees_bps,
                "slippage_bps": slippage_bps,
                "net_edge_bps": net_edge_bps,
                "stale_age_s": round(max_age, 1),
                "liquidity": round(min_liquidity, 2),
                "dynamic_min_edge_bps": effective_min_edge if effective_min_edge > 0 else None,
                "reason": rejection_reason,
            })

        if not is_tradable:
            return None

        # Build multi-leg opportunity with ALL leg data
        all_token_ids = [s.token_id for s in valid_outcomes]
        all_prices = [round(s.best_ask or s.mid_price or 0, 6) for s in valid_outcomes]

        opp = ArbOpportunity(
            arb_type="multi_outcome",
            condition_id=condition_id,
            question=question,
            yes_token_id=valid_outcomes[0].token_id,
            no_token_id=valid_outcomes[-1].token_id,
            yes_price=round(total_cost, 6),
            no_price=0,
            total_cost=round(total_cost, 6),
            expected_profit=round(max(gross_edge, 0), 6),
            gross_edge_bps=gross_edge_bps,
            estimated_fees_bps=trading_fees_bps,
            estimated_slippage_bps=slippage_bps,
            execution_penalty_bps=0,
            net_edge_bps=net_edge_bps,
            liquidity_estimate=min_liquidity,
            confidence_score=compute_confidence(min_liquidity, max_age, abs(gross_edge), min_volume),
            recommended_size=size,
            is_tradable=True,
            rejection_reason=None,
            all_leg_token_ids=all_token_ids,
            all_leg_prices=all_prices,
        )
        return opp

    # ---- Binary Arb Execution (BOTH legs) ----

    async def _execute_arb(self, opp: ArbOpportunity):
        """Execute binary arb: buy YES + buy NO simultaneously."""
        if not self._risk_engine or not self._execution_engine:
            return

        size = opp.recommended_size

        yes_order = OrderRecord(
            token_id=opp.yes_token_id,
            side=OrderSide.BUY,
            price=opp.yes_price,
            size=size,
            strategy_id=self.strategy_id,
        )
        no_order = OrderRecord(
            token_id=opp.no_token_id,
            side=OrderSide.BUY,
            price=opp.no_price,
            size=size,
            strategy_id=self.strategy_id,
        )

        ok_y, reason_y = self._risk_engine.check_order(yes_order)
        if not ok_y:
            opp.is_tradable = False
            opp.rejection_reason = f"risk_yes: {reason_y}"
            self._m["rejected_count"] += 1
            self._m["rejection_reasons"]["risk"] = self._m["rejection_reasons"].get("risk", 0) + 1
            self._cooldown[opp.condition_id] = time.time()  # prevent re-scan spam
            logger.info(f"[ARB-BIN] Risk blocked YES leg: {reason_y} ({opp.question[:40]}...)")
            return

        ok_n, reason_n = self._risk_engine.check_order(no_order)
        if not ok_n:
            opp.is_tradable = False
            opp.rejection_reason = f"risk_no: {reason_n}"
            self._m["rejected_count"] += 1
            self._m["rejection_reasons"]["risk"] = self._m["rejection_reasons"].get("risk", 0) + 1
            self._cooldown[opp.condition_id] = time.time()
            logger.info(f"[ARB-BIN] Risk blocked NO leg: {reason_n} ({opp.question[:40]}...)")
            return

        execution = ArbExecution(
            arb_type="binary",
            opportunity_id=opp.id,
            condition_id=opp.condition_id,
            question=opp.question,
            yes_order_id=yes_order.id,
            no_order_id=no_order.id,
            target_edge_bps=opp.net_edge_bps,
            size=size,
            all_order_ids=[yes_order.id, no_order.id],
            all_fill_prices=[None, None],
            legs_total=2,
        )

        self._active_executions[execution.id] = execution
        self._order_to_execution[yes_order.id] = execution.id
        self._order_to_execution[no_order.id] = execution.id
        opp.execution_id = execution.id
        self._m["executed_count"] += 1
        self._m["binary_executed"] += 1
        self._m["total_capital_deployed"] += size * (opp.yes_price + opp.no_price)
        self._cooldown[opp.condition_id] = time.time()

        await self._bus.emit(Event(
            type=EventType.SIGNAL,
            source=self.strategy_id,
            data={
                "strategy": "ARB-BINARY", "asset": opp.question[:50],
                "strike": "", "fair_price": 1 - opp.total_cost,
                "market_price": opp.total_cost,
                "edge_bps": opp.net_edge_bps, "side": "BUY YES+NO",
                "size": size,
            },
        ))

        logger.info(
            f"[ARB-BIN] Executing: {opp.question[:50]}... "
            f"YES={opp.yes_price:.4f} NO={opp.no_price:.4f} "
            f"cost={opp.total_cost:.4f} profit/share={opp.expected_profit:.4f} "
            f"net_edge={opp.net_edge_bps:.1f}bps size={size:.1f}"
        )

        try:
            await self._execution_engine.submit_order(yes_order)
            await self._execution_engine.submit_order(no_order)
            self._consecutive_failures = 0
        except Exception as e:
            logger.error(f"Arb execution error: {e}")
            execution.status = ArbPairStatus.INVALIDATED
            execution.invalidation_reason = str(e)
            self._m["invalidated_count"] += 1
            self._consecutive_failures += 1
            self._check_failure_killswitch()
            self._finalize_execution(execution)

    # ---- Multi-Outcome Arb Execution (ALL legs) ----

    async def _execute_multi_arb(self, opp: ArbOpportunity):
        """Execute multi-outcome arb: buy ALL outcome tokens."""
        if not self._risk_engine or not self._execution_engine:
            return

        if not opp.all_leg_token_ids or len(opp.all_leg_token_ids) < 3:
            return

        size = opp.recommended_size
        orders = []

        # Create orders for all legs
        for token_id, price in zip(opp.all_leg_token_ids, opp.all_leg_prices):
            order = OrderRecord(
                token_id=token_id,
                side=OrderSide.BUY,
                price=price,
                size=size,
                strategy_id=self.strategy_id,
            )
            ok, reason = self._risk_engine.check_order(order)
            if not ok:
                opp.is_tradable = False
                opp.rejection_reason = f"risk_leg: {reason}"
                self._m["rejected_count"] += 1
                self._m["rejection_reasons"]["risk"] = self._m["rejection_reasons"].get("risk", 0) + 1
                self._cooldown[opp.condition_id] = time.time()
                logger.info(
                    f"[ARB-MULTI] Risk blocked leg {len(orders)+1}/{len(opp.all_leg_token_ids)}: "
                    f"{reason} (market: {opp.question[:40]}...)"
                )
                return
            orders.append(order)

        execution = ArbExecution(
            arb_type="multi_outcome",
            opportunity_id=opp.id,
            condition_id=opp.condition_id,
            question=opp.question,
            yes_order_id=orders[0].id,
            no_order_id=orders[-1].id,
            target_edge_bps=opp.net_edge_bps,
            size=size,
            all_order_ids=[o.id for o in orders],
            all_fill_prices=[None] * len(orders),
            legs_total=len(orders),
        )

        self._active_executions[execution.id] = execution
        for order in orders:
            self._order_to_execution[order.id] = execution.id
        opp.execution_id = execution.id
        self._m["executed_count"] += 1
        self._m["multi_executed"] += 1
        self._m["total_capital_deployed"] += size * opp.total_cost
        self._cooldown[opp.condition_id] = time.time()

        logger.info(
            f"[ARB-MULTI] Executing: {opp.question[:50]}... "
            f"{len(orders)} legs, cost={opp.total_cost:.4f} "
            f"profit/share={opp.expected_profit:.4f} "
            f"net_edge={opp.net_edge_bps:.1f}bps size={size:.1f}"
        )

        try:
            for order in orders:
                await self._execution_engine.submit_order(order)
            self._consecutive_failures = 0
        except Exception as e:
            logger.error(f"Multi-arb execution error: {e}")
            execution.status = ArbPairStatus.INVALIDATED
            execution.invalidation_reason = str(e)
            self._m["invalidated_count"] += 1
            self._consecutive_failures += 1
            self._check_failure_killswitch()
            self._finalize_execution(execution)

    # ---- Safety ----

    def _check_failure_killswitch(self):
        """Pause arb execution if too many consecutive failures."""
        if self._consecutive_failures >= self.config.max_consecutive_failures:
            self._failure_pause_until = time.time() + self.config.failure_cooldown_seconds
            logger.warning(
                f"[ARB-SAFETY] Kill-switch: {self._consecutive_failures} consecutive failures. "
                f"Pausing for {self.config.failure_cooldown_seconds}s"
            )

    # ---- Fill Tracking ----

    async def _on_order_update(self, event: Event):
        if event.source != "paper_adapter":
            return

        order_id = event.data.get("order_id")
        if not order_id:
            return

        exec_id = self._order_to_execution.get(order_id)
        if not exec_id:
            return

        execution = self._active_executions.get(exec_id)
        if not execution:
            return

        fill_price = event.data.get("fill_price")
        status = event.data.get("status")

        if status == "filled":
            # Track fill for the specific leg
            if order_id in execution.all_order_ids:
                idx = execution.all_order_ids.index(order_id)
                if idx < len(execution.all_fill_prices):
                    execution.all_fill_prices[idx] = fill_price
                    execution.legs_filled += 1

            # Legacy binary fill tracking
            if order_id == execution.yes_order_id:
                execution.yes_fill_price = fill_price
            elif order_id == execution.no_order_id:
                execution.no_fill_price = fill_price

            # Check if ALL legs are filled
            if execution.legs_filled >= execution.legs_total:
                execution.status = ArbPairStatus.COMPLETED
                execution.completed_at = utc_now()
                filled_prices = [p for p in execution.all_fill_prices if p is not None]
                total_cost = sum(filled_prices)
                execution.realized_edge_bps = round((1.0 - total_cost) * 10000, 2)
                self._m["completed_count"] += 1
                self._m["total_realized_edge_bps"] += execution.realized_edge_bps
                self._m["last_execution_time"] = utc_now()
                logger.info(
                    f"[ARB] COMPLETED ({execution.arb_type}): {execution.question[:40]}... "
                    f"legs={execution.legs_total} total_cost={total_cost:.4f} "
                    f"realized={execution.realized_edge_bps:.1f}bps "
                    f"(target={execution.target_edge_bps:.1f}bps)"
                )
                self._finalize_execution(execution)
            else:
                execution.status = ArbPairStatus.PARTIALLY_FILLED

        elif status in ("rejected", "cancelled"):
            execution.status = ArbPairStatus.INVALIDATED
            execution.invalidation_reason = f"leg {order_id[:8]} {status}"
            self._m["invalidated_count"] += 1
            logger.warning(f"[ARB] INVALIDATED: {execution.question[:40]}...")
            self._finalize_execution(execution)

    def _finalize_execution(self, execution: ArbExecution):
        self._active_executions.pop(execution.id, None)
        self._completed_executions.append(execution)
        if len(self._completed_executions) > 200:
            self._completed_executions = self._completed_executions[-200:]
        for oid in execution.all_order_ids:
            self._order_to_execution.pop(oid, None)
        self._order_to_execution.pop(execution.yes_order_id, None)
        self._order_to_execution.pop(execution.no_order_id, None)
        if hasattr(self._state, "arb_executions_log"):
            self._state.arb_executions_log.append(execution.model_dump())

    # ---- API Data ----

    def get_opportunities(self, limit: int = 50) -> List[dict]:
        return [o.model_dump() for o in self._opportunities[:limit]]

    def get_active_executions(self) -> List[dict]:
        return [e.model_dump() for e in self._active_executions.values()]

    def get_completed_executions(self, limit: int = 50) -> List[dict]:
        return [e.model_dump() for e in self._completed_executions[-limit:]]

    def get_diagnostics(self) -> dict:
        # Show dynamic threshold at representative data points
        threshold_samples = []
        for age_s in [30, 120, 300, 600, 900, 1200, 1800]:
            for liq in [300, 800, 3000]:
                min_edge, reject = self._compute_dynamic_min_edge_bps(age_s, liq)
                threshold_samples.append({
                    "stale_age_s": age_s,
                    "liquidity": liq,
                    "required_min_edge_bps": min_edge if not reject else None,
                    "hard_reject": reject,
                })
        return {
            **self._diag,
            "metrics": self._m,
            "config": self.config.model_dump(),
            "active_executions": len(self._active_executions),
            "total_completed": len(self._completed_executions),
            "dynamic_threshold_samples": threshold_samples,
        }

    def get_performance(self) -> dict:
        """Arb performance metrics for tracking capital efficiency."""
        elapsed_h = max((time.time() - (self._m["execution_start_time"] or time.time())) / 3600, 0.01)
        completed = self._m["completed_count"]
        avg_edge = self._m["total_realized_edge_bps"] / max(completed, 1)

        # Capital utilization: deployed / reserved
        reserved = self._state.risk_config.arb_reserved_capital if self._state else 120
        arb_exposure = sum(
            pos.size * (pos.current_price or pos.avg_cost or 0)
            for pos in self._state.positions.values()
            if "arb" in (getattr(pos, "strategy_id", "") or "")
        ) if self._state else 0

        return {
            "trades_per_hour": round(completed / elapsed_h, 2),
            "avg_realized_edge_bps": round(avg_edge, 2),
            "total_realized_edge_bps": round(self._m["total_realized_edge_bps"], 2),
            "capital_deployed": round(self._m["total_capital_deployed"], 2),
            "current_exposure": round(arb_exposure, 2),
            "capital_utilization_pct": round(arb_exposure / max(reserved, 1) * 100, 1),
            "binary_executed": self._m["binary_executed"],
            "multi_executed": self._m["multi_executed"],
            "completed": completed,
            "invalidated": self._m["invalidated_count"],
            "uptime_hours": round(elapsed_h, 2),
            "consecutive_failures": self._consecutive_failures,
            "failure_paused": time.time() < self._failure_pause_until,
        }

    def get_health(self) -> dict:
        return {
            **self._m,
            "config": self.config.model_dump(),
            "active_executions": len(self._active_executions),
            "total_completed_executions": len(self._completed_executions),
            "running": self._running,
            "performance": self.get_performance(),
            "diagnostics": {
                "markets_scanned": self._diag["markets_scanned"],
                "binary_pairs_found": self._diag["binary_pairs_found"],
                "multi_outcome_groups_found": self._diag["multi_outcome_groups_found"],
                "combinations_generated": self._diag["combinations_generated"],
                "raw_edges_count": len(self._diag["raw_edges"]),
                "rejection_log_count": len(self._diag["rejection_log"]),
            },
        }

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            strategy_id=self.strategy_id,
            name=self.name,
            enabled=self._running,
            status=StrategyStatusEnum.ACTIVE if self._running else StrategyStatusEnum.STOPPED,
            parameters=self.config.model_dump(),
        )
