"""
Purchase the phone number +17252391803 for Casa de Pizza & Wings via Twilio API.
"""
import re
import requests
import json

# Load credentials from napoli .env
with open('/home/ubuntu/napoli-voice-agent/.env', 'r') as f:
    content = f.read()

sid = re.search(r'TWILIO_ACCOUNT_SID=(.+)', content).group(1).strip()
token = re.search(r'TWILIO_AUTH_TOKEN=(.+)', content).group(1).strip()

PHONE_TO_BUY = "+17252391803"

url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json"

payload = {
    "PhoneNumber": PHONE_TO_BUY,
    "FriendlyName": "Casa de Pizza & Wings - AI Agent",
    "VoiceMethod": "POST",
    "SmsMethod": "POST",
}

print(f"Purchasing {PHONE_TO_BUY}...")
r = requests.post(url, auth=(sid, token), data=payload)

if r.status_code in (200, 201):
    data = r.json()
    print(f"\n✅ SUCCESS! Number purchased:")
    print(f"  Phone Number: {data['phone_number']}")
    print(f"  Friendly Name: {data['friendly_name']}")
    print(f"  SID: {data['sid']}")
    print(f"  Date Created: {data['date_created']}")
    print(f"\nSave this SID: {data['sid']}")
else:
    print(f"\n❌ FAILED: {r.status_code}")
    print(r.text)
