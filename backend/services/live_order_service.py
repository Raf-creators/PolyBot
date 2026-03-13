"""Persistence for live CLOB order tracking.

Stores LiveOrderRecord documents in MongoDB `live_orders` collection.
Provides CRUD + query for open/partial orders that need status polling.
"""

import logging
from typing import Dict, List, Optional

from models import LiveOrderRecord, utc_now

logger = logging.getLogger(__name__)


class LiveOrderService:
    def __init__(self, db):
        self._db = db
        self._collection = db["live_orders"]
        # In-memory cache of active orders for fast lookup
        self._active: Dict[str, LiveOrderRecord] = {}

    async def save(self, record: LiveOrderRecord):
        """Upsert a live order record."""
        doc = record.model_dump()
        doc["_id"] = record.id
        await self._collection.update_one(
            {"_id": record.id},
            {"$set": {k: v for k, v in doc.items() if k != "_id"}},
            upsert=True,
        )
        if record.status in ("submitted", "open", "partially_filled"):
            self._active[record.id] = record
        else:
            self._active.pop(record.id, None)

    async def update_status(self, record_id: str, **kwargs):
        """Partial update on a live order."""
        kwargs["last_checked_at"] = utc_now()
        await self._collection.update_one(
            {"_id": record_id},
            {"$set": kwargs},
        )
        if record_id in self._active:
            for k, v in kwargs.items():
                if hasattr(self._active[record_id], k):
                    setattr(self._active[record_id], k, v)
            # Remove from active if terminal
            status = kwargs.get("status", self._active[record_id].status)
            if status in ("filled", "cancelled", "rejected", "expired"):
                self._active.pop(record_id, None)

    async def load_active(self) -> List[LiveOrderRecord]:
        """Load all non-terminal orders from MongoDB on startup."""
        cursor = self._collection.find(
            {"status": {"$in": ["submitted", "open", "partially_filled"]}},
            {"_id": 0},
        )
        self._active.clear()
        async for doc in cursor:
            try:
                rec = LiveOrderRecord(**doc)
                self._active[rec.id] = rec
            except Exception as e:
                logger.warning(f"Skipping malformed live order: {e}")
        logger.info(f"Loaded {len(self._active)} active live orders from MongoDB")
        return list(self._active.values())

    async def get_recent(self, limit: int = 50) -> List[dict]:
        """Get recent live orders (all statuses), newest first."""
        cursor = self._collection.find(
            {}, {"_id": 0}
        ).sort("submitted_at", -1).limit(limit)
        return [doc async for doc in cursor]

    async def get_by_exchange_id(self, exchange_order_id: str) -> Optional[dict]:
        return await self._collection.find_one(
            {"exchange_order_id": exchange_order_id}, {"_id": 0}
        )

    @property
    def active_orders(self) -> Dict[str, LiveOrderRecord]:
        return self._active

    @property
    def open_count(self) -> int:
        return sum(1 for r in self._active.values() if r.status in ("submitted", "open"))

    @property
    def partial_count(self) -> int:
        return sum(1 for r in self._active.values() if r.status == "partially_filled")
