"""Crypto Sniper Strategy — directional pricing on BTC/ETH 5m/15m markets.

Uses Binance spot price + simplified option model to compute fair probability,
then trades when Polymarket price diverges beyond a configurable threshold.

Architecture:
  - Classification (slow, every 30s): regex-parse market titles → cache
  - Price sampling (fast, every scan): append spot to ring buffer
  - Evaluation (fast, every scan): compute fair prob → edge → filter
  - Execution (async): submit through RiskEngine + ExecutionEngine
"""

import asyncio
import logging
import math
import re
import time
from collections import deque, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from models import (
    Event, EventType, OrderRecord, OrderSide, TradeRecord,
    StrategyConfig, StrategyStatusEnum, utc_now, new_id,
)
from engine.strategies.base import BaseStrategy
from engine.strategies.sniper_models import (
    SniperConfig, CryptoMarketClassification, SniperSignal,
    SniperExecution, SniperSignalStatus,
)
from engine.strategies.sniper_pricing import (
    compute_fair_probability, compute_realized_volatility,
    compute_momentum, compute_signal_confidence, compute_edge_bps,
)
from engine.strategies.arb_pricing import compute_data_age

logger = logging.getLogger(__name__)


# ---- Market Classification Patterns ----
# Compiled once at module load. Checked in order; first match wins.

_ASSET_NORM = {
    "btc": "BTC", "bitcoin": "BTC",
    "eth": "ETH", "ethereum": "ETH",
}
_DIR_NORM = {
    "above": "above", "over": "above", "higher than": "above",
    "≥": "above", ">=": "above", ">": "above",
    "reach": "above", "hit": "above",
    "below": "below", "under": "below", "lower than": "below",
    "dip to": "below", "dip": "below",
    "≤": "below", "<=": "below", "<": "below",
}

# Slug-based patterns — checked BEFORE question patterns
_SLUG_PATTERNS = [
    # {asset}-updown-{window}-{timestamp}  e.g., btc-updown-5m-1773666000
    re.compile(
        r"^(?P<asset>btc|eth|bitcoin|ethereum)-updown-"
        r"(?P<window>5m|15m|1h|4h)-"
        r"(?P<ts>\d{10,})",
        re.IGNORECASE,
    ),
    # {asset}-up-or-down-{date-info}  e.g., bitcoin-up-or-down-march-17-2026-12pm-et
    re.compile(
        r"^(?P<asset>btc|eth|bitcoin|ethereum)-up-or-down-",
        re.IGNORECASE,
    ),
    # {asset}-above-{price}-on-{date}  e.g., ethereum-above-2400-on-march-16
    re.compile(
        r"^(?P<asset>btc|eth|bitcoin|ethereum)-above-"
        r"(?P<strike>[\d]+[km]?)-on-",
        re.IGNORECASE,
    ),
    # will-{asset}-hit-{price}-by-{date}  e.g., will-bitcoin-hit-150k-by-march-31-2026
    re.compile(
        r"^will-(?P<asset>btc|eth|bitcoin|ethereum)-(?:hit|reach)-"
        r"(?P<strike>[\d]+[km]?)-by-",
        re.IGNORECASE,
    ),
]

# Question-based patterns — fallback when slug doesn't match
_QUESTION_PATTERNS = [
    # "Will BTC be above $97,000 at 12:15 UTC?"
    re.compile(
        r"(?:Will\s+)?(?P<asset>BTC|Bitcoin|ETH|Ethereum)\b"
        r".*?(?P<dir>above|below|over|under|higher than|lower than)"
        r"\s+\$?(?P<strike>[\d,]+(?:\.\d+)?)"
        r".*?(?:at|by)\s+(?P<time>\d{1,2}:\d{2})\s*(?:(?:AM|PM)\s*)?(?:UTC|ET|EST|EDT)?",
        re.IGNORECASE,
    ),
    # "Will the price of Ethereum be above $2,400 on March 16?" / "Will Bitcoin hit $150k by March 31?"
    re.compile(
        r"(?:Will\s+)?(?:the\s+)?(?:price\s+of\s+)?(?P<asset>BTC|Bitcoin|ETH|Ethereum)\b"
        r".*?(?:be\s+)?(?P<dir>above|below|over|under|higher than|lower than|reach|hit|dip(?:\s+to)?)"
        r"\s+\$?(?P<strike>[\d,]+(?:[km])?(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    # "Bitcoin Up or Down - March 17, 12PM ET" (question-based updown)
    re.compile(
        r"(?P<asset>BTC|Bitcoin|ETH|Ethereum)\b"
        r"\s+Up\s+or\s+Down",
        re.IGNORECASE,
    ),
    # "BTC price ≥ $97000 at 4:00 PM ET"
    re.compile(
        r"(?P<asset>BTC|Bitcoin|ETH|Ethereum)\b"
        r".*?(?:price\s*)?(?P<dir>[>≥<≤])\s*\$?(?P<strike>[\d,]+(?:\.\d+)?)"
        r".*?(?:at|by)\s+(?P<time>\d{1,2}:\d{2})\s*(?:(?:AM|PM)\s*)?(?:UTC|ET|EST|EDT)?",
        re.IGNORECASE,
    ),
    # "Will the price of Bitcoin be between $70,000 and $72,000 on March 16?"
    re.compile(
        r"(?:Will\s+)?(?:the\s+)?(?:price\s+of\s+)?(?P<asset>BTC|Bitcoin|ETH|Ethereum)\b"
        r".*?between\s+\$?(?P<strike_low>[\d,]+(?:\.\d+)?)"
        r"\s+and\s+\$?(?P<strike_high>[\d,]+(?:\.\d+)?)",
        re.IGNORECASE,
    ),
]

# Window string to seconds mapping for updown slug parsing
_WINDOW_SECONDS = {
    "5m": 300, "15m": 900, "1h": 3600, "4h": 14400,
}


def _parse_asset(raw: str) -> Optional[str]:
    return _ASSET_NORM.get(raw.lower())


def _parse_direction(raw: str) -> Optional[str]:
    return _DIR_NORM.get(raw.lower())


def _parse_strike(raw: str) -> Optional[float]:
    try:
        clean = raw.replace(",", "")
        # Handle "150k" → 150000, "1m" → 1000000
        lower = clean.lower()
        if lower.endswith("m"):
            return float(clean[:-1]) * 1_000_000
        if lower.endswith("k"):
            return float(clean[:-1]) * 1_000
        return float(clean)
    except (ValueError, TypeError):
        return None


def _parse_expiry(time_str: Optional[str], end_date_str: Optional[str]) -> Optional[datetime]:
    """Parse expiry datetime from either explicit time in question or endDate field."""
    now = datetime.now(timezone.utc)

    if time_str:
        try:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            # Assume UTC, today. If past, try tomorrow.
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt <= now:
                dt += timedelta(days=1)
            return dt
        except (ValueError, IndexError):
            pass

    if end_date_str:
        try:
            dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            pass

    return None


def classify_market_question(
    question: str,
    condition_id: str,
    yes_token_id: str,
    no_token_id: str,
    end_date: Optional[str] = None,
    slug: str = "",
) -> Tuple[Optional[CryptoMarketClassification], Optional[str]]:
    """Try to classify a market as a tradable crypto binary option.

    Checks slug patterns first (most reliable), then falls back to question parsing.
    Returns (classification, None) on success or (None, rejection_reason) on failure.
    """
    # ---- Phase 1: Slug-based classification ----
    if slug:
        result = _classify_from_slug(slug, condition_id, yes_token_id, no_token_id, question, end_date)
        if result:
            return result, None

    # ---- Phase 2: Question-based fallback ----
    return _classify_from_question(question, condition_id, yes_token_id, no_token_id, end_date)


def _classify_from_slug(
    slug: str, condition_id: str, yes_token_id: str, no_token_id: str,
    question: str, end_date: Optional[str],
) -> Optional[CryptoMarketClassification]:
    """Parse slug patterns for crypto markets."""

    # Pattern 1: {asset}-updown-{window}-{timestamp}
    m = _SLUG_PATTERNS[0].search(slug)
    if m:
        asset = _parse_asset(m.group("asset"))
        if not asset:
            return None
        window = m.group("window")
        ts = int(m.group("ts"))
        expiry = datetime.fromtimestamp(ts, tz=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            return None  # Expired
        return CryptoMarketClassification(
            condition_id=condition_id,
            asset=asset,
            direction="above",  # updown → YES=Up → direction=above
            strike=0,  # sentinel: use spot price at evaluation time
            expiry_utc=expiry.isoformat(),
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            question=question,
            window=window,
            market_type="updown",
        )

    # Pattern 2: {asset}-up-or-down-{date-info}
    m = _SLUG_PATTERNS[1].search(slug)
    if m:
        asset = _parse_asset(m.group("asset"))
        if not asset:
            return None
        expiry = _parse_expiry(None, end_date)
        if expiry is None or expiry <= datetime.now(timezone.utc):
            return None
        return CryptoMarketClassification(
            condition_id=condition_id,
            asset=asset,
            direction="above",
            strike=0,
            expiry_utc=expiry.isoformat(),
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            question=question,
            window=None,
            market_type="updown",
        )

    # Pattern 3: {asset}-above-{price}-on-{date} OR will-{asset}-hit-{price}-by-{date}
    for pat in _SLUG_PATTERNS[2:4]:
        m = pat.search(slug)
        if m:
            asset = _parse_asset(m.group("asset"))
            if not asset:
                continue
            strike = _parse_strike(m.group("strike"))
            if strike is None or strike <= 0:
                continue
            expiry = _parse_expiry(None, end_date)
            if expiry is None or expiry <= datetime.now(timezone.utc):
                return None
            return CryptoMarketClassification(
                condition_id=condition_id,
                asset=asset,
                direction="above",
                strike=strike,
                expiry_utc=expiry.isoformat(),
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                question=question,
                market_type="threshold",
            )

    return None


def _classify_from_question(
    question: str, condition_id: str, yes_token_id: str, no_token_id: str,
    end_date: Optional[str],
) -> Tuple[Optional[CryptoMarketClassification], Optional[str]]:
    """Parse question text for crypto market classification."""

    for i, pattern in enumerate(_QUESTION_PATTERNS):
        m = pattern.search(question)
        if not m:
            continue

        groups = m.groupdict()
        asset = _parse_asset(groups.get("asset", ""))
        if not asset:
            continue

        # "Up or Down" question pattern (index 2)
        if i == 2:
            expiry = _parse_expiry(None, end_date)
            if expiry is None or expiry <= datetime.now(timezone.utc):
                return None, "invalid_expiry"
            return CryptoMarketClassification(
                condition_id=condition_id,
                asset=asset,
                direction="above",
                strike=0,
                expiry_utc=expiry.isoformat(),
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                question=question,
                market_type="updown",
            ), None

        # "Between X and Y" pattern (index 4)
        if i == 4:
            strike_low = _parse_strike(groups.get("strike_low", ""))
            strike_high = _parse_strike(groups.get("strike_high", ""))
            if strike_low is None or strike_high is None:
                return None, "invalid_strike"
            # Use midpoint as the strike, direction=above for the lower bound
            strike = (strike_low + strike_high) / 2
            expiry = _parse_expiry(groups.get("time"), end_date)
            if expiry is None or expiry <= datetime.now(timezone.utc):
                return None, "invalid_expiry"
            return CryptoMarketClassification(
                condition_id=condition_id,
                asset=asset,
                direction="above",
                strike=strike,
                expiry_utc=expiry.isoformat(),
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                question=question,
                market_type="range",
            ), None

        # Standard directional patterns (index 0, 1, 3)
        direction = _parse_direction(groups.get("dir", ""))
        if not direction:
            return None, "unknown_direction"

        strike = _parse_strike(groups.get("strike", ""))
        if strike is None or strike <= 0:
            return None, "invalid_strike"

        expiry = _parse_expiry(groups.get("time"), end_date)
        if expiry is None:
            return None, "invalid_expiry"
        if expiry <= datetime.now(timezone.utc):
            return None, "expired"

        return CryptoMarketClassification(
            condition_id=condition_id,
            asset=asset,
            direction=direction,
            strike=strike,
            expiry_utc=expiry.isoformat(),
            yes_token_id=yes_token_id,
            no_token_id=no_token_id,
            question=question,
            market_type="threshold",
        ), None

    return None, "no_regex_match"


# ---- Strategy Class ----


class CryptoSniper(BaseStrategy):
    """Directional crypto sniper for BTC/ETH 5m/15m Polymarket markets.

    Uses Binance spot price and a simplified digital option model to compute
    fair probability. Trades when market probability diverges from model.
    """

    def __init__(self, config: Optional[SniperConfig] = None):
        super().__init__(strategy_id="crypto_sniper", name="Crypto Sniper")
        self.config = config or SniperConfig()
        self._risk_engine = None
        self._execution_engine = None
        self._scan_task: Optional[asyncio.Task] = None
        self._tracker = None  # StrategyTracker (injected at start)
        self._shadow = None   # ShadowSniperEngine (injected from server.py)
        self._moondev = None  # MoonDevShadowEngine (injected from server.py)

        # Classification cache (refreshed every classification_refresh_interval)
        self._classified_cache: Dict[str, CryptoMarketClassification] = {}
        self._last_classification_time: float = 0.0
        self._last_market_count: int = 0

        # Price history ring buffers
        max_samples = int(self.config.vol_lookback_minutes * 60 / self.config.vol_sample_interval)
        self._price_history: Dict[str, deque] = {
            "BTC": deque(maxlen=max_samples),
            "ETH": deque(maxlen=max_samples),
        }
        self._last_sample_time: float = 0.0

        # Signal + execution tracking
        self._signals: List[SniperSignal] = []
        self._active_executions: Dict[str, SniperExecution] = {}
        self._completed_executions: List[SniperExecution] = []
        self._order_to_execution: Dict[str, str] = {}
        self._cooldown: Dict[str, float] = {}

        # Regime detector: track recent outcomes
        self._recent_outcomes: deque = deque(maxlen=30)  # rolling window of wins/losses
        self._regime_paused = False
        self._regime_pause_until: float = 0.0

        # Metrics — lightweight, primitive writes only
        self._m = {
            "total_scans": 0,
            "last_scan_time": None,
            "last_scan_duration_ms": 0.0,
            "markets_classified": 0,
            "classification_failures": 0,
            "classification_failure_reasons": {},
            "markets_evaluated": 0,
            "signals_generated": 0,
            "signals_rejected": 0,
            "signals_executed": 0,
            "signals_filled": 0,
            "rejection_reasons": {},
            "stale_feed_skips": 0,
            "btc_vol_samples": 0,
            "eth_vol_samples": 0,
            "btc_realized_vol": None,
            "eth_realized_vol": None,
            "active_executions": 0,
            "completed_executions": 0,
            "last_execution_time": None,
            "position_capped": 0,
            "dislocation_filtered": 0,
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
            f"CryptoSniper started "
            f"(interval={self.config.scan_interval}s, "
            f"min_edge={self.config.min_edge_bps}bps)"
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
        logger.info("CryptoSniper stopped")

    async def on_market_update(self, event):
        pass  # Uses own scan loop

    # ---- Scan Loop (5 stages) ----

    async def _scan_loop(self):
        await asyncio.sleep(5)  # let feeds settle
        while self._running:
            t0 = time.monotonic()
            try:
                # Stage 1: Sample prices
                self._sample_prices()

                # Stage 2: Refresh classifications if stale
                self._maybe_refresh_classifications()

                # Stage 2.5: Regime detector — adjust edge threshold based on recent WR
                self._regime_check()

                # Stage 3+4: Evaluate and filter signals
                signals = self._evaluate_all()

                # Stage 5: Execute eligible signals
                eligible = [s for s in signals if s.is_tradable]
                for sig in eligible:
                    if len(self._active_executions) >= self.config.max_concurrent_signals:
                        break
                    await self._execute_signal(sig)

                # Stage 6: Cleanup opposite-side positions (runs every scan)
                await self._cleanup_opposite_side_positions()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sniper scan error: {e}", exc_info=True)

            elapsed_ms = (time.monotonic() - t0) * 1000
            self._m["total_scans"] += 1
            self._m["last_scan_time"] = utc_now()
            self._m["last_scan_duration_ms"] = round(elapsed_ms, 2)

            await asyncio.sleep(self.config.scan_interval)

    # ---- Stage 1: Price Sampling ----

    def _sample_prices(self):
        now = time.time()
        if now - self._last_sample_time < self.config.vol_sample_interval:
            return
        self._last_sample_time = now

        for asset in ("BTC", "ETH"):
            # StateManager stores as "BTC" key from PriceFeedManager
            price = self._state.spot_prices.get(asset)
            if price and price > 0:
                self._price_history[asset].append((now, price))

        self._m["btc_vol_samples"] = len(self._price_history["BTC"])
        self._m["eth_vol_samples"] = len(self._price_history["ETH"])

    # ---- Stage 2: Classification Cache ----

    def _regime_check(self):
        """Regime detector: if rolling WR drops below 30%, double min_edge_bps.
        When WR recovers above 40%, restore normal min_edge_bps.
        Sends Telegram alert on state changes."""
        if not self._state:
            return

        # Check recent resolved trades (last 20+ crypto trades with PnL)
        recent_pnl = []
        for trade in reversed(self._state.trades):
            if trade.pnl is None:
                continue
            sid = trade.strategy_id or ""
            if "sniper" not in sid and "crypto" not in sid:
                continue
            recent_pnl.append(trade.pnl)
            if len(recent_pnl) >= 20:
                break

        if len(recent_pnl) < 10:
            return  # not enough data

        wins = sum(1 for p in recent_pnl if p > 0)
        wr = wins / len(recent_pnl)

        now = time.time()

        if wr < 0.30 and not self._regime_paused:
            # PAUSE — WR cratered, boost edge threshold
            self._regime_paused = True
            self._regime_pause_until = now + 1800  # at least 30 min
            self._m["regime_paused"] = True
            self._m["regime_wr"] = round(wr * 100, 1)
            logger.warning(
                f"[REGIME] PAUSED — WR={wr*100:.0f}% < 30% on last {len(recent_pnl)} trades. "
                f"Boosting min_edge_bps from {self.config.min_edge_bps} to {self.config.min_edge_bps * 2}"
            )

        elif wr >= 0.40 and self._regime_paused and now > self._regime_pause_until:
            # RESUME — WR recovered
            self._regime_paused = False
            self._m["regime_paused"] = False
            self._m["regime_wr"] = round(wr * 100, 1)
            logger.info(
                f"[REGIME] RESUMED — WR={wr*100:.0f}% > 40% on last {len(recent_pnl)} trades. "
                f"Restoring normal min_edge_bps={self.config.min_edge_bps}"
            )

    @property
    def _effective_min_edge_bps(self) -> float:
        """Return the effective min_edge_bps, doubled during regime pause."""
        base = self.config.min_edge_bps
        return base * 2 if self._regime_paused else base

    # ---- Stage 2 actual: Classification Cache ----

    def _maybe_refresh_classifications(self):
        now = time.monotonic()
        market_count = len(self._state.markets)
        needs_refresh = (
            now - self._last_classification_time >= self.config.classification_refresh_interval
            or market_count != self._last_market_count
        )
        if not needs_refresh:
            return

        self._classified_cache = self._classify_markets()
        self._last_classification_time = now
        self._last_market_count = market_count
        self._m["markets_classified"] = len(self._classified_cache)

    def _classify_markets(self) -> Dict[str, CryptoMarketClassification]:
        """Scan all markets, find binary crypto pairs, parse question text and slug."""
        # First, group by condition_id into binary pairs (same as ArbScanner)
        by_condition: Dict[str, Dict] = {}
        for snap in self._state.markets.values():
            cid = snap.condition_id
            if not cid:
                continue
            if cid not in by_condition:
                by_condition[cid] = {}
            out = (snap.outcome or "").upper()
            if "YES" in out or "UP" in out:
                by_condition[cid]["yes"] = snap
            elif "NO" in out or "DOWN" in out:
                by_condition[cid]["no"] = snap

        results = {}
        fail_reasons = {}

        for cid, pair in by_condition.items():
            if "yes" not in pair or "no" not in pair:
                continue

            yes_snap = pair["yes"]
            no_snap = pair["no"]

            classification, reason = classify_market_question(
                question=yes_snap.question,
                condition_id=cid,
                yes_token_id=yes_snap.token_id,
                no_token_id=no_snap.token_id,
                end_date=yes_snap.end_date,
                slug=yes_snap.slug,
            )

            if classification:
                results[cid] = classification
            elif reason:
                fail_reasons[reason] = fail_reasons.get(reason, 0) + 1

        self._m["classification_failures"] = sum(fail_reasons.values())
        self._m["classification_failure_reasons"] = fail_reasons
        return results

    # ---- Stage 3+4: Evaluate + Filter ----

    def _evaluate_all(self) -> List[SniperSignal]:
        results = []
        evaluated = 0

        # Pre-compute volatility and momentum once per scan (not per market)
        vol_cache = {}
        mom_cache = {}
        for asset in ("BTC", "ETH"):
            buf = self._price_history[asset]
            vol = compute_realized_volatility(buf, self.config.vol_min_samples)
            vol_cache[asset] = vol
            mom_cache[asset] = compute_momentum(buf, self.config.momentum_lookback_seconds)

            # Update metrics
            self._m[f"{asset.lower()}_realized_vol"] = vol

        # Expire old cooldowns
        now = time.time()
        self._cooldown = {
            cid: ts for cid, ts in self._cooldown.items()
            if now - ts < self.config.cooldown_seconds
        }

        for cid, cm in self._classified_cache.items():
            sig = self._evaluate_signal(cm, vol_cache, mom_cache, now)
            if sig:
                results.append(sig)

                # Shadow evaluation: feed ALL signals (tradable + rejected) for comparison
                if self._shadow:
                    try:
                        yes_snap = self._state.get_market(cm.yes_token_id)
                        no_snap = self._state.get_market(cm.no_token_id)
                        if yes_snap and no_snap:
                            yp = yes_snap.mid_price or 0
                            np_ = no_snap.mid_price or 0
                            fp = sig.fair_price if sig.fair_price > 0 else 0.5
                            self._shadow.evaluate_signal(
                                condition_id=cm.condition_id,
                                asset=cm.asset,
                                direction=cm.direction,
                                spot=sig.spot_price,
                                fair_prob=fp,
                                yes_price=yp,
                                no_price=np_,
                                edge_bps_yes=compute_edge_bps(fp, yp) if yp > 0 else 0,
                                edge_bps_no=compute_edge_bps(1.0 - fp, np_) if np_ > 0 else 0,
                                tte_seconds=sig.time_to_expiry_seconds,
                                volatility=sig.volatility if sig.volatility > 0 else (vol_cache.get(cm.asset) or 0),
                                live_decision=f"trade_{sig.side.replace('buy_', '')}" if sig.is_tradable else "skip",
                                live_rejection="" if sig.is_tradable else (sig.rejection_reason or ""),
                                token_id_yes=cm.yes_token_id,
                                token_id_no=cm.no_token_id,
                                question=cm.question,
                            )
                    except Exception:
                        pass  # shadow must never break live

                # MoonDev: feed same signal with window info
                if self._moondev:
                    try:
                        yes_snap = self._state.get_market(cm.yes_token_id)
                        no_snap = self._state.get_market(cm.no_token_id)
                        if yes_snap and no_snap:
                            yp = yes_snap.mid_price or 0
                            np_ = no_snap.mid_price or 0
                            fp = sig.fair_price if sig.fair_price > 0 else 0.5
                            self._moondev.evaluate_signal(
                                condition_id=cm.condition_id,
                                asset=cm.asset,
                                direction=cm.direction,
                                spot=sig.spot_price,
                                fair_prob=fp,
                                yes_price=yp,
                                no_price=np_,
                                edge_bps_yes=compute_edge_bps(fp, yp) if yp > 0 else 0,
                                edge_bps_no=compute_edge_bps(1.0 - fp, np_) if np_ > 0 else 0,
                                tte_seconds=sig.time_to_expiry_seconds,
                                volatility=sig.volatility if sig.volatility > 0 else (vol_cache.get(cm.asset) or 0),
                                live_decision=f"trade_{sig.side.replace('buy_', '')}" if sig.is_tradable else "skip",
                                live_rejection="" if sig.is_tradable else (sig.rejection_reason or ""),
                                token_id_yes=cm.yes_token_id,
                                token_id_no=cm.no_token_id,
                                question=cm.question,
                                window=cm.window,
                            )
                    except Exception:
                        pass  # moondev must never break live

            evaluated += 1

        self._m["markets_evaluated"] = evaluated

        # Prepend new signals, keep last 300
        self._signals = results + self._signals
        if len(self._signals) > 300:
            self._signals = self._signals[:300]

        return results

    def _evaluate_signal(
        self,
        cm: CryptoMarketClassification,
        vol_cache: Dict[str, Optional[float]],
        mom_cache: Dict[str, float],
        now: float,
    ) -> Optional[SniperSignal]:
        """Evaluate a single classified market. Returns SniperSignal or None."""

        # Window-aware position cap: short windows get smaller max positions
        window_caps = {"5m": 12, "15m": 22, "1h": 30}
        effective_cap = window_caps.get(cm.window, self._state.risk_config.max_position_size if self._state else 25.0)
        base_cap = self._state.risk_config.max_position_size if self._state else 25.0
        cap = min(effective_cap, base_cap)

        # Anti-clustering: skip markets where we already hold a near-cap position
        for token_id in (cm.yes_token_id, cm.no_token_id):
            existing = self._state.get_position(token_id) if self._state else None
            if existing and existing.size >= (cap - 1):
                self._m["position_capped"] += 1
                return None  # silent skip — no need to log every scan cycle

        # Get spot price
        spot = self._state.spot_prices.get(cm.asset)
        if not spot or spot <= 0:
            self._m["stale_feed_skips"] += 1
            return None

        # Check spot freshness
        stale_key = f"spot_{cm.asset.lower()}_stale"
        if self._state.health.get(stale_key, True):
            self._m["stale_feed_skips"] += 1
            return None

        # Time to expiry
        try:
            expiry_dt = datetime.fromisoformat(cm.expiry_utc)
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
            tte = (expiry_dt - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError):
            return None

        if tte < self.config.min_tte_seconds:
            return self._reject_signal(cm, spot, tte, 0, 0, 0, 0, 0,
                                       f"tte {tte:.0f}s < min {self.config.min_tte_seconds}s")
        if tte > self.config.max_tte_seconds:
            return self._reject_signal(cm, spot, tte, 0, 0, 0, 0, 0,
                                       f"tte {tte:.0f}s > max {self.config.max_tte_seconds}s")

        # Volatility
        vol = vol_cache.get(cm.asset)
        if vol is None:
            return self._reject_signal(cm, spot, tte, 0, 0, 0, 0, 0,
                                       "insufficient_vol_data")

        # Momentum
        momentum = mom_cache.get(cm.asset, 0.0)

        # Market prices
        yes_snap = self._state.get_market(cm.yes_token_id)
        no_snap = self._state.get_market(cm.no_token_id)
        if not yes_snap or not no_snap:
            return None

        yes_price = yes_snap.mid_price or 0
        no_price = no_snap.mid_price or 0
        if yes_price <= 0 or no_price <= 0:
            return None

        # Market freshness
        data_age = max(compute_data_age(yes_snap.updated_at), compute_data_age(no_snap.updated_at))
        if data_age > self.config.max_stale_age_seconds:
            return self._reject_signal(cm, spot, tte, vol, momentum, yes_price, data_age, 0,
                                       f"stale_data {data_age:.0f}s")

        # Spread check
        spread = abs(1.0 - (yes_price + no_price))
        if spread > self.config.max_spread:
            return self._reject_signal(cm, spot, tte, vol, momentum, yes_price, data_age, spread,
                                       f"spread {spread:.3f} > max {self.config.max_spread}")

        # Liquidity
        liquidity = min(yes_snap.liquidity, no_snap.liquidity)
        if liquidity < self.config.min_liquidity:
            return self._reject_signal(cm, spot, tte, vol, momentum, yes_price, data_age, spread,
                                       f"liquidity {liquidity:.0f} < min {self.config.min_liquidity}")

        # Cooldown
        if cm.condition_id in self._cooldown:
            return None

        # ---- Fair probability ----
        # For updown markets (strike=0), use current spot as strike
        effective_strike = cm.strike if cm.strike > 0 else spot
        fair = compute_fair_probability(
            spot=spot,
            strike=effective_strike,
            vol=vol,
            tte_seconds=tte,
            direction=cm.direction,
            momentum=momentum,
            momentum_weight=self.config.momentum_weight,
            vol_floor=self.config.vol_floor,
        )

        # Edge calculation: check both sides
        edge_yes = compute_edge_bps(fair, yes_price)           # buy Yes if positive
        edge_no = compute_edge_bps(1.0 - fair, no_price)       # buy No if positive

        # Pick the better side
        if edge_yes >= edge_no and edge_yes > 0:
            side, token_id, edge_bps, market_price = "buy_yes", cm.yes_token_id, edge_yes, yes_price
        elif edge_no > 0:
            side, token_id, edge_bps, market_price = "buy_no", cm.no_token_id, edge_no, no_price
        else:
            # No positive edge
            return self._reject_signal(cm, spot, tte, vol, momentum, yes_price, data_age, spread,
                                       f"no_edge yes={edge_yes:.0f}bps no={edge_no:.0f}bps")

        # Edge threshold (regime-aware)
        effective_min_edge = self._effective_min_edge_bps
        if edge_bps < effective_min_edge:
            return self._reject_signal(cm, spot, tte, vol, momentum, market_price, data_age, spread,
                                       f"edge {edge_bps:.0f}bps < min {effective_min_edge:.0f}bps")

        # Minimum dislocation filter: skip coin-flip entries near 0.50
        dislocation = abs(fair - market_price)
        if dislocation < 0.03:
            self._m["dislocation_filtered"] += 1
            return self._reject_signal(cm, spot, tte, vol, momentum, market_price, data_age, spread,
                                       f"dislocation {dislocation:.4f} < 0.03 (too close to coin-flip)")

        # Confidence
        vol_quality = len(self._price_history[cm.asset]) / self.config.vol_min_samples
        confidence = compute_signal_confidence(
            liquidity=liquidity,
            data_age_seconds=data_age,
            spread=spread,
            vol_quality=vol_quality,
            tte_seconds=tte,
            min_tte=self.config.min_tte_seconds,
            max_tte=self.config.max_tte_seconds,
        )

        if confidence < self.config.min_confidence:
            return self._reject_signal(cm, spot, tte, vol, momentum, market_price, data_age, spread,
                                       f"confidence {confidence:.3f} < min {self.config.min_confidence}")

        # Kill switch
        if self._state.risk_config.kill_switch_active:
            return self._reject_signal(cm, spot, tte, vol, momentum, market_price, data_age, spread,
                                       "kill_switch_active")

        # Concurrency check
        if len(self._active_executions) >= self.config.max_concurrent_signals:
            return self._reject_signal(cm, spot, tte, vol, momentum, market_price, data_age, spread,
                                       "max_concurrent_signals")

        # ---- Signal is tradable ----
        # Dynamic sizing: scale with edge magnitude (Kelly-inspired)
        if edge_bps >= 1200:
            size = 35.0
        elif edge_bps >= 900:
            size = 25.0
        elif edge_bps >= 600:
            size = 18.0
        elif edge_bps >= 400:
            size = 12.0
        else:
            size = 5.0
        # Respect window cap and config ceiling
        size = min(size, cap, self.config.max_signal_size)

        signal = SniperSignal(
            condition_id=cm.condition_id,
            asset=cm.asset,
            direction=cm.direction,
            strike=cm.strike,
            expiry_utc=cm.expiry_utc,
            spot_price=round(spot, 2),
            market_price=round(market_price, 6),
            fair_price=round(fair, 6),
            edge_bps=edge_bps,
            volatility=round(vol, 6),
            time_to_expiry_seconds=round(tte, 1),
            momentum=round(momentum, 6),
            confidence=confidence,
            side=side,
            token_id=token_id,
            recommended_size=size,
            is_tradable=True,
        )

        self._m["signals_generated"] += 1
        logger.info(
            f"[SNIPER] Signal: {cm.asset} {cm.direction} ${cm.strike} "
            f"spot=${spot:.2f} fair={fair:.4f} mkt={market_price:.4f} "
            f"edge={edge_bps:.0f}bps conf={confidence:.3f} side={side}"
        )
        return signal

    def _reject_signal(self, cm, spot, tte, vol, momentum, mkt_price, data_age, spread, reason):
        """Create a rejected signal for the log and update metrics."""
        self._m["signals_rejected"] += 1
        bucket = reason.split(" ")[0] if reason else "unknown"
        self._m["rejection_reasons"][bucket] = self._m["rejection_reasons"].get(bucket, 0) + 1
        if self._tracker:
            self._tracker.record_signal(self.strategy_id, False, bucket)

        return SniperSignal(
            condition_id=cm.condition_id,
            asset=cm.asset,
            direction=cm.direction,
            strike=cm.strike,
            expiry_utc=cm.expiry_utc,
            spot_price=round(spot, 2) if spot else 0,
            market_price=round(mkt_price, 6) if mkt_price else 0,
            fair_price=0,
            edge_bps=0,
            volatility=round(vol, 6) if vol else 0,
            time_to_expiry_seconds=round(tte, 1) if tte else 0,
            momentum=round(momentum, 6) if momentum else 0,
            confidence=0,
            side="none",
            token_id="",
            recommended_size=0,
            is_tradable=False,
            rejection_reason=reason,
        )

    # ---- Stage 5: Execution ----

    async def _execute_signal(self, signal: SniperSignal):
        if not self._risk_engine or not self._execution_engine:
            logger.warning("No execution context; skipping signal")
            return

        # Prevent opening both sides of the same market simultaneously
        # RE-ACTIVATED: Forensic analysis showed best period (M2→D, $56.28/h) had this active.
        # With it removed (D→E), PnL/trade collapsed from $0.221 to $0.003.
        cm = self._classified_cache.get(signal.condition_id)
        if cm:
            opposite_token = cm.no_token_id if signal.side == "buy_yes" else cm.yes_token_id
            if opposite_token and opposite_token in self._state.positions:
                signal.is_tradable = False
                signal.rejection_reason = "opposite_side_held"
                self._m["signals_rejected"] += 1
                self._m["rejection_reasons"]["opposite_side_held"] = self._m["rejection_reasons"].get("opposite_side_held", 0) + 1
                if self._tracker:
                    self._tracker.record_signal(self.strategy_id, False, "opposite_side_held")
                logger.info(
                    f"[SNIPER] Blocked opposite-side trade: {signal.asset} {signal.side} "
                    f"(already hold {opposite_token[:16]}..)"
                )
                return

        order = OrderRecord(
            token_id=signal.token_id,
            side=OrderSide.BUY,
            price=signal.market_price,
            size=signal.recommended_size,
            strategy_id=self.strategy_id,
        )

        ok, reason = self._risk_engine.check_order(order)
        if not ok:
            signal.is_tradable = False
            signal.rejection_reason = f"risk: {reason}"
            self._m["signals_rejected"] += 1
            risk_bucket = f"risk:{reason.split('(')[0].strip()}"
            self._m["rejection_reasons"][risk_bucket] = self._m["rejection_reasons"].get(risk_bucket, 0) + 1
            if self._tracker:
                self._tracker.record_signal(self.strategy_id, False, risk_bucket)
            return

        execution = SniperExecution(
            signal_id=signal.id,
            condition_id=signal.condition_id,
            question=signal.asset + " " + signal.direction + " $" + str(signal.strike),
            asset=signal.asset,
            side=signal.side,
            order_id=order.id,
            target_edge_bps=signal.edge_bps,
            size=signal.recommended_size,
        )

        self._active_executions[execution.id] = execution
        self._order_to_execution[order.id] = execution.id
        self._cooldown[signal.condition_id] = time.time()
        self._m["signals_executed"] += 1
        self._m["active_executions"] = len(self._active_executions)

        # Track in strategy tracker
        if self._tracker:
            self._tracker.record_signal(self.strategy_id, True)

        # Emit signal event for notification system (non-blocking)
        await self._bus.emit(Event(
            type=EventType.SIGNAL,
            source=self.strategy_id,
            data={
                "strategy": "SNIPER", "asset": signal.asset,
                "strike": signal.strike, "fair_price": signal.fair_price,
                "market_price": signal.market_price, "edge_bps": signal.edge_bps,
                "side": signal.side,
            },
        ))

        logger.info(
            f"[SNIPER] Executing: {signal.asset} {signal.side} "
            f"price={signal.market_price:.4f} size={signal.recommended_size} "
            f"edge={signal.edge_bps:.0f}bps"
        )

        try:
            await self._execution_engine.submit_order(order)
        except Exception as e:
            logger.error(f"Sniper execution error: {e}")
            execution.status = SniperSignalStatus.REJECTED
            self._finalize_execution(execution)

    # ---- Fill Tracking ----

    async def _cleanup_opposite_side_positions(self):
        """Detect and close weaker side of opposite-side positions on the same market."""
        if not self._state or not self._execution_engine:
            return

        # Group positions by condition_id
        by_condition: Dict[str, List] = defaultdict(list)
        for token_id, pos in self._state.positions.items():
            sid = getattr(pos, "strategy_id", "") or ""
            if "crypto" not in sid and "sniper" not in sid:
                continue
            # Find the condition_id for this token
            for cid, cm in self._classified_cache.items():
                if cm.yes_token_id == token_id or cm.no_token_id == token_id:
                    side = "yes" if cm.yes_token_id == token_id else "no"
                    by_condition[cid].append((token_id, pos, side))
                    break

        closed = 0
        for cid, positions_list in by_condition.items():
            if len(positions_list) < 2:
                continue

            yes_pos = [(tid, p) for tid, p, s in positions_list if s == "yes"]
            no_pos = [(tid, p) for tid, p, s in positions_list if s == "no"]

            if not yes_pos or not no_pos:
                continue

            # Both sides held — close the weaker one (lower unrealized PnL)
            for y_tid, y_p in yes_pos:
                for n_tid, n_p in no_pos:
                    y_pnl = (y_p.current_price - y_p.avg_cost) * y_p.size
                    n_pnl = (n_p.current_price - n_p.avg_cost) * n_p.size

                    # Close the weaker side
                    if y_pnl <= n_pnl:
                        close_tid, close_pos = y_tid, y_p
                        kept_side = "NO"
                    else:
                        close_tid, close_pos = n_tid, n_p
                        kept_side = "YES"

                    close_price = close_pos.current_price or close_pos.avg_cost
                    pnl = round((close_price - close_pos.avg_cost) * close_pos.size, 4)

                    trade = TradeRecord(
                        id=new_id(),
                        order_id="opposite_side_cleanup",
                        token_id=close_tid,
                        market_question=close_pos.market_question,
                        outcome=f"closed_weaker_side:kept_{kept_side}",
                        side=OrderSide.SELL,
                        price=close_price,
                        size=close_pos.size,
                        fees=0.0,
                        pnl=pnl,
                        strategy_id=getattr(close_pos, "strategy_id", self.strategy_id),
                        signal_reason="opposite_side_cleanup",
                    )
                    self._state.add_trade(trade)
                    self._state.positions.pop(close_tid, None)
                    closed += 1

                    logger.warning(
                        f"[SNIPER-CLEANUP] Closed opposite-side position: {close_pos.market_question[:40]}.. "
                        f"kept={kept_side} pnl=${pnl:+.4f}"
                    )

        if closed > 0:
            self._m["opposite_side_cleanups"] = self._m.get("opposite_side_cleanups", 0) + closed

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

        status = event.data.get("status")
        fill_price = event.data.get("fill_price")

        if status == "filled":
            execution.status = SniperSignalStatus.FILLED
            execution.entry_price = fill_price
            execution.filled_at = utc_now()
            self._m["signals_filled"] += 1
            self._m["last_execution_time"] = utc_now()
            logger.info(
                f"[SNIPER] FILLED: {execution.asset} {execution.side} "
                f"fill={fill_price:.4f} target_edge={execution.target_edge_bps:.0f}bps"
            )
            self._finalize_execution(execution)

        elif status in ("rejected", "cancelled"):
            execution.status = SniperSignalStatus.REJECTED
            logger.warning(f"[SNIPER] Order {order_id[:8]} {status}")
            self._finalize_execution(execution)

    def _finalize_execution(self, execution: SniperExecution):
        self._active_executions.pop(execution.id, None)
        self._completed_executions.append(execution)
        if len(self._completed_executions) > 200:
            self._completed_executions = self._completed_executions[-200:]
        self._order_to_execution.pop(execution.order_id, None)
        self._m["active_executions"] = len(self._active_executions)
        self._m["completed_executions"] = len(self._completed_executions)

    # ---- API Data Accessors ----

    def get_signals(self, limit: int = 50) -> List[dict]:
        return [s.model_dump() for s in self._signals[:limit]]

    def get_active_executions(self) -> List[dict]:
        return [e.model_dump() for e in self._active_executions.values()]

    def get_completed_executions(self, limit: int = 50) -> List[dict]:
        return [e.model_dump() for e in self._completed_executions[-limit:]]

    def get_health(self) -> dict:
        pnl = self._compute_pnl()
        return {
            **self._m,
            "config": self.config.model_dump(),
            "running": self._running,
            "regime_paused": self._regime_paused,
            "effective_min_edge_bps": self._effective_min_edge_bps,
            "price_buffer_sizes": {
                "BTC": len(self._price_history["BTC"]),
                "ETH": len(self._price_history["ETH"]),
            },
            "pnl": pnl,
        }

    def _compute_pnl(self) -> dict:
        """Compute sniper PnL from filled executions + current market prices."""
        if not self._state:
            return {"realized": 0, "unrealized": 0, "total": 0, "positions": 0, "fills": 0}

        fills = [e for e in self._completed_executions if e.status == SniperSignalStatus.FILLED]
        unrealized = 0.0
        positions = 0

        for ex in fills:
            if not ex.entry_price:
                continue
            # Find current market price for the token
            cm = self._classified_cache.get(ex.condition_id)
            if not cm:
                continue
            token_id = cm.yes_token_id if ex.side == "buy_yes" else cm.no_token_id
            snap = self._state.get_market(token_id)
            if snap and snap.mid_price and snap.mid_price > 0:
                unrealized += (snap.mid_price - ex.entry_price) * ex.size
                positions += 1

        return {
            "realized": 0,
            "unrealized": round(unrealized, 4),
            "total": round(unrealized, 4),
            "positions": positions,
            "fills": len(fills),
        }

    def get_config(self) -> StrategyConfig:
        return StrategyConfig(
            strategy_id=self.strategy_id,
            name=self.name,
            enabled=self._running,
            status=StrategyStatusEnum.ACTIVE if self._running else StrategyStatusEnum.STOPPED,
            parameters=self.config.model_dump(),
        )
