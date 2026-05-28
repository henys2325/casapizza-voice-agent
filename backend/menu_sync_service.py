"""
Menu Sync Service for Casa de Pizza & Wings AI Voice Agent (Noa)
Connects to the web API at casadepizzawingsnellis.com/api/menu
and syncs the menu ONCE PER DAY at 11:30 PM (Las Vegas time).

Strategy:
- On startup, load menu from local cache (menu_cache.json) or fallback (menu.json)
- Background scheduler syncs from API every night at 11:30 PM PST
  (outside business hours 10AM-10PM, so no impact on system)
- If API data is received, update local cache file + memory
- During the day, Noa uses the in-memory menu (instant, no API calls)
- If cache file doesn't exist on first boot, fetch immediately from API
"""

import asyncio
import time
import json
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import threading

import httpx

logger = logging.getLogger(__name__)

# Configuration
MENU_API_URL = os.getenv("MENU_API_URL", "https://casadepizzawingsnellis.com/api/menu")
FALLBACK_MENU_PATH = os.path.join(os.path.dirname(__file__), "menu.json")
CACHE_FILE_PATH = os.path.join(os.path.dirname(__file__), "menu_cache.json")
REQUEST_TIMEOUT = 10  # seconds
SYNC_HOUR = 23  # 11 PM
SYNC_MINUTE = 30  # :30


class MenuSyncService:
    """Daily menu synchronization service — syncs at 11:30 PM Las Vegas time."""

    def __init__(self):
        self._menu: Optional[Dict[str, Any]] = None
        self._last_sync: Optional[str] = None
        self._scheduler_running = False
        self._load_menu_on_startup()

    def _load_menu_on_startup(self):
        """Load menu from cache file, or fallback if cache doesn't exist."""
        # Try loading from daily cache first
        if os.path.exists(CACHE_FILE_PATH):
            try:
                with open(CACHE_FILE_PATH, "r") as f:
                    cache_data = json.load(f)
                self._menu = cache_data.get("menu", {})
                self._last_sync = cache_data.get("synced_at", "unknown")
                logger.info(f"Menu loaded from cache (last sync: {self._last_sync})")
                return
            except Exception as e:
                logger.error(f"Failed to load menu cache: {e}")

        # Fall back to menu.json
        try:
            with open(FALLBACK_MENU_PATH, "r") as f:
                self._menu = json.load(f)
            self._last_sync = "fallback"
            logger.info("Menu loaded from fallback menu.json")
        except Exception as e:
            logger.error(f"Failed to load fallback menu: {e}")
            self._menu = {}

    def _save_cache(self, menu_data: Dict[str, Any]):
        """Save synced menu to local cache file."""
        try:
            import pytz
            pst = pytz.timezone("America/Los_Angeles")
            now = datetime.now(pst)
            cache_data = {
                "synced_at": now.strftime("%Y-%m-%d %H:%M:%S PST"),
                "menu": menu_data
            }
            with open(CACHE_FILE_PATH, "w") as f:
                json.dump(cache_data, f, indent=2)
            logger.info(f"Menu cache saved at {cache_data['synced_at']}")
        except Exception as e:
            logger.error(f"Failed to save menu cache: {e}")

    async def sync_from_api(self) -> bool:
        """Fetch fresh menu data from the web API and update cache."""
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get(MENU_API_URL)
                if response.status_code == 200:
                    data = response.json()
                    categories = data.get("categories", [])
                    logger.info(f"Menu synced from API: {len(categories)} categories")

                    # Update in-memory menu
                    self._menu = data

                    # Save to cache file
                    self._save_cache(data)

                    import pytz
                    pst = pytz.timezone("America/Los_Angeles")
                    self._last_sync = datetime.now(pst).strftime("%Y-%m-%d %H:%M:%S PST")
                    return True
                else:
                    logger.warning(f"Menu API returned status {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Failed to sync menu from API: {e}")
            return False

    def _sync_from_api_sync(self):
        """Synchronous wrapper for the async sync (used by scheduler thread)."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.sync_from_api())
            loop.close()
            if result:
                logger.info("Nightly menu sync completed successfully")
            else:
                logger.error("Nightly menu sync failed — keeping current menu")
        except Exception as e:
            logger.error(f"Nightly sync error: {e}")

    def _get_seconds_until_next_sync(self) -> float:
        """Calculate seconds until next 11:30 PM Las Vegas time."""
        try:
            import pytz
            pst = pytz.timezone("America/Los_Angeles")
            now = datetime.now(pst)

            # Target: today at 11:30 PM
            target = now.replace(hour=SYNC_HOUR, minute=SYNC_MINUTE, second=0, microsecond=0)

            # If we already passed 11:30 PM today, schedule for tomorrow
            if now >= target:
                target += timedelta(days=1)

            delta = (target - now).total_seconds()
            logger.info(f"Next menu sync in {delta/3600:.1f} hours ({target.strftime('%Y-%m-%d %H:%M:%S')} PST)")
            return delta
        except Exception as e:
            logger.error(f"Error calculating next sync time: {e}")
            # Default to 12 hours if calculation fails
            return 43200

    def _scheduler_loop(self):
        """Background thread that runs the nightly sync."""
        while self._scheduler_running:
            # Wait until 11:30 PM
            wait_seconds = self._get_seconds_until_next_sync()
            logger.info(f"Menu sync scheduler: sleeping {wait_seconds/3600:.1f} hours until next sync")

            # Sleep in small intervals so we can stop the thread
            elapsed = 0
            while elapsed < wait_seconds and self._scheduler_running:
                time.sleep(min(60, wait_seconds - elapsed))  # Check every 60 seconds
                elapsed += 60

            if not self._scheduler_running:
                break

            # Time to sync!
            logger.info("Starting nightly menu sync...")
            self._sync_from_api_sync()

    def start_scheduler(self):
        """Start the background scheduler for nightly syncs."""
        if self._scheduler_running:
            return

        self._scheduler_running = True
        thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="menu-sync-scheduler")
        thread.start()
        logger.info(f"Menu sync scheduler started — syncs daily at {SYNC_HOUR}:{SYNC_MINUTE:02d} PM Las Vegas time")

        # If no cache exists (first boot), do an immediate sync
        if self._last_sync == "fallback" or self._last_sync is None:
            logger.info("No cache found — performing initial sync from API...")
            threading.Thread(target=self._sync_from_api_sync, daemon=True).start()

    def stop_scheduler(self):
        """Stop the background scheduler."""
        self._scheduler_running = False
        logger.info("Menu sync scheduler stopped")

    async def get_menu(self) -> Dict[str, Any]:
        """Get the current menu from memory (instant, no API call)."""
        if self._menu:
            return self._menu
        # If somehow menu is None, try loading fallback
        self._load_menu_on_startup()
        return self._menu or {}

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
        if not self._menu:
            return "Menu unavailable. Please ask customer to check our website."

        lines = ["=== CASA DE PIZZA & WINGS — MENU ===\n"]

        categories = self._menu.get("categories", {})
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
        import pytz
        pst = pytz.timezone("America/Los_Angeles")
        now = datetime.now(pst)
        return 10 <= now.hour < 15

    def get_sync_status(self) -> Dict[str, Any]:
        """Get the current sync status for health checks."""
        import pytz
        pst = pytz.timezone("America/Los_Angeles")
        now = datetime.now(pst)

        # Calculate next sync time
        target = now.replace(hour=SYNC_HOUR, minute=SYNC_MINUTE, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        hours_until_sync = (target - now).total_seconds() / 3600

        return {
            "last_sync": self._last_sync,
            "next_sync": target.strftime("%Y-%m-%d %H:%M:%S PST"),
            "hours_until_next_sync": round(hours_until_sync, 1),
            "menu_loaded": self._menu is not None,
            "categories_count": len(self._menu.get("categories", [])) if self._menu and "categories" in self._menu else 0,
            "scheduler_running": self._scheduler_running
        }

    async def force_sync(self) -> Dict[str, Any]:
        """Force an immediate sync (for admin/debug purposes)."""
        success = await self.sync_from_api()
        return {
            "success": success,
            "synced_at": self._last_sync,
            "categories": len(self._menu.get("categories", [])) if self._menu and "categories" in self._menu else 0
        }

    async def close(self):
        """Stop scheduler and cleanup."""
        self.stop_scheduler()


# Singleton instance
menu_sync = MenuSyncService()
