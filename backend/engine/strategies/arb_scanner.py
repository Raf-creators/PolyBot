import asyncio
import logging
import time
from typing import Dict, List, Optional

from models import (
    Event, EventType, OrderRecord, OrderSide,
    StrategyConfig, StrategyStatusEnum, utc_now,
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
    """Binary complement arbitrage scanner.

    Scans loaded binary markets for opportunities where:
        YES_ask + NO_ask < 1.00 after modeled costs.
    Executes paired paper trades with full lifecycle tracking.
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
        self._cooldown: Dict[str, float] = {}  # condition_id -> last exec timestamp
        self._cooldown_seconds = 120.0  # no re-execution within 2 minutes

        # Metrics
        self._m = {
            "last_scan_time": None,
            "total_scans": 0,
            "pairs_scanned": 0,
            "raw_edges_found": 0,
            "eligible_count": 0,
            "executed_count": 0,
            "rejected_count": 0,
            "completed_count": 0,
            "invalidated_count": 0,
            "rejection_reasons": {},
            "last_execution_time": None,
        }

    # ---- Lifecycle ----

    def set_execution_context(self, risk_engine, execution_engine):
        self._risk_engine = risk_engine
        self._execution_engine = execution_engine

    async def start(self, state, bus):
        await super().start(state, bus)
        self._bus.on(EventType.ORDER_UPDATE, self._on_order_update)
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info(
            f"ArbScanner started "
            f"(interval={self.config.scan_interval}s, "
            f"min_edge={self.config.min_net_edge_bps}bps)"
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
        pass  # Arb scanner uses its own scan loop

    # ---- Scan Loop ----

    async def _scan_loop(self):
        await asyncio.sleep(8)  # let market data settle
        while self._running:
            try:
                scan_results = self._run_scan()
                eligible = [o for o in scan_results if o.is_tradable]
                for opp in eligible:
                    if len(self._active_executions) >= self.config.max_concurrent_arbs:
                        break
                    await self._execute_arb(opp)
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

        pairs = self._find_binary_pairs()
        self._m["pairs_scanned"] = len(pairs)

        results = []
        for condition_id, (yes_snap, no_snap) in pairs.items():
            opp = self._evaluate_pair(condition_id, yes_snap, no_snap)
            if opp:
                results.append(opp)

        # Prepend new results, keep last 300
        self._opportunities = results + self._opportunities
        if len(self._opportunities) > 300:
            self._opportunities = self._opportunities[:300]

        return results

    # ---- Market Pairing ----

    def _find_binary_pairs(self) -> Dict:
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

    # ---- Opportunity Evaluation ----

    def _evaluate_pair(self, condition_id, yes_snap, no_snap):
        yes_price = yes_snap.mid_price
        no_price = no_snap.mid_price

        if not yes_price or not no_price:
            return None
        if yes_price <= 0 or no_price <= 0:
            return None
        if yes_price >= 1.0 or no_price >= 1.0:
            return None

        # Cooldown: skip recently-traded pairs
        if condition_id in self._cooldown:
            return None

        # Gross edge
        gross_edge = 1.0 - (yes_price + no_price)
        gross_edge_bps = round(gross_edge * 10000, 2)
        if gross_edge_bps <= 0:
            return None

        self._m["raw_edges_found"] += 1

        # Data freshness
        yes_age = compute_data_age(yes_snap.updated_at)
        no_age = compute_data_age(no_snap.updated_at)
        max_age = max(yes_age, no_age)

        # Liquidity — use the weaker side (bottleneck)
        liquidity = min(yes_snap.liquidity, no_snap.liquidity)
        volume = min(yes_snap.volume_24h, no_snap.volume_24h)

        # Confidence
        spread_proxy = abs(gross_edge)
        confidence = compute_confidence(liquidity, max_age, spread_proxy, volume)

        # Cost modeling
        size = min(self.config.default_size, self.config.max_arb_size)
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

        # Tradability filters
        is_tradable = True
        rejection_reason = None

        if net_edge_bps < self.config.min_net_edge_bps:
            is_tradable = False
            rejection_reason = f"net_edge {net_edge_bps:.1f}bps < min {self.config.min_net_edge_bps}bps"
        elif liquidity < self.config.min_liquidity:
            is_tradable = False
            rejection_reason = f"liquidity {liquidity:.0f} < min {self.config.min_liquidity}"
        elif confidence < self.config.min_confidence:
            is_tradable = False
            rejection_reason = f"confidence {confidence:.3f} < min {self.config.min_confidence}"
        elif max_age > self.config.max_stale_age_seconds:
            is_tradable = False
            rejection_reason = f"stale data {max_age:.0f}s > max {self.config.max_stale_age_seconds}s"
        elif self._state.risk_config.kill_switch_active:
            is_tradable = False
            rejection_reason = "kill_switch active"

        if is_tradable:
            self._m["eligible_count"] += 1
        else:
            self._m["rejected_count"] += 1
            bucket = (rejection_reason or "unknown").split(" ")[0]
            self._m["rejection_reasons"][bucket] = self._m["rejection_reasons"].get(bucket, 0) + 1

        opp = ArbOpportunity(
            condition_id=condition_id,
            question=yes_snap.question,
            yes_token_id=yes_snap.token_id,
            no_token_id=no_snap.token_id,
            yes_price=round(yes_price, 6),
            no_price=round(no_price, 6),
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

        # Persist to state log for write-behind
        if hasattr(self._state, "arb_opportunities_log"):
            self._state.arb_opportunities_log.append(opp.model_dump())

        return opp

    # ---- Paired Execution ----

    async def _execute_arb(self, opp: ArbOpportunity):
        if not self._risk_engine or not self._execution_engine:
            logger.warning("No execution context; skipping arb")
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

        # Pre-flight risk check for both legs
        ok_y, reason_y = self._risk_engine.check_order(yes_order)
        if not ok_y:
            opp.is_tradable = False
            opp.rejection_reason = f"risk_yes: {reason_y}"
            self._m["rejected_count"] += 1
            self._m["rejection_reasons"]["risk"] = self._m["rejection_reasons"].get("risk", 0) + 1
            return

        ok_n, reason_n = self._risk_engine.check_order(no_order)
        if not ok_n:
            opp.is_tradable = False
            opp.rejection_reason = f"risk_no: {reason_n}"
            self._m["rejected_count"] += 1
            self._m["rejection_reasons"]["risk"] = self._m["rejection_reasons"].get("risk", 0) + 1
            return

        # Create execution record
        execution = ArbExecution(
            opportunity_id=opp.id,
            condition_id=opp.condition_id,
            question=opp.question,
            yes_order_id=yes_order.id,
            no_order_id=no_order.id,
            target_edge_bps=opp.net_edge_bps,
            size=size,
        )

        self._active_executions[execution.id] = execution
        self._order_to_execution[yes_order.id] = execution.id
        self._order_to_execution[no_order.id] = execution.id
        opp.execution_id = execution.id
        self._m["executed_count"] += 1
        self._cooldown[opp.condition_id] = time.time()

        # Emit signal event for notification system (non-blocking)
        await self._bus.emit(Event(
            type=EventType.SIGNAL,
            source=self.strategy_id,
            data={
                "strategy": "ARB", "asset": opp.question[:50],
                "strike": "", "fair_price": 1 - opp.yes_price - opp.no_price,
                "market_price": opp.yes_price + opp.no_price,
                "edge_bps": opp.net_edge_bps, "side": "BUY YES+NO",
            },
        ))

        logger.info(
            f"[ARB] Submitting pair: {opp.question[:50]}... "
            f"YES={opp.yes_price:.4f} NO={opp.no_price:.4f} "
            f"net_edge={opp.net_edge_bps:.1f}bps size={size}"
        )

        try:
            await self._execution_engine.submit_order(yes_order)
            await self._execution_engine.submit_order(no_order)
        except Exception as e:
            logger.error(f"Arb execution error: {e}")
            execution.status = ArbPairStatus.INVALIDATED
            execution.invalidation_reason = str(e)
            self._m["invalidated_count"] += 1
            self._finalize_execution(execution)

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
            if order_id == execution.yes_order_id:
                execution.yes_fill_price = fill_price
            elif order_id == execution.no_order_id:
                execution.no_fill_price = fill_price

            if execution.yes_fill_price is not None and execution.no_fill_price is not None:
                # Both legs filled — pair complete
                execution.status = ArbPairStatus.COMPLETED
                execution.completed_at = utc_now()
                total_cost = execution.yes_fill_price + execution.no_fill_price
                execution.realized_edge_bps = round((1.0 - total_cost) * 10000, 2)
                self._m["completed_count"] += 1
                self._m["last_execution_time"] = utc_now()
                logger.info(
                    f"[ARB] COMPLETED: {execution.question[:40]}... "
                    f"Y={execution.yes_fill_price:.4f} N={execution.no_fill_price:.4f} "
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
        """Move execution from active to completed and log for persistence."""
        self._active_executions.pop(execution.id, None)
        self._completed_executions.append(execution)
        if len(self._completed_executions) > 200:
            self._completed_executions = self._completed_executions[-200:]

        # Clean up order mappings
        self._order_to_execution.pop(execution.yes_order_id, None)
        self._order_to_execution.pop(execution.no_order_id, None)

        # Persist to state log for write-behind
        if hasattr(self._state, "arb_executions_log"):
            self._state.arb_executions_log.append(execution.model_dump())

    # ---- API Data ----

    def get_opportunities(self, limit: int = 50) -> List[dict]:
        return [o.model_dump() for o in self._opportunities[:limit]]

    def get_active_executions(self) -> List[dict]:
        return [e.model_dump() for e in self._active_executions.values()]

    def get_completed_executions(self, limit: int = 50) -> List[dict]:
        return [e.model_dump() for e in self._completed_executions[-limit:]]

    def get_health(self) -> dict:
        return {
            **self._m,
            "config": self.config.model_dump(),
            "active_executions": len(self._active_executions),
            "total_completed_executions": len(self._completed_executions),
            "running": self._running,
        }

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            strategy_id=self.strategy_id,
            name=self.name,
            enabled=self._running,
            status=StrategyStatusEnum.ACTIVE if self._running else StrategyStatusEnum.STOPPED,
            parameters=self.config.model_dump(),
        )
