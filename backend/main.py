"""
Casa de Pizza & Wings — Voice AI Agent Backend
FastAPI server that handles:
  - Vapi.ai voice agent tool calls (order management)
  - Clover POS order creation
  - Authorize.net hosted payment page generation
  - Twilio SMS sending
  - Payment webhook processing
  - Dashboard API
"""
import os
import json
import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

import sys
sys.path.insert(0, os.path.dirname(__file__))

from clover_service import CloverService
from sms_service import SMSService
from authorize_service import AuthorizeService
from order_store import OrderStore
from sms_bot import handle_inbound_sms
from menu_sync_service import menu_sync

# ─── Logging ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ─── Keep-Alive (prevents Render cold starts) ────────────────
async def _keep_alive_loop():
    import httpx
    port = int(os.getenv("APP_PORT", 8000))
    url = f"http://localhost:{port}/health"
    await asyncio.sleep(60)
    while True:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get(url)
            logger.debug("Keep-alive ping OK")
        except Exception as e:
            logger.debug(f"Keep-alive ping failed: {e}")
        await asyncio.sleep(240)  # Every 4 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_keep_alive_loop())
    logger.info("Keep-alive background task started")
    # Start nightly menu sync scheduler (11:30 PM Las Vegas time)
    menu_sync.start_scheduler()
    logger.info("Menu sync scheduler started (daily at 11:30 PM PST)")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await menu_sync.close()

# ─── App Init ───────────────────────────────────────────────
app = FastAPI(
    title="Casa de Pizza & Wings Voice AI Agent",
    description="Backend for AI phone ordering system",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Services ───────────────────────────────────────────────
clover_svc = CloverService()
sms_svc = SMSService()
authnet_svc = AuthorizeService()
order_store = OrderStore()

# ─── Constants ──────────────────────────────────────────────
RESTAURANT_NAME = "Casa de Pizza & Wings"
RESTAURANT_PHONE = "702-200-5252"
TAX_RATE = 0.08375
CONVENIENCE_FEE_RATE = 0.03
DELIVERY_FEE = 1.99

# ─── Load Menu (with real-time sync from web API) ───────────
MENU_PATH = os.path.join(os.path.dirname(__file__), "menu.json")
try:
    with open(MENU_PATH) as f:
        MENU_DATA = json.load(f)
    logger.info("Fallback menu loaded from menu.json")
except Exception as e:
    MENU_DATA = {}
    logger.error(f"Failed to load fallback menu: {e}")

async def get_live_menu() -> dict:
    """Get menu from memory (synced nightly at 11:30 PM from web API)."""
    try:
        live = await menu_sync.get_menu()
        if live:
            return live
    except Exception as e:
        logger.error(f"Menu sync failed: {e}")
    return MENU_DATA

# ─── Pydantic Models ────────────────────────────────────────
class OrderItem(BaseModel):
    name: str
    quantity: int = 1
    unit_price: Optional[float] = None
    unit_price_cents: Optional[int] = None
    price: Optional[float] = None
    modifiers: Optional[str] = ""
    size: Optional[str] = ""
    sauce: Optional[str] = ""

class SubmitOrderRequest(BaseModel):
    session_id: str
    customer_name: str
    customer_phone: str
    order_type: str = "takeout"  # takeout or delivery
    delivery_address: Optional[str] = None
    items: List[OrderItem]
    special_instructions: Optional[str] = ""

# ─── Helper Functions ───────────────────────────────────────
def calculate_order_total(items: List[OrderItem], order_type: str) -> dict:
    """Calculate subtotal, fees, tax, and total."""
    subtotal = 0.0
    for item in items:
        qty = item.quantity or 1
        if item.unit_price and item.unit_price > 0:
            price = item.unit_price
        elif item.unit_price_cents and item.unit_price_cents > 0:
            price = item.unit_price_cents / 100.0
        elif item.price and item.price > 0:
            price = item.price
        else:
            price = 0.0
        subtotal += price * qty

    delivery_fee = DELIVERY_FEE if order_type == "delivery" else 0.0
    convenience_fee = round(subtotal * CONVENIENCE_FEE_RATE, 2)
    taxable_amount = subtotal + delivery_fee
    tax = round(taxable_amount * TAX_RATE, 2)
    total = round(subtotal + delivery_fee + convenience_fee + tax, 2)

    return {
        "subtotal": round(subtotal, 2),
        "delivery_fee": delivery_fee,
        "convenience_fee": convenience_fee,
        "tax": tax,
        "total": total
    }

def get_backend_url() -> str:
    return os.getenv("BACKEND_URL", "https://casapizza-voice-agent.onrender.com")

# ─── Health Check ───────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "Casa de Pizza & Wings Voice AI Agent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "clover": clover_svc.enabled,
        "authorize_net": authnet_svc.enabled,
        "sms": sms_svc.enabled
    }

# ─── Menu Endpoint ──────────────────────────────────────────
@app.get("/menu")
async def get_menu():
    return await get_live_menu()

@app.get("/menu/sync-status")
async def menu_sync_status():
    """Check menu sync status (last sync, next sync, etc.)"""
    return menu_sync.get_sync_status()

@app.post("/menu/force-sync")
async def menu_force_sync():
    """Force an immediate menu sync from the web API (admin use)."""
    result = await menu_sync.force_sync()
    return result

# ─── Vapi Tool Call Handler ─────────────────────────────────
@app.post("/vapi/tool-call")
async def vapi_tool_call(request: Request):
    """Handle all tool calls from Vapi voice agent."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Extract tool call info — support both Vapi formats
    message = body.get("message", {})
    tool_calls = message.get("toolCalls") or message.get("toolCallList", [])

    if not tool_calls:
        return JSONResponse({"results": []})

    results = []
    for tc in tool_calls:
        tool_id = tc.get("id", "")
        fn = tc.get("function", {})
        fn_name = fn.get("name", "")
        raw_args = fn.get("arguments", "{}")

        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except Exception:
            args = {}

        logger.info(f"Tool call: {fn_name} | args={json.dumps(args)[:200]}")

        # Route to handler (accept both naming conventions)
        if fn_name == "search_menu_item":
            result = await tool_search_menu_item(args)
        elif fn_name == "calculate_total":
            result = await tool_calculate_total(args)
        elif fn_name in ("submit_order_and_send_payment", "submit_order"):
            result = await tool_submit_order(args, message)
        elif fn_name in ("check_order_status", "get_order_status"):
            result = await tool_check_order_status(args)
        else:
            result = {"error": f"Unknown tool: {fn_name}"}

        results.append({
            "toolCallId": tool_id,
            "result": json.dumps(result) if isinstance(result, dict) else str(result)
        })

    return JSONResponse({"results": results})

# ─── Tool Implementations ───────────────────────────────────
async def tool_search_menu_item(args: dict) -> dict:
    """Search for a menu item by name and return price (real-time from web API)."""
    query = args.get("item_name", "").lower().strip()
    if not query:
        return {"error": "No item name provided"}

    # Try real-time search from menu_sync first
    try:
        live_results = await menu_sync.search_menu(query)
        if live_results:
            items_out = []
            for r in live_results[:5]:
                entry = {"name": r["name"], "category": r["category"]}
                if r.get("price"):
                    entry["price"] = r["price"]
                items_out.append(entry)
            return {"found": True, "items": items_out}
    except Exception as e:
        logger.error(f"Menu sync search failed: {e}")

    # Fallback to local MENU_DATA
    results = []
    menu_data = MENU_DATA
    categories = menu_data.get("categories", {})

    # Support both dict and list format for categories
    if isinstance(categories, dict):
        cat_iter = categories.items()
    elif isinstance(categories, list):
        cat_iter = [(c.get("id", ""), c) for c in categories]
    else:
        cat_iter = []

    for cat_key, category in cat_iter:
        items = list(category.get("items", []))
        # Handle nested items (wings) — some sub-keys are dicts with an 'items' key
        for sub_key in ["casa_special_wings", "regular_wings", "fingers"]:
            if sub_key in category:
                sub = category[sub_key]
                if isinstance(sub, list):
                    items += sub
                elif isinstance(sub, dict) and "items" in sub:
                    items += sub["items"]

        for item in items:
            if not isinstance(item, dict):
                continue
            item_name = item.get("name", "").lower()
            if query in item_name or item_name in query:
                entry = {"name": item.get("name"), "category": category.get("name")}
                if "prices" in item:
                    entry["prices"] = item["prices"]
                elif "price_usd" in item:
                    entry["price"] = item["price_usd"]
                elif "price" in item:
                    entry["price"] = item["price"]
                elif "price_cents" in item:
                    entry["price"] = item["price_cents"] / 100
                elif "price_sm" in item:
                    entry["price_small"] = item["price_sm"]
                    entry["price_large"] = item["price_lg"]
                results.append(entry)

    if results:
        return {"found": True, "items": results[:5]}
    return {"found": False, "message": f"Item '{query}' not found in menu"}

async def tool_calculate_total(args: dict) -> dict:
    """Calculate order total with tax and fees."""
    items_raw = args.get("items", [])
    order_type = args.get("order_type", "takeout")

    items = []
    for it in items_raw:
        items.append(OrderItem(
            name=it.get("name", "Item"),
            quantity=it.get("quantity", 1),
            unit_price=it.get("unit_price"),
            unit_price_cents=it.get("unit_price_cents"),
            price=it.get("price"),
            modifiers=it.get("modifiers", ""),
            size=it.get("size", ""),
            sauce=it.get("sauce", "")
        ))

    totals = calculate_order_total(items, order_type)
    return {
        "subtotal": f"${totals['subtotal']:.2f}",
        "delivery_fee": f"${totals['delivery_fee']:.2f}" if totals['delivery_fee'] else "None",
        "convenience_fee": f"${totals['convenience_fee']:.2f} (3%)",
        "tax": f"${totals['tax']:.2f} (8.375%)",
        "total": f"${totals['total']:.2f}"
    }

async def tool_submit_order(args: dict, message: dict) -> dict:
    """Submit order, create Clover order, generate Authorize.net payment link, send SMS."""
    session_id = message.get("call", {}).get("id", str(uuid.uuid4()))
    order_id = str(uuid.uuid4())

    customer_name = args.get("customer_name", "Customer")
    customer_phone = args.get("customer_phone", "")
    order_type = args.get("order_type", "takeout")
    delivery_address = args.get("delivery_address", "")
    items_raw = args.get("items", [])
    special_instructions = args.get("special_instructions", "")

    if not customer_phone:
        return {"success": False, "error": "Customer phone number is required to send the payment link."}

    if not items_raw:
        return {"success": False, "error": "No items in order."}

    # Build order items — handle both field naming conventions
    # Vapi sends: item_name, unit_price_cents, modifier_names
    # Legacy sends: name, unit_price, price
    items = []
    for it in items_raw:
        name = it.get("item_name") or it.get("name", "Item")
        modifiers = it.get("modifiers", "")
        if not modifiers and it.get("modifier_names"):
            modifiers = ", ".join(it["modifier_names"])
        items.append(OrderItem(
            name=name,
            quantity=it.get("quantity", 1),
            unit_price=it.get("unit_price"),
            unit_price_cents=it.get("unit_price_cents"),
            price=it.get("price"),
            modifiers=modifiers,
            size=it.get("size", ""),
            sauce=it.get("sauce", "")
        ))

    # Calculate totals
    totals = calculate_order_total(items, order_type)
    total_amount = totals["total"]

    # Build order record
    order_record = {
        "order_id": order_id,
        "session_id": session_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "order_type": order_type,
        "delivery_address": delivery_address,
        "items": [{"name": i.name, "quantity": i.quantity, "unit_price": i.unit_price or (i.unit_price_cents / 100 if i.unit_price_cents else i.price or 0), "modifiers": i.modifiers, "size": i.size, "sauce": i.sauce} for i in items],
        "special_instructions": special_instructions,
        "subtotal": totals["subtotal"],
        "delivery_fee": totals["delivery_fee"],
        "convenience_fee": totals["convenience_fee"],
        "tax": totals["tax"],
        "total_usd": total_amount,
        "status": "pending_payment",
        "payment_method": "authorize_net",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    # Save order
    order_store.save(order_record)

    # Step 1: Create Clover order
    clover_items = [{"name": f"{i.size} {i.name}".strip() + (f" ({i.sauce})" if i.sauce else "") + (f" - {i.modifiers}" if i.modifiers else ""), "quantity": i.quantity, "unit_price": i.unit_price or (i.unit_price_cents / 100 if i.unit_price_cents else i.price or 0)} for i in items]
    clover_result = clover_svc.create_order(
        items=clover_items,
        order_type=order_type,
        customer_name=customer_name,
        note=f"Phone: {customer_phone} | {special_instructions}"
    )
    if clover_result.get("success"):
        order_store.update_status(order_id, "pending_payment", {"clover_order_id": clover_result.get("order_id")})

    # Step 2: Generate Authorize.net payment link
    backend_url = get_backend_url()
    description = f"Casa de Pizza order for {customer_name} - {order_type}"
    authnet_result = authnet_svc.create_hosted_payment_page(
        amount=total_amount,
        description=description,
        customer_name=customer_name,
        customer_phone=customer_phone,
        order_id=order_id,
        backend_url=backend_url
    )

    payment_url = None
    if authnet_result.get("success"):
        payment_url = authnet_result["payment_url"]
        order_store.update_status(order_id, "payment_link_sent", {"payment_url": payment_url})
    else:
        logger.warning(f"Authorize.net failed: {authnet_result.get('error')} — order saved without payment link")
        order_store.update_status(order_id, "payment_link_failed", {"authnet_error": authnet_result.get("error")})

    # Step 3: Send SMS with payment link
    sms_sent = False
    if payment_url and customer_phone:
        sms_sent = sms_svc.send_payment_link(
            to_phone=customer_phone,
            customer_name=customer_name,
            payment_url=payment_url,
            total=total_amount,
            order_id=order_id
        )

    # Build response for Vapi
    items_summary = ", ".join([f"{i.quantity}x {i.size} {i.name}".strip() for i in items])
    response = {
        "success": True,
        "order_id": order_id[-8:].upper(),
        "customer_name": customer_name,
        "items_summary": items_summary,
        "subtotal": f"${totals['subtotal']:.2f}",
        "convenience_fee": f"${totals['convenience_fee']:.2f}",
        "tax": f"${totals['tax']:.2f}",
        "total": f"${total_amount:.2f}",
        "order_type": order_type,
        "sms_sent": sms_sent,
        "payment_method": "Authorize.net"
    }

    if payment_url:
        response["payment_url"] = payment_url
        response["message"] = f"Order confirmed! I've sent a payment link to {customer_phone}. Total is ${total_amount:.2f}. Your order will go to the kitchen as soon as payment is received."
    else:
        response["message"] = f"Order saved! Total is ${total_amount:.2f}. Please call 702-200-5252 to complete payment."

    return response

async def tool_check_order_status(args: dict) -> dict:
    """Check the status of an existing order."""
    order_id = args.get("order_id", "")
    if not order_id:
        return {"error": "No order ID provided"}

    # Try to find by short ID
    for oid, order in order_store._orders.items():
        if oid.endswith(order_id.lower()) or oid[-8:].upper() == order_id.upper():
            return {
                "order_id": oid[-8:].upper(),
                "status": order.get("status"),
                "total": f"${order.get('total_usd', 0):.2f}",
                "items": order.get("items", [])
            }

    return {"error": f"Order {order_id} not found"}

# ─── Vapi Webhook ───────────────────────────────────────────
@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    """Handle Vapi call lifecycle events."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "ok"})

    event_type = body.get("message", {}).get("type", "")
    call_id = body.get("message", {}).get("call", {}).get("id", "")
    logger.info(f"Vapi webhook: {event_type} | call_id={call_id}")

    return JSONResponse({"status": "ok"})

# ─── Authorize.net Webhook ──────────────────────────────────
@app.post("/authnet/webhook")
async def authnet_webhook(request: Request):
    """Handle Authorize.net payment notifications."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "ok"})

    event_type = body.get("eventType", "")
    logger.info(f"Authorize.net webhook: {event_type}")

    if "authcapture" in event_type.lower() or "payment.authorized" in event_type.lower():
        payload = body.get("payload", {})
        invoice = payload.get("invoiceNumber", "")
        amount = payload.get("authAmount", 0)

        # Find order by invoice (order_id prefix)
        for oid, order in order_store._orders.items():
            if oid.startswith(invoice) or oid[:20] == invoice:
                order_store.update_status(oid, "paid", {
                    "paid_at": datetime.now(timezone.utc).isoformat(),
                    "amount_paid": amount
                })
                logger.info(f"Order {oid} marked as PAID via Authorize.net — ${amount}")
                break

    return JSONResponse({"status": "ok"})

# ─── Payment Complete Redirect ──────────────────────────────
@app.get("/payment/complete")
async def payment_complete(request: Request):
    return HTMLResponse("""
    <html><body style="font-family:sans-serif;text-align:center;padding:40px;background:#f0fdf4">
    <h1 style="color:#16a34a">✅ Payment Successful!</h1>
    <p style="font-size:1.2em">Thank you! Your order is being prepared at Casa de Pizza & Wings.</p>
    <p>📞 Questions? Call <strong>702-200-5252</strong></p>
    <p style="color:#666">765 N Nellis Blvd, Suite 10, Las Vegas, NV 89110</p>
    </body></html>
    """)

@app.get("/payment/cancel")
async def payment_cancel():
    return HTMLResponse("""
    <html><body style="font-family:sans-serif;text-align:center;padding:40px;background:#fef2f2">
    <h1 style="color:#dc2626">Payment Cancelled</h1>
    <p>Your order was not completed. Please call us to place your order.</p>
    <p>📞 <strong>702-200-5252</strong></p>
    </body></html>
    """)

# ─── Dashboard API ──────────────────────────────────────────
@app.get("/api/orders")
async def get_orders(limit: int = 20):
    return {"orders": order_store.list_recent(limit), "total": order_store.count()}

@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    order = order_store.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/status")
async def get_status():
    return {
        "restaurant": RESTAURANT_NAME,
        "clover_connected": clover_svc.enabled,
        "authorize_net_connected": authnet_svc.enabled,
        "sms_connected": sms_svc.enabled,
        "orders_today": order_store.count(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ─── SMS Inbound Webhook ─────────────────────────────────────
@app.post("/webhook/sms")
async def inbound_sms(request: Request, background_tasks: BackgroundTasks):
    """
    Twilio webhook for inbound SMS messages.
    Returns TwiML XML with the bot reply.
    """
    from fastapi.responses import Response
    try:
        form = await request.form()
        from_phone = form.get("From", "")
        body = form.get("Body", "").strip()
        logger.info(f"Inbound SMS from {from_phone}: '{body[:80]}'")

        if not from_phone or not body:
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml"
            )

        live_menu = await get_live_menu()
        reply = await handle_inbound_sms(
            from_phone=from_phone,
            body=body,
            menu_data=live_menu,
            authnet_svc=authnet_svc,
            sms_svc=sms_svc,
            order_store=order_store,
            get_backend_url=get_backend_url,
            background_tasks=background_tasks
        )

        reply_escaped = reply.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply_escaped}</Message></Response>'
        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Inbound SMS webhook error: {e}")
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Message>Sorry, there was an error. Please call 702-200-5252.</Message></Response>',
            media_type="application/xml"
        )


# ─── Test Endpoints ─────────────────────────────────────────
@app.post("/test/sms")
async def test_sms(request: Request):
    body = await request.json()
    phone = body.get("phone", "")
    if not phone:
        return {"error": "phone required"}
    sent = sms_svc.send_custom(phone, f"Test SMS from Casa de Pizza & Wings AI system. 🍕")
    return {"sent": sent, "to": phone}

@app.post("/test/payment")
async def test_payment(request: Request):
    body = await request.json()
    amount = body.get("amount", 19.99)
    result = authnet_svc.create_hosted_payment_page(
        amount=amount,
        description="Test payment",
        customer_name="Test Customer",
        customer_phone="7025551234",
        order_id=str(uuid.uuid4()),
        backend_url=get_backend_url()
    )
    return result

# ─── Run ────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", 8000)),
        reload=False
    )
