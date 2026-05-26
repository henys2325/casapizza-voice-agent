"""
Casa de Pizza & Wings — Clover POS Service
Handles order creation in Clover POS.
"""
import os
import requests
import logging

logger = logging.getLogger(__name__)

class CloverService:
    def __init__(self):
        self.merchant_id = os.getenv("CLOVER_MERCHANT_ID", "")
        self.api_token = os.getenv("CLOVER_API_TOKEN", "")
        self.base_url = os.getenv("CLOVER_BASE_URL", "https://api.clover.com")
        self.enabled = bool(self.merchant_id and self.api_token)
        if self.enabled:
            logger.info(f"Clover service initialized for merchant: {self.merchant_id}")
        else:
            logger.warning("Clover service disabled — missing CLOVER_MERCHANT_ID or CLOVER_API_TOKEN")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

    def create_order(self, items: list, order_type: str = "takeout", customer_name: str = "", note: str = "") -> dict:
        """Create an order in Clover POS."""
        if not self.enabled:
            logger.warning("Clover disabled — skipping order creation")
            return {"success": False, "error": "Clover not configured"}

        try:
            # Step 1: Create the order
            order_payload = {
                "title": f"{order_type.upper()} - {customer_name}".strip(" -"),
                "note": note,
                "orderType": {"id": "takeout"},
                "employee": {"id": "online"}
            }
            r = requests.post(
                f"{self.base_url}/v3/merchants/{self.merchant_id}/orders",
                headers=self._headers(),
                json=order_payload,
                timeout=15
            )
            r.raise_for_status()
            order = r.json()
            order_id = order["id"]
            logger.info(f"Clover order created: {order_id}")

            # Step 2: Add line items
            for item in items:
                line_item = {
                    "name": item.get("name", "Item"),
                    "price": int(item.get("unit_price", 0) * 100),  # cents
                    "unitQty": item.get("quantity", 1) * 1000
                }
                requests.post(
                    f"{self.base_url}/v3/merchants/{self.merchant_id}/orders/{order_id}/line_items",
                    headers=self._headers(),
                    json=line_item,
                    timeout=10
                )

            return {"success": True, "order_id": order_id, "clover_order": order}

        except Exception as e:
            logger.error(f"Clover order creation failed: {e}")
            return {"success": False, "error": str(e)}

    def get_order(self, order_id: str) -> dict:
        """Get order details from Clover."""
        if not self.enabled:
            return {}
        try:
            r = requests.get(
                f"{self.base_url}/v3/merchants/{self.merchant_id}/orders/{order_id}",
                headers=self._headers(),
                timeout=10
            )
            return r.json()
        except Exception as e:
            logger.error(f"Clover get order failed: {e}")
            return {}
