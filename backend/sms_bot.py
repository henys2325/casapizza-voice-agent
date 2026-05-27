"""
SMS Ordering Bot EVA — Casa de Pizza & Wings
Handles inbound SMS messages from customers.

Conversation flow (Opción C — Combined):
  1. Greeting / "menu" / "hola" → sends menu link + quick order instructions
  2. Customer types their order in natural language → GPT parses it
  3. Bot confirms items + total → customer replies YES/SI/ДА
  4. Bot generates Authorize.net payment link → sends via SMS
  5. Customer pays → order goes to Clover kitchen

State is stored in-memory (per phone number, TTL 30 min).
"""
import os
import json
import uuid
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────
MENU_LINK = "https://casadepizzawings.com/"
RESTAURANT_NAME = "Casa de Pizza & Wings"
RESTAURANT_PHONE = "702-200-5252"
RESTAURANT_ADDRESS = "765 N Nellis Blvd, Suite 10, Las Vegas, NV 89110"
TAX_RATE = 0.08375

SESSION_TTL_MINUTES = 30

# ── Greeting keywords ─────────────────────────────────────────
GREETING_KEYWORDS = {
    "hola", "hello", "hi", "hey", "menu", "menú", "order", "ordenar",
    "start", "help", "ayuda", "привет", "заказ", "меню", "info",
    "pizza", "wings", "food", "comida", "eat", "comer", "pickup",
    "delivery", "entrega"
}

CONFIRM_KEYWORDS = {"yes", "si", "sí", "да", "confirm", "confirmar",
                    "ok", "okay", "sure", "correct", "correcto", "yep",
                    "yeah", "affirmative", "proceed", "go", "pay", "pagar"}

CANCEL_KEYWORDS = {"no", "cancel", "cancelar", "нет", "stop", "nevermind",
                   "never mind", "quit", "exit", "salir", "wrong", "malo"}

# ── In-memory session store ────────────────────────────────────
_sessions: Dict[str, Dict[str, Any]] = {}


def _get_session(phone: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    if phone in _sessions:
        s = _sessions[phone]
        last_activity = s.get("last_activity")
        if last_activity and (now - last_activity).total_seconds() > SESSION_TTL_MINUTES * 60:
            del _sessions[phone]
        else:
            s["last_activity"] = now
            return s
    _sessions[phone] = {
        "phone": phone,
        "state": "idle",
        "language": "en",
        "items": [],
        "customer_name": "Customer",
        "order_type": "takeout",
        "pending_order": None,
        "last_activity": now,
        "created_at": now,
    }
    return _sessions[phone]


def _clear_session(phone: str):
    if phone in _sessions:
        del _sessions[phone]


def _detect_language(text: str) -> str:
    if re.search(r'[а-яА-ЯёЁ]', text):
        return "ru"
    spanish_words = ["hola", "gracias", "quiero", "pizza", "orden", "pagar",
                     "sí", "si", "por favor", "cuánto", "cuanto", "menú",
                     "menu", "entrega", "recoger", "alitas"]
    if any(w in text.lower() for w in spanish_words):
        return "es"
    return "en"


def _build_greeting(lang: str) -> str:
    if lang == "es":
        return (
            f"¡Hola! Soy EVA 🍕🌗 Bienvenido a {RESTAURANT_NAME}.\n\n"
            f"📋 Ver menú completo y ordenar en línea:\n{MENU_LINK}\n\n"
            f"O escríbeme tu pedido aquí y te envío un link de pago.\n"
            f"Ejemplo: \"2 alitas buffalo y 1 pizza pepperoni\"\n\n"
            f"📞 {RESTAURANT_PHONE}\n📍 {RESTAURANT_ADDRESS}"
        )
    elif lang == "ru":
        return (
            f"Привет! Я EVA 🍕🌗 Добро пожаловать в {RESTAURANT_NAME}.\n\n"
            f"📋 Полное меню и онлайн-заказ:\n{MENU_LINK}\n\n"
            f"Или напишите заказ здесь, и я пришлю ссылку для оплаты.\n"
            f"Пример: \"2 крылышка буффало и 1 пицца пепперони\"\n\n"
            f"📞 {RESTAURANT_PHONE}\n📍 {RESTAURANT_ADDRESS}"
        )
    else:
        return (
            f"Hi! I'm EVA 🍕🌗 Welcome to {RESTAURANT_NAME}.\n\n"
            f"📋 View full menu & order online:\n{MENU_LINK}\n\n"
            f"Or text me your order and I'll send you a payment link!\n"
            f"Example: \"2 buffalo wings and 1 pepperoni pizza\"\n\n"
            f"📞 {RESTAURANT_PHONE}\n📍 {RESTAURANT_ADDRESS}"
        )


def _build_confirmation(items: List[Dict], subtotal: float, lang: str) -> str:
    lines = []
    for item in items:
        name = item.get("name", "Item")
        size = item.get("size", "")
        if size:
            name = f"{size} {name}"
        qty = item.get("quantity", 1)
        price = item.get("unit_price", 0)
        lines.append(f"  • {qty}x {name} — ${price * qty:.2f}")

    items_text = "\n".join(lines)
    conv_fee = subtotal * 0.03
    tax = subtotal * TAX_RATE
    grand_total = subtotal + conv_fee + tax

    if lang == "es":
        return (
            f"📋 Tu orden:\n{items_text}\n\n"
            f"Subtotal: ${subtotal:.2f}\n"
            f"Cargo de conveniencia (3%): ${conv_fee:.2f}\n"
            f"Impuesto (8.375%): ${tax:.2f}\n"
            f"💰 Total: ${grand_total:.2f}\n\n"
            f"¿Confirmas? Responde SI para pagar o NO para cancelar."
        )
    elif lang == "ru":
        return (
            f"📋 Ваш заказ:\n{items_text}\n\n"
            f"Подытог: ${subtotal:.2f}\n"
            f"Комиссия (3%): ${conv_fee:.2f}\n"
            f"Налог (8.375%): ${tax:.2f}\n"
            f"💰 Итого: ${grand_total:.2f}\n\n"
            f"Подтверждаете? Ответьте ДА для оплаты или НЕТ для отмены."
        )
    else:
        return (
            f"📋 Your order:\n{items_text}\n\n"
            f"Subtotal: ${subtotal:.2f}\n"
            f"Convenience fee (3%): ${conv_fee:.2f}\n"
            f"Tax (8.375%): ${tax:.2f}\n"
            f"💰 Total: ${grand_total:.2f}\n\n"
            f"Confirm? Reply YES to pay or NO to cancel."
        )


async def _parse_order_with_gpt(text: str, menu_data: dict, lang: str) -> Dict[str, Any]:
    """Parse a natural language order using GPT."""
    # Build compact menu summary
    menu_lines = []
    for cat_key, category in menu_data.get("categories", {}).items():
        if isinstance(category, list):
            for item in category:
                if isinstance(item, dict):
                    menu_lines.append(
                        f"{item.get('name', '?')} | ${item.get('price', 0):.2f}"
                    )
        elif isinstance(category, dict):
            # Handle nested structures like wings
            for sub_key, sub_items in category.items():
                if isinstance(sub_items, list):
                    for item in sub_items:
                        if isinstance(item, dict):
                            menu_lines.append(
                                f"{item.get('name', '?')} | ${item.get('price', 0):.2f}"
                            )

    menu_text = "\n".join(menu_lines[:150])

    system_prompt = f"""You are an order parser for {RESTAURANT_NAME}.
Extract items from the customer's message and match them to the menu.
Return a JSON object with this structure:
{{
  "items": [
    {{"name": "...", "quantity": 1, "unit_price": 0.00, "size": "", "modifiers": "", "special_instructions": ""}}
  ],
  "order_type": "takeout",
  "customer_name": "Customer",
  "error": null
}}

Rules:
- Match items to the menu even if the customer uses informal names
- "alitas" = wings, "alitas buffalo" = buffalo wings
- If an item is not on the menu, set error to a message explaining it
- order_type is "takeout" unless customer says "delivery" or "entrega" or "доставка"
- If customer mentions their name, extract it
- unit_price must be the exact price from the menu
- Return ONLY valid JSON, no other text

Menu:
{menu_text}
"""

    try:
        import openai
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("BUILT_IN_FORGE_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("BUILT_IN_FORGE_API_URL")

        if not api_key:
            raise ValueError("No OpenAI API key")

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = openai.AsyncOpenAI(**client_kwargs)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        result_text = response.choices[0].message.content
        return json.loads(result_text)
    except Exception as e:
        logger.error(f"GPT parse error: {e}")
        return {"items": [], "order_type": "takeout", "customer_name": "Customer",
                "error": str(e)}


async def handle_inbound_sms(
    from_phone: str,
    body: str,
    menu_data: dict,
    authnet_svc,
    sms_svc,
    order_store,
    get_backend_url,
    background_tasks=None
) -> str:
    """
    Main handler for inbound SMS messages.
    Returns the response text to send back to the customer.
    """
    session = _get_session(from_phone)
    text = body.strip()
    text_lower = text.lower()
    lang = _detect_language(text)
    session["language"] = lang

    logger.info(f"SMS from {from_phone}: '{text[:80]}' | state={session['state']} | lang={lang}")

    # ── CANCEL at any point ────────────────────────────────────
    if any(kw in text_lower for kw in CANCEL_KEYWORDS) and session["state"] != "idle":
        _clear_session(from_phone)
        if lang == "es":
            return "❌ Orden cancelada. ¡Escríbenos cuando quieras ordenar! 🍕"
        elif lang == "ru":
            return "❌ Заказ отменён. Напишите нам, когда захотите заказать! 🍕"
        else:
            return "❌ Order cancelled. Text us anytime to order! 🍕"

    # ── STATE: idle ────────────────────────────────────────────
    if session["state"] == "idle":
        is_greeting = any(kw in text_lower for kw in GREETING_KEYWORDS) and len(text.split()) <= 4
        if is_greeting:
            session["state"] = "greeted"
            return _build_greeting(lang)
        else:
            session["state"] = "greeted"
            # Fall through to order parsing

    # ── STATE: greeted / ordering — parse order ────────────────
    if session["state"] in ("greeted", "ordering"):
        if any(kw in text_lower for kw in {"menu", "menú", "меню", "link", "enlace"}):
            if lang == "es":
                return f"📋 Menú completo: {MENU_LINK}\n\nO escríbeme tu pedido aquí."
            elif lang == "ru":
                return f"📋 Полное меню: {MENU_LINK}\n\nИли напишите заказ здесь."
            else:
                return f"📋 Full menu: {MENU_LINK}\n\nOr text your order here."

        parsed = await _parse_order_with_gpt(text, menu_data, lang)

        if parsed.get("error") or not parsed.get("items"):
            if lang == "es":
                return (
                    f"No pude entender tu pedido. 😕\n"
                    f"Escribe algo como: \"2 alitas buffalo y 1 pizza pepperoni\"\n"
                    f"O ve el menú: {MENU_LINK}"
                )
            elif lang == "ru":
                return (
                    f"Не смог распознать заказ. 😕\n"
                    f"Напишите, например: \"2 крылышка буффало и 1 пицца пепперони\"\n"
                    f"Или посмотрите меню: {MENU_LINK}"
                )
            else:
                return (
                    f"I couldn't understand your order. 😕\n"
                    f"Try: \"2 buffalo wings and 1 pepperoni pizza\"\n"
                    f"Or view the menu: {MENU_LINK}"
                )

        items = parsed["items"]
        order_type = parsed.get("order_type", "takeout")
        customer_name = parsed.get("customer_name", "Customer")
        subtotal = sum(
            item.get("unit_price", 0) * item.get("quantity", 1)
            for item in items
        )

        session["items"] = items
        session["order_type"] = order_type
        session["customer_name"] = customer_name
        session["subtotal"] = subtotal
        session["state"] = "confirming"

        return _build_confirmation(items, subtotal, lang)

    # ── STATE: confirming ──────────────────────────────────────
    if session["state"] == "confirming":
        if any(kw in text_lower for kw in CONFIRM_KEYWORDS):
            items = session["items"]
            order_type = session["order_type"]
            customer_name = session["customer_name"]
            subtotal = session.get("subtotal", 0)
            lang = session["language"]

            conv_fee = subtotal * 0.03
            tax = subtotal * TAX_RATE
            total_amount = round(subtotal + conv_fee + tax, 2)
            order_id = str(uuid.uuid4())

            try:
                backend_url = get_backend_url()
                description = f"Casa de Pizza order for {customer_name} - {order_type}"
                authnet_result = authnet_svc.create_hosted_payment_page(
                    amount=total_amount,
                    description=description,
                    customer_name=customer_name,
                    customer_phone=from_phone,
                    order_id=order_id,
                    backend_url=backend_url
                )

                if not authnet_result.get("success"):
                    raise ValueError(authnet_result.get("error", "Payment link failed"))

                payment_url = authnet_result["payment_url"]

                # Save pending order
                order_record = {
                    "order_id": order_id,
                    "session_id": f"sms_{from_phone}_{order_id[:8]}",
                    "source": "sms",
                    "customer_name": customer_name,
                    "customer_phone": from_phone,
                    "order_type": order_type,
                    "items": items,
                    "subtotal": subtotal,
                    "convenience_fee": conv_fee,
                    "tax": tax,
                    "total_usd": total_amount,
                    "status": "pending_payment",
                    "payment_method": "authorize_net",
                    "payment_url": payment_url,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                order_store.save(order_record)

                _clear_session(from_phone)

                if lang == "es":
                    return (
                        f"✅ ¡Perfecto! Aquí está tu link de pago:\n"
                        f"{payment_url}\n\n"
                        f"💰 Total: ${total_amount:.2f}\n"
                        f"⚠️ Tu orden se prepara al confirmar el pago."
                    )
                elif lang == "ru":
                    return (
                        f"✅ Отлично! Ссылка для оплаты:\n"
                        f"{payment_url}\n\n"
                        f"💰 Итого: ${total_amount:.2f}\n"
                        f"⚠️ Заказ начнём готовить после оплаты."
                    )
                else:
                    return (
                        f"✅ Great! Here's your payment link:\n"
                        f"{payment_url}\n\n"
                        f"💰 Total: ${total_amount:.2f}\n"
                        f"⚠️ Your order will be prepared once payment is confirmed."
                    )

            except Exception as e:
                logger.error(f"SMS order payment link error: {e}")
                _clear_session(from_phone)
                if lang == "es":
                    return f"Lo siento, hubo un error. Por favor llama al {RESTAURANT_PHONE}."
                else:
                    return f"Sorry, there was an error. Please call {RESTAURANT_PHONE}."

        elif any(kw in text_lower for kw in CANCEL_KEYWORDS):
            _clear_session(from_phone)
            if lang == "es":
                return "❌ Orden cancelada. ¡Escríbenos cuando quieras! 🍕"
            else:
                return "❌ Order cancelled. Text us anytime! 🍕"
        else:
            items = session["items"]
            subtotal = session.get("subtotal", 0)
            if lang == "es":
                return f"Por favor responde SI para confirmar o NO para cancelar.\n\n{_build_confirmation(items, subtotal, lang)}"
            else:
                return f"Please reply YES to confirm or NO to cancel.\n\n{_build_confirmation(items, subtotal, lang)}"

    # ── Fallback ───────────────────────────────────────────────
    _clear_session(from_phone)
    return _build_greeting(lang)
