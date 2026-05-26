"""
Casa de Pizza & Wings — Authorize.net Payment Service
Generates hosted payment page URLs via Authorize.net Accept Hosted.
"""
import os
import json
import hashlib
import hmac
import time
import requests
import logging

logger = logging.getLogger(__name__)

AUTHNET_SANDBOX_URL = "https://apitest.authorize.net/xml/v1/request.api"
AUTHNET_PROD_URL = "https://api.authorize.net/xml/v1/request.api"
AUTHNET_HOSTED_SANDBOX = "https://test.authorize.net/payment/payment"
AUTHNET_HOSTED_PROD = "https://accept.authorize.net/payment/payment"


class AuthorizeService:
    def __init__(self):
        self.api_login_id = os.getenv("AUTHNET_API_LOGIN_ID", "")
        self.transaction_key = os.getenv("AUTHNET_TRANSACTION_KEY", "")
        self.sandbox = os.getenv("AUTHNET_SANDBOX", "false").lower() == "true"
        self.enabled = bool(self.api_login_id and self.transaction_key)
        self.api_url = AUTHNET_SANDBOX_URL if self.sandbox else AUTHNET_PROD_URL
        self.hosted_url = AUTHNET_HOSTED_SANDBOX if self.sandbox else AUTHNET_HOSTED_PROD

        if self.enabled:
            mode = "SANDBOX" if self.sandbox else "PRODUCTION"
            logger.info(f"Authorize.net service initialized [{mode}] login_id={self.api_login_id[:4]}...")
        else:
            logger.warning("Authorize.net disabled — missing AUTHNET_API_LOGIN_ID or AUTHNET_TRANSACTION_KEY")

    def create_hosted_payment_page(self, amount: float, description: str, customer_name: str, customer_phone: str, order_id: str, backend_url: str) -> dict:
        """
        Create an Authorize.net Accept Hosted payment page token.
        Returns a URL the customer can visit to pay.
        """
        if not self.enabled:
            logger.warning("Authorize.net disabled — cannot create payment page")
            return {"success": False, "error": "Authorize.net not configured"}

        try:
            payload = {
                "getHostedPaymentPageRequest": {
                    "merchantAuthentication": {
                        "name": self.api_login_id,
                        "transactionKey": self.transaction_key
                    },
                    "transactionRequest": {
                        "transactionType": "authCaptureTransaction",
                        "amount": f"{amount:.2f}",
                        "order": {
                            "invoiceNumber": order_id[:20],
                            "description": description[:255]
                        },
                        "customer": {
                            "type": "individual",
                            "id": order_id
                        },
                        "billTo": {
                            "firstName": customer_name.split()[0] if customer_name else "Customer",
                            "lastName": " ".join(customer_name.split()[1:]) if len(customer_name.split()) > 1 else "."
                        }
                    },
                    "hostedPaymentSettings": {
                        "setting": [
                            {
                                "settingName": "hostedPaymentReturnOptions",
                                "settingValue": json.dumps({
                                    "showReceipt": True,
                                    "url": f"{backend_url}/payment/complete",
                                    "urlText": "Return to Casa de Pizza",
                                    "cancelUrl": f"{backend_url}/payment/cancel",
                                    "cancelUrlText": "Cancel"
                                })
                            },
                            {
                                "settingName": "hostedPaymentButtonOptions",
                                "settingValue": json.dumps({"text": "Pay Now"})
                            },
                            {
                                "settingName": "hostedPaymentStyleOptions",
                                "settingValue": json.dumps({"bgColor": "green"})
                            },
                            {
                                "settingName": "hostedPaymentPaymentOptions",
                                "settingValue": json.dumps({
                                    "cardCodeRequired": True,
                                    "showCreditCard": True,
                                    "showBankAccount": False
                                })
                            },
                            {
                                "settingName": "hostedPaymentSecurityOptions",
                                "settingValue": json.dumps({"captcha": False})
                            },
                            {
                                "settingName": "hostedPaymentShippingAddressOptions",
                                "settingValue": json.dumps({"show": False, "required": False})
                            },
                            {
                                "settingName": "hostedPaymentBillingAddressOptions",
                                "settingValue": json.dumps({"show": True, "required": False})
                            },
                            {
                                "settingName": "hostedPaymentCustomerOptions",
                                "settingValue": json.dumps({
                                    "showEmail": False,
                                    "requiredEmail": False,
                                    "addPaymentProfile": False
                                })
                            },
                            {
                                "settingName": "hostedPaymentOrderOptions",
                                "settingValue": json.dumps({
                                    "show": True,
                                    "merchantName": "Casa de Pizza & Wings"
                                })
                            }
                        ]
                    }
                }
            }

            r = requests.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=20
            )
            r.raise_for_status()
            data = r.json()

            # Remove BOM if present
            if isinstance(data, str):
                data = json.loads(data.lstrip('\ufeff'))

            if data.get("messages", {}).get("resultCode") == "Ok":
                token = data.get("token")
                payment_url = f"{self.hosted_url}?token={token}"
                logger.info(f"Authorize.net payment page created for order {order_id}: {payment_url[:60]}...")
                return {"success": True, "payment_url": payment_url, "token": token}
            else:
                errors = data.get("messages", {}).get("message", [])
                error_msg = errors[0].get("text", "Unknown error") if errors else "Unknown error"
                logger.error(f"Authorize.net error: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Authorize.net payment page creation failed: {e}")
            return {"success": False, "error": str(e)}
