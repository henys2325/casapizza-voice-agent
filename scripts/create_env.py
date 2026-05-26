"""Generate .env file for Casa de Pizza & Wings."""
import re

# Load from napoli .env
with open('/home/ubuntu/napoli-voice-agent/.env', 'r') as f:
    napoli = f.read()

def get(key):
    m = re.search(rf'{key}=(.+)', napoli)
    return m.group(1).strip() if m else ''

twilio_sid = get('TWILIO_ACCOUNT_SID')
twilio_token = get('TWILIO_AUTH_TOKEN')
vapi_key = get('VAPI_API_KEY')

# Casa de Pizza specific Clover credentials (from user's images)
# WPAPItoken: 13fd6685-ec43-ade7-205e-77aea1a1d97d
# Clover eComm API Public: b5ea387525d5796202088198fe091536
# Clover eComm API Private: 93f18cbe-4cfd-7849-21dc-82beefa55dbb

env_content = f"""# Casa de Pizza & Wings — Voice AI Agent
# Generated automatically

# ─── Server ─────────────────────────────────────────────
APP_PORT=8000
BACKEND_URL=https://casapizza-voice-agent.onrender.com
RESTAURANT_NAME=Casa de Pizza & Wings
RESTAURANT_ADDRESS=765 N Nellis Blvd Suite 10, Las Vegas, NV 89110
RESTAURANT_PHONE=7022005252
TAX_RATE=0.0838

# ─── Twilio (shared account) ────────────────────────────
TWILIO_ACCOUNT_SID={twilio_sid}
TWILIO_AUTH_TOKEN={twilio_token}
TWILIO_PHONE_NUMBER=+17252391803

# ─── Vapi ───────────────────────────────────────────────
VAPI_API_KEY={vapi_key}
VAPI_AGENT_ID=d6654d57-e84b-4f82-967f-7a30776b1df3
VAPI_WEBHOOK_SECRET=casapizza2026

# ─── Clover POS ─────────────────────────────────────────
CLOVER_API_TOKEN=13fd6685-ec43-ade7-205e-77aea1a1d97d
CLOVER_ECOMM_PUBLIC_TOKEN=b5ea387525d5796202088198fe091536
CLOVER_ECOMM_PRIVATE_TOKEN=93f18cbe-4cfd-7849-21dc-82beefa55dbb
CLOVER_MERCHANT_ID=

# ─── Authorize.net ──────────────────────────────────────
AUTHNET_API_LOGIN_ID=6j2x2ZVhyuV3
AUTHNET_TRANSACTION_KEY=7a4MCPj4Q74a43v6
AUTHNET_SANDBOX=false
"""

with open('/home/ubuntu/casapizza-voice-agent/.env', 'w') as f:
    f.write(env_content)

print("✅ .env file created for Casa de Pizza & Wings")
print("\nKey variables:")
print(f"  TWILIO_PHONE_NUMBER: +17252391803")
print(f"  VAPI_AGENT_ID: d6654d57-e84b-4f82-967f-7a30776b1df3")
print(f"  AUTHNET_API_LOGIN_ID: 6j2x2ZVhyuV3")
print(f"  BACKEND_URL: https://casapizza-voice-agent.onrender.com")
