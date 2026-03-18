"""Configuration persistence service.

Reads/writes engine configuration to MongoDB `configs` collection.
Single document with _id="engine_config" using upsert pattern.
On startup, loads persisted config and applies to engine state.
On update, writes to MongoDB and updates in-memory state.
"""

import logging
from typing import Any, Dict, Optional

from models import utc_now

logger = logging.getLogger(__name__)

CONFIG_DOC_ID = "engine_config"


class ConfigService:
    def __init__(self, db):
        self._db = db
        self._collection = db["configs"]
        self._cache: Dict[str, Any] = {}

    async def load(self) -> Dict[str, Any]:
        """Load config from MongoDB. Returns empty dict if none exists."""
        doc = await self._collection.find_one(
            {"_id": CONFIG_DOC_ID}, {"_id": 0}
        )
        if doc:
            self._cache = doc
            logger.info("Configuration loaded from MongoDB")
        else:
            self._cache = {}
            logger.info("No persisted configuration found, using defaults")
        return self._cache

    async def save(self, config: Dict[str, Any]):
        """Persist full config document to MongoDB."""
        config["updated_at"] = utc_now()
        await self._collection.update_one(
            {"_id": CONFIG_DOC_ID},
            {"$set": config},
            upsert=True,
        )
        self._cache = config
        logger.info("Configuration persisted to MongoDB")

    async def patch(self, updates: Dict[str, Any]):
        """Partial update — merge updates into existing config."""
        updates["updated_at"] = utc_now()
        await self._collection.update_one(
            {"_id": CONFIG_DOC_ID},
            {"$set": updates},
            upsert=True,
        )
        self._cache.update(updates)

    @property
    def cached(self) -> Dict[str, Any]:
        return self._cache

    def build_snapshot(self, state, telegram_notifier, arb_ref, sniper_ref, weather_ref=None) -> Dict[str, Any]:
        """Build a full config snapshot from current in-memory state."""
        snapshot = {
            "trading_mode": state.trading_mode.value,
            "telegram_enabled": telegram_notifier._enabled if telegram_notifier else False,
            "telegram_signals_enabled": telegram_notifier._signals_enabled if telegram_notifier else False,
            "risk": state.risk_config.model_dump(),
            "strategies": {},
        }

        if arb_ref:
            snapshot["strategies"]["arb_scanner"] = {
                "enabled": state.strategies.get("arb_scanner", None) and state.strategies["arb_scanner"].enabled,
                **arb_ref.config.model_dump(),
            }
        if sniper_ref:
            snapshot["strategies"]["crypto_sniper"] = {
                "enabled": state.strategies.get("crypto_sniper", None) and state.strategies["crypto_sniper"].enabled,
                **sniper_ref.config.model_dump(),
            }
        if weather_ref:
            snapshot["strategies"]["weather_trader"] = {
                "enabled": state.strategies.get("weather_trader", None) and state.strategies["weather_trader"].enabled,
                **weather_ref.config.model_dump(),
            }

        return snapshot

    def apply_to_engine(self, config, state, telegram_notifier, arb_ref, sniper_ref, weather_ref=None):
        """Apply a loaded config dict to the live engine state."""
        from models import TradingMode, RiskConfig

        if not config:
            return

        # Trading mode
        mode_str = config.get("trading_mode")
        if mode_str:
            try:
                state.trading_mode = TradingMode(mode_str)
            except ValueError:
                pass

        # Telegram
        if telegram_notifier:
            telegram_notifier.configure(
                enabled=config.get("telegram_enabled", False),
                signals_enabled=config.get("telegram_signals_enabled", False),
            )

        # Risk
        risk_dict = config.get("risk")
        if risk_dict:
            try:
                # Migrate old defaults so multi-strategy trading works
                if risk_dict.get("max_concurrent_positions", 0) <= 10:
                    new_default = RiskConfig().max_concurrent_positions
                    risk_dict["max_concurrent_positions"] = new_default
                    logger.info(
                        f"[CONFIG] Migrated max_concurrent_positions → {new_default}"
                    )
                # Ensure new per-strategy fields exist
                for field in ("max_weather_positions",
                              "min_market_freshness_seconds", "max_spread_bps",
                              "max_size_to_liquidity_ratio",
                              "crypto_max_exposure", "weather_max_exposure",
                              "arb_max_exposure", "arb_reserved_capital"):
                    if field not in risk_dict:
                        risk_dict[field] = getattr(RiskConfig(), field)
                # Remove unknown fields that may exist in persisted config
                known_fields = set(RiskConfig.model_fields.keys())
                risk_dict = {k: v for k, v in risk_dict.items() if k in known_fields}
                state.risk_config = RiskConfig(**risk_dict)
            except Exception as e:
                logger.warning(f"Failed to apply risk config: {e}")

        # Strategy configs
        strats = config.get("strategies", {})

        if arb_ref and "arb_scanner" in strats:
            arb_data = strats["arb_scanner"]
            enabled = arb_data.pop("enabled", None)
            if enabled is not None and "arb_scanner" in state.strategies:
                state.strategies["arb_scanner"].enabled = enabled
            try:
                from engine.strategies.arb_models import ArbConfig
                known = set(ArbConfig.model_fields.keys())
                filtered = {k: v for k, v in arb_data.items() if k in known}
                arb_ref.config = ArbConfig(**{**arb_ref.config.model_dump(), **filtered})
            except Exception as e:
                logger.warning(f"Failed to apply arb config: {e}")

        if sniper_ref and "crypto_sniper" in strats:
            sniper_data = strats["crypto_sniper"]
            enabled = sniper_data.pop("enabled", None)
            if enabled is not None and "crypto_sniper" in state.strategies:
                state.strategies["crypto_sniper"].enabled = enabled
            try:
                from engine.strategies.sniper_models import SniperConfig
                known = set(SniperConfig.model_fields.keys())
                filtered = {k: v for k, v in sniper_data.items() if k in known}
                sniper_ref.config = SniperConfig(**{**sniper_ref.config.model_dump(), **filtered})
            except Exception as e:
                logger.warning(f"Failed to apply sniper config: {e}")

        if weather_ref and "weather_trader" in strats:
            weather_data = strats["weather_trader"]
            enabled = weather_data.pop("enabled", None)
            if enabled is not None and "weather_trader" in state.strategies:
                state.strategies["weather_trader"].enabled = enabled
            try:
                from engine.strategies.weather_models import WeatherConfig
                known = set(WeatherConfig.model_fields.keys())
                filtered = {k: v for k, v in weather_data.items() if k in known}
                weather_ref.config = WeatherConfig(**{**weather_ref.config.model_dump(), **filtered})
            except Exception as e:
                logger.warning(f"Failed to apply weather config: {e}")

        logger.info("Configuration applied to engine")
