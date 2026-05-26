"""
Casa de Pizza & Wings — In-memory order store
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

class OrderStore:
    def __init__(self):
        self._orders: Dict[str, dict] = {}

    def save(self, order: dict) -> str:
        order_id = order.get("order_id", "")
        self._orders[order_id] = order
        logger.info(f"Order saved: {order_id} | status={order.get('status')}")
        return order_id

    def get(self, order_id: str) -> Optional[dict]:
        return self._orders.get(order_id)

    def get_by_session(self, session_id: str) -> Optional[dict]:
        for order in self._orders.values():
            if order.get("session_id") == session_id:
                return order
        return None

    def update_status(self, order_id: str, status: str, extra: dict = None):
        if order_id in self._orders:
            self._orders[order_id]["status"] = status
            self._orders[order_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            if extra:
                self._orders[order_id].update(extra)
            logger.info(f"Order {order_id} status → {status}")

    def list_recent(self, limit: int = 20) -> List[dict]:
        orders = sorted(
            self._orders.values(),
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )
        return orders[:limit]

    def count(self) -> int:
        return len(self._orders)
