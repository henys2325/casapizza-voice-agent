"""
Menu Sync Service for Casa de Pizza & Wings AI Voice Agent (Noa)
Connects to the web API at casadepizzawingsnellis.com/api/menu
and keeps the menu updated in real-time (< 3 seconds).

Strategy:
- Cache the menu in memory with a TTL of 3 seconds
- On each call/request, check if cache is stale
- If stale, fetch fresh data from the API
- If API is down, fall back to local menu.json
- Prices from API are in CENTS, convert to dollars for Noa
"""

import asyncio
import time
import json
import os
import logging
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger(__name__)

# Configuration
MENU_API_URL = os.getenv("MENU_API_URL", "https://casadepizzawingsnellis.com/api/menu")
CACHE_TTL_SECONDS = 3  # Menu updates within 3 seconds
FALLBACK_MENU_PATH = os.path.join(os.path.dirname(__file__), "menu.json")
REQUEST_TIMEOUT = 5  # seconds


class MenuSyncService:
    """Real-time menu synchronization service."""

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0
        self._fallback_menu: Optional[Dict[str, Any]] = None
        self._lock = asyncio.Lock()
        self._http_client: Optional[httpx.AsyncClient] = None
        self._load_fallback()

    def _load_fallback(self):
        """Load the local menu.json as fallback."""
        try:
            with open(FALLBACK_MENU_PATH, "r") as f:
                self._fallback_menu = json.load(f)
            logger.info("Fallback menu loaded from menu.json")
        except Exception as e:
            logger.error(f"Failed to load fallback menu: {e}")
            self._fallback_menu = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        return self._http_client

    def _is_cache_valid(self) -> bool:
        """Check if cached menu is still fresh."""
        if self._cache is None:
            return False
        return (time.time() - self._cache_timestamp) < CACHE_TTL_SECONDS

    async def fetch_menu_from_api(self) -> Optional[Dict[str, Any]]:
        """Fetch fresh menu data from the web API."""
        try:
            client = await self._get_client()
            response = await client.get(MENU_API_URL)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Menu fetched from API: {len(data.get('categories', []))} categories")
                return data
            else:
                logger.warning(f"Menu API returned status {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch menu from API: {e}")
            return None

    async def get_menu(self) -> Dict[str, Any]:
        """Get the current menu (from cache, API, or fallback)."""
        # Return cache if valid
        if self._is_cache_valid():
            return self._cache

        # Fetch fresh data
        async with self._lock:
            # Double-check after acquiring lock
            if self._is_cache_valid():
                return self._cache

            api_data = await self.fetch_menu_from_api()
            if api_data:
                self._cache = api_data
                self._cache_timestamp = time.time()
                return self._cache
            elif self._cache:
                # API failed but we have stale cache — use it
                logger.warning("Using stale cache (API unavailable)")
                return self._cache
            else:
                # No cache, no API — use fallback
                logger.warning("Using fallback menu.json (API unavailable, no cache)")
                return self._fallback_menu

    async def get_menu_for_noa(self) -> str:
        """Get menu formatted as a string for Noa's system prompt / tool response."""
        menu_data = await self.get_menu()
        return self._format_menu_for_ai(menu_data)

    def _format_menu_for_ai(self, menu_data: Dict[str, Any]) -> str:
        """Format API menu data into a readable string for the AI agent."""
        if not menu_data or "categories" not in menu_data:
            return self._format_fallback_menu()

        lines = []
        lines.append("=== CASA DE PIZZA & WINGS — CURRENT MENU ===\n")

        # Restaurant info
        restaurant = menu_data.get("restaurant", {})
        lines.append(f"Phone: {restaurant.get('phone', '(702) 200-5252')}")
        lines.append(f"Hours: {restaurant.get('hours', {}).get('everyday', '10 AM - 10 PM')}")
        lines.append(f"Address: {restaurant.get('address', {}).get('street', '765 N Nellis Blvd, Suite 10')}\n")

        price_unit = menu_data.get("priceUnit", "cents")

        for category in menu_data.get("categories", []):
            cat_name = category.get("name", "")
            cat_emoji = category.get("emoji", "")
            is_lunch = category.get("isLunchSpecial", False)

            lines.append(f"\n{'='*50}")
            lines.append(f"{cat_emoji} {cat_name}")
            if is_lunch:
                lines.append("  ⏰ Available 10:00 AM – 3:00 PM only")
            lines.append(f"{'='*50}")

            for item in category.get("items", []):
                if not item.get("available", True):
                    continue

                name = item.get("name", "")
                price = item.get("price", 0)
                desc = item.get("description", "")
                item_type = item.get("itemType", "")
                piece_count = item.get("pieceCount")

                # Convert cents to dollars
                if price_unit == "cents":
                    price_dollars = price / 100
                else:
                    price_dollars = price

                price_str = f"${price_dollars:.2f}"

                # Check for modifier groups (sizes, etc.)
                modifiers = item.get("modifierGroups", [])
                size_info = ""
                for mod_group in modifiers:
                    if mod_group.get("name", "").lower() == "size":
                        sizes = []
                        for mod in mod_group.get("modifiers", []):
                            mod_price = mod.get("price", 0)
                            if price_unit == "cents":
                                total = (price + mod_price) / 100
                            else:
                                total = price + mod_price
                            sizes.append(f"{mod['name']}: ${total:.2f}")
                        size_info = " | ".join(sizes)

                if size_info:
                    lines.append(f"\n  {name}")
                    if desc:
                        lines.append(f"    {desc}")
                    lines.append(f"    Sizes: {size_info}")
                else:
                    lines.append(f"\n  {name} — {price_str}")
                    if desc:
                        lines.append(f"    {desc}")

                if piece_count:
                    lines.append(f"    ({piece_count} pieces)")

        # Wings sauces
        wings_data = menu_data.get("wings", {})
        if wings_data:
            sauces = wings_data.get("sauces", [])
            if sauces:
                lines.append(f"\n{'='*50}")
                lines.append("🌶️ WING SAUCES AVAILABLE")
                lines.append(f"{'='*50}")
                sauce_names = [s.get("name", "") for s in sauces]
                lines.append(f"  {', '.join(sauce_names)}")

                rules = wings_data.get("rules", {})
                if rules.get("halfAndHalfMinPieces"):
                    lines.append(f"  Half & Half available on {rules['halfAndHalfMinPieces']}+ pieces")

        # Toppings
        toppings_data = menu_data.get("toppings", {})
        if toppings_data:
            lines.append(f"\n{'='*50}")
            lines.append("🧀 PIZZA TOPPINGS")
            lines.append(f"{'='*50}")
            free_toppings = toppings_data.get("free", [])
            if free_toppings:
                topping_names = [t.get("name", "") for t in free_toppings]
                lines.append(f"  Available: {', '.join(topping_names)}")
            lines.append("  Extra topping prices by size:")
            lines.append("    14\" = $2.50 | 16\" = $3.00 | 18\" = $3.25 | 30\" = $5.50")

        return "\n".join(lines)

    def _format_fallback_menu(self) -> str:
        """Format the fallback menu.json for the AI."""
        if not self._fallback_menu:
            return "Menu unavailable. Please ask customer to check our website."

        lines = ["=== CASA DE PIZZA & WINGS — MENU (FALLBACK) ===\n"]

        categories = self._fallback_menu.get("categories", {})
        if isinstance(categories, dict):
            for key, cat in categories.items():
                cat_name = cat.get("name", key)
                lines.append(f"\n--- {cat_name} ---")
                if cat.get("note"):
                    lines.append(f"  Note: {cat['note']}")
                for item in cat.get("items", []):
                    name = item.get("name", "")
                    price = item.get("price", "")
                    desc = item.get("desc", "")
                    if price:
                        lines.append(f"  {name} — ${price}")
                    else:
                        # Pizza with multiple sizes
                        prices = item.get("prices", {})
                        if prices:
                            price_str = " | ".join([f'{s}": ${p}' for s, p in prices.items()])
                            lines.append(f"  {name} — {price_str}")
                    if desc:
                        lines.append(f"    {desc}")

        return "\n".join(lines)

    async def get_item_price(self, item_name: str, size: str = None) -> Optional[float]:
        """Look up a specific item's price. Returns price in dollars."""
        menu_data = await self.get_menu()
        if not menu_data or "categories" not in menu_data:
            return None

        price_unit = menu_data.get("priceUnit", "cents")
        item_name_lower = item_name.lower()

        for category in menu_data.get("categories", []):
            for item in category.get("items", []):
                if item_name_lower in item.get("name", "").lower():
                    base_price = item.get("price", 0)

                    # Check for size modifier
                    if size:
                        for mod_group in item.get("modifierGroups", []):
                            if mod_group.get("name", "").lower() == "size":
                                for mod in mod_group.get("modifiers", []):
                                    if size.lower() in mod.get("name", "").lower():
                                        mod_price = mod.get("price", 0)
                                        total = base_price + mod_price
                                        if price_unit == "cents":
                                            return total / 100
                                        return total

                    if price_unit == "cents":
                        return base_price / 100
                    return base_price

        return None

    async def search_menu(self, query: str) -> List[Dict[str, Any]]:
        """Search menu items by name or description."""
        menu_data = await self.get_menu()
        if not menu_data or "categories" not in menu_data:
            return []

        results = []
        query_lower = query.lower()
        price_unit = menu_data.get("priceUnit", "cents")

        for category in menu_data.get("categories", []):
            for item in category.get("items", []):
                name = item.get("name", "")
                desc = item.get("description", "")
                if query_lower in name.lower() or query_lower in desc.lower():
                    price = item.get("price", 0)
                    if price_unit == "cents":
                        price = price / 100

                    results.append({
                        "name": name,
                        "price": price,
                        "description": desc,
                        "category": category.get("name", ""),
                        "available": item.get("available", True)
                    })

        return results

    async def is_lunch_special_available(self) -> bool:
        """Check if lunch specials are currently available (10 AM - 3 PM PST)."""
        from datetime import datetime
        import pytz

        pst = pytz.timezone("America/Los_Angeles")
        now = datetime.now(pst)
        return 10 <= now.hour < 15

    async def close(self):
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


# Singleton instance
menu_sync = MenuSyncService()
