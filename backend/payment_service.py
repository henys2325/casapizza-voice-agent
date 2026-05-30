"""
Payment Service — Process Card Payments via DTMF
Casa de Pizza & Wings

Uses Authorize.net to process credit/debit card payments.
Card data is collected via DTMF (phone keypad) and processed immediately.
No card data is stored — PCI compliant.
"""
import os
import json
import logging
import requests
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

# Authorize.net credentials
AUTHNET_LOGIN_ID = os.getenv("AUTHORIZE_NET_LOGIN_ID", "6j2x2ZVhyuV3")
AUTHNET_TRANSACTION_KEY = os.getenv("AUTHORIZE_NET_TRANSACTION_KEY", "")
AUTHNET_ENVIRONMENT = os.getenv("AUTHORIZE_NET_ENVIRONMENT", "production")

# Authorize.net API URLs
AUTHNET_URLS = {
    "sandbox": "https://apitest.authorize.net/xml/v1/request.api",
    "production": "https://api.authorize.net/xml/v1/request.api"
}

TAX_RATE = Decimal("0.08375")  # 8.375% Nevada tax
CONVENIENCE_FEE_RATE = Decimal("0.03")  # 3% convenience fee


def validate_card_data(card_number: str, exp_month: str, exp_year: str, cvv: str) -> dict:
    """Validate card data format before processing."""
    errors = []

    # Clean card number (remove spaces, dashes)
    clean_card = card_number.replace(" ", "").replace("-", "").replace("#", "")

    if not clean_card.isdigit():
        errors.append("Card number must contain only digits")
    elif len(clean_card) < 13 or len(clean_card) > 19:
        errors.append("Card number must be 13-19 digits")

    # Validate expiration
    clean_month = exp_month.replace("#", "").strip()
    clean_year = exp_year.replace("#", "").strip()

    if not clean_month.isdigit() or int(clean_month) < 1 or int(clean_month) > 12:
        errors.append("Expiration month must be 01-12")

    if not clean_year.isdigit() or len(clean_year) != 2:
        errors.append("Expiration year must be 2 digits")

    # Validate CVV
    clean_cvv = cvv.replace("#", "").strip()
    if not clean_cvv.isdigit() or len(clean_cvv) < 3 or len(clean_cvv) > 4:
        errors.append("CVV must be 3-4 digits")

    if errors:
        return {"valid": False, "errors": errors}

    return {
        "valid": True,
        "card_number": clean_card,
        "exp_month": clean_month,
        "exp_year": clean_year,
        "cvv": clean_cvv
    }


def process_payment(
    card_number: str,
    exp_month: str,
    exp_year: str,
    cvv: str,
    amount_cents: int,
    customer_name: str,
    customer_phone: str,
    order_type: str,
    items: list,
    delivery_address: str = None,
    language: str = "en"
) -> dict:
    """
    Process a credit/debit card payment via Authorize.net.

    Args:
        card_number: 16-digit card number (from DTMF)
        exp_month: 2-digit month (01-12)
        exp_year: 2-digit year (e.g., "27")
        cvv: 3-digit CVV
        amount_cents: Total amount in cents
        customer_name: Customer's name
        customer_phone: Customer's phone
        order_type: "pickup" or "delivery"
        items: List of ordered items
        delivery_address: Delivery address (if delivery)
        language: Language for confirmation ("en", "es", "ru")

    Returns:
        dict with success/failure info
    """
    # Validate card data
    validation = validate_card_data(card_number, exp_month, exp_year, cvv)
    if not validation["valid"]:
        return {
            "success": False,
            "error": "invalid_card_data",
            "message": f"Card validation failed: {', '.join(validation['errors'])}"
        }

    clean_card = validation["card_number"]
    clean_month = validation["exp_month"]
    clean_year = validation["exp_year"]
    clean_cvv = validation["cvv"]

    # Calculate amount in dollars
    amount_dollars = Decimal(amount_cents) / Decimal(100)
    amount_str = str(amount_dollars.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    # Build Authorize.net request
    api_url = AUTHNET_URLS.get(AUTHNET_ENVIRONMENT, AUTHNET_URLS["production"])

    # Build line items for the order
    line_items = []
    for i, item in enumerate(items[:30]):  # Authorize.net max 30 line items
        line_items.append({
            "lineItem": {
                "itemId": str(i + 1),
                "name": item.get("item_name", "Item")[:31],  # Max 31 chars
                "description": ", ".join(item.get("modifier_names", []))[:255] if item.get("modifier_names") else "",
                "quantity": str(item.get("quantity", 1)),
                "unitPrice": str(Decimal(item.get("unit_price_cents", 0)) / Decimal(100))
            }
        })

    # First name / last name split
    name_parts = customer_name.strip().split(" ", 1)
    first_name = name_parts[0] if name_parts else "Customer"
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    payload = {
        "createTransactionRequest": {
            "merchantAuthentication": {
                "name": AUTHNET_LOGIN_ID,
                "transactionKey": AUTHNET_TRANSACTION_KEY
            },
            "transactionRequest": {
                "transactionType": "authCaptureTransaction",
                "amount": amount_str,
                "payment": {
                    "creditCard": {
                        "cardNumber": clean_card,
                        "expirationDate": f"20{clean_year}-{clean_month}",
                        "cardCode": clean_cvv
                    }
                },
                "order": {
                    "invoiceNumber": f"NOA-{customer_phone[-4:]}",
                    "description": f"Casa de Pizza - {order_type.title()} Order"
                },
                "lineItems": {"lineItem": [li["lineItem"] for li in line_items]} if line_items else None,
                "customer": {
                    "type": "individual",
                    "email": ""
                },
                "billTo": {
                    "firstName": first_name,
                    "lastName": last_name,
                    "phone": customer_phone
                },
                "shipTo": {
                    "firstName": first_name,
                    "lastName": last_name,
                    "address": delivery_address or "765 N Nellis Blvd Suite 10",
                    "city": "Las Vegas",
                    "state": "NV",
                    "zip": "89110"
                },
                "customerIP": "0.0.0.0",
                "retail": {
                    "marketType": "2",  # MOTO (Mail Order / Telephone Order)
                    "deviceType": "8"   # Website/Phone
                },
                "transactionSettings": {
                    "setting": [
                        {
                            "settingName": "duplicateWindow",
                            "settingValue": "60"
                        }
                    ]
                }
            }
        }
    }

    # Remove None values
    if not line_items:
        del payload["createTransactionRequest"]["transactionRequest"]["lineItems"]

    try:
        logger.info(f"Processing payment: ${amount_str} for {customer_name} ({order_type})")

        response = requests.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        # Authorize.net returns JSON with BOM sometimes
        response_text = response.text.lstrip('\ufeff')
        result = json.loads(response_text)

        transaction_response = result.get("transactionResponse", {})
        messages = result.get("messages", {})

        response_code = transaction_response.get("responseCode")
        trans_id = transaction_response.get("transId", "")
        auth_code = transaction_response.get("authCode", "")

        if response_code == "1":  # Approved
            logger.info(f"✅ Payment approved: TransID={trans_id}, Auth={auth_code}")
            return {
                "success": True,
                "transaction_id": trans_id,
                "auth_code": auth_code,
                "amount": amount_str,
                "last_four": clean_card[-4:],
                "message": get_success_message(language, amount_str, order_type)
            }
        elif response_code == "2":  # Declined
            error_msg = ""
            if transaction_response.get("errors"):
                error_msg = transaction_response["errors"][0].get("errorText", "Card declined")
            logger.warning(f"❌ Payment declined: {error_msg}")
            return {
                "success": False,
                "error": "declined",
                "message": get_declined_message(language)
            }
        elif response_code == "3":  # Error
            error_msg = ""
            if transaction_response.get("errors"):
                error_msg = transaction_response["errors"][0].get("errorText", "Processing error")
            logger.error(f"❌ Payment error: {error_msg}")
            return {
                "success": False,
                "error": "processing_error",
                "message": get_error_message(language)
            }
        else:
            # Check messages for errors
            if messages.get("resultCode") == "Error":
                error_text = messages.get("message", [{}])[0].get("text", "Unknown error")
                logger.error(f"❌ API error: {error_text}")
                return {
                    "success": False,
                    "error": "api_error",
                    "message": get_error_message(language)
                }
            return {
                "success": False,
                "error": "unknown",
                "message": get_error_message(language)
            }

    except requests.exceptions.Timeout:
        logger.error("Payment request timed out")
        return {
            "success": False,
            "error": "timeout",
            "message": get_error_message(language)
        }
    except Exception as e:
        logger.error(f"Payment processing error: {str(e)}")
        return {
            "success": False,
            "error": "exception",
            "message": get_error_message(language)
        }


def get_success_message(language: str, amount: str, order_type: str) -> str:
    if language == "es":
        return f"¡Pago aprobado! Se cobró ${amount} a tu tarjeta. Tu orden para {('recoger' if order_type == 'pickup' else 'entrega')} está siendo preparada."
    elif language == "ru":
        ot = "самовывоз" if order_type == "pickup" else "доставку"
        return f"Оплата прошла! С вашей карты списано ${amount}. Ваш заказ на {ot} готовится."
    else:
        return f"Payment approved! ${amount} charged to your card. Your {order_type} order is being prepared now."


def get_declined_message(language: str) -> str:
    if language == "es":
        return "Lo siento, el pago fue rechazado. ¿Quieres intentar con otra tarjeta o te transfiero al restaurante?"
    elif language == "ru":
        return "Извините, платёж отклонён. Хотите попробовать другую карту или перевести вас на ресторан?"
    else:
        return "I'm sorry, the payment was declined. Would you like to try a different card, or should I transfer you to the restaurant?"


def get_error_message(language: str) -> str:
    if language == "es":
        return "Hubo un error procesando el pago. ¿Quieres intentar de nuevo o te transfiero al restaurante?"
    elif language == "ru":
        return "Произошла ошибка при обработке платежа. Хотите попробовать ещё раз или перевести вас на ресторан?"
    else:
        return "There was an error processing the payment. Would you like to try again, or should I transfer you to the restaurant?"
