"""
Casa de Pizza & Wings — Twilio SMS Service
"""
import os
import logging

logger = logging.getLogger(__name__)

class SMSService:
    def __init__(self):
        import os as _os
        twilio_sid = _os.getenv("TWILIO_ACCOUNT_SID", "")
        twilio_token = _os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_phone = _os.getenv("TWILIO_PHONE_NUMBER", "")
        self.enabled = bool(twilio_sid and twilio_token and self.twilio_phone)

        if self.enabled:
            from twilio.rest import Client
            self.client = Client(twilio_sid, twilio_token)
            logger.info(f"SMS service initialized with phone: {self.twilio_phone}")
        else:
            self.client = None
            logger.warning("SMS service disabled — missing Twilio credentials")

    def send_payment_link(self, to_phone: str, customer_name: str, payment_url: str, total: float, order_id: str) -> bool:
        """Send payment link via SMS."""
        if not self.enabled:
            logger.warning(f"SMS disabled — would send to {to_phone}: {payment_url}")
            return False

        # Normalize phone number
        phone = to_phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone.startswith("+"):
            phone = f"+1{phone}" if len(phone) == 10 else f"+{phone}"

        message = (
            f"Hi {customer_name}! 🍕 Casa de Pizza & Wings\n"
            f"Your order total: ${total:.2f}\n"
            f"Pay here: {payment_url}\n"
            f"Order #{order_id[-6:].upper()} | Link expires in 30 min\n"
            f"Questions? Call 702-200-5252"
        )

        try:
            msg = self.client.messages.create(
                body=message,
                from_=self.twilio_phone,
                to=phone
            )
            logger.info(f"SMS sent to {phone} — SID: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"SMS send failed to {phone}: {e}")
            return False

    def send_custom(self, to_phone: str, message: str) -> bool:
        """Send a custom SMS message."""
        if not self.enabled:
            logger.warning(f"SMS disabled — would send to {to_phone}")
            return False

        phone = to_phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone.startswith("+"):
            phone = f"+1{phone}" if len(phone) == 10 else f"+{phone}"

        try:
            msg = self.client.messages.create(
                body=message,
                from_=self.twilio_phone,
                to=phone
            )
            logger.info(f"Custom SMS sent to {phone} — SID: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"Custom SMS failed to {phone}: {e}")
            return False
