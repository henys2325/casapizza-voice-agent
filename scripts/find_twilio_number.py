"""
Search for available 702/725 Las Vegas phone numbers via Twilio API.
Uses the AvailablePhoneNumbers endpoint which has more inventory than the UI.
"""
import re
import requests
import json

# Load credentials from napoli .env
with open('/home/ubuntu/napoli-voice-agent/.env', 'r') as f:
    content = f.read()

sid = re.search(r'TWILIO_ACCOUNT_SID=(.+)', content).group(1).strip()
token = re.search(r'TWILIO_AUTH_TOKEN=(.+)', content).group(1).strip()

base = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/AvailablePhoneNumbers/US"

def search_numbers(area_code=None, region=None, contains=None, label=""):
    params = {
        "VoiceEnabled": "true",
        "SmsEnabled": "true",
        "PageSize": 20,
    }
    if area_code:
        params["AreaCode"] = area_code
    if region:
        params["InRegion"] = region
    if contains:
        params["Contains"] = contains

    url = f"{base}/Local.json"
    r = requests.get(url, auth=(sid, token), params=params)
    data = r.json()
    numbers = data.get("available_phone_numbers", [])
    print(f"\n{'='*50}")
    print(f"Search: {label} → {len(numbers)} results")
    for n in numbers[:10]:
        print(f"  {n['phone_number']}  {n.get('locality','')}, {n.get('region','')}  ${n.get('monthly_rate','?')}/mo")
    return numbers

# Try 702 area code
n702 = search_numbers(area_code="702", label="Area code 702 (Las Vegas)")

# Try 725 area code
n725 = search_numbers(area_code="725", label="Area code 725 (Las Vegas)")

# Try Nevada state (any area code)
nnv = search_numbers(region="NV", label="Any Nevada number")

# Try toll-free
url_tf = f"{base}/TollFree.json"
r_tf = requests.get(url_tf, auth=(sid, token), params={"VoiceEnabled": "true", "SmsEnabled": "true", "PageSize": 10})
tf_data = r_tf.json()
tf_numbers = tf_data.get("available_phone_numbers", [])
print(f"\n{'='*50}")
print(f"Toll-Free numbers → {len(tf_numbers)} results")
for n in tf_numbers[:5]:
    print(f"  {n['phone_number']}  ${n.get('monthly_rate','?')}/mo")

# Summary
all_702_725 = [n for n in n702 + n725 if n['phone_number'].startswith(('+1702', '+1725'))]
print(f"\n{'='*50}")
print(f"SUMMARY:")
print(f"  702 numbers available: {len(n702)}")
print(f"  725 numbers available: {len(n725)}")
print(f"  Nevada (any) numbers: {len(nnv)}")
print(f"  Toll-free numbers: {len(tf_numbers)}")

if all_702_725:
    print(f"\n✅ BEST OPTION — Las Vegas 702/725 number:")
    best = all_702_725[0]
    print(f"  {best['phone_number']} — {best.get('locality','')}, NV")
elif nnv:
    print(f"\n⚠️  No 702/725 available. Best Nevada option:")
    best = nnv[0]
    print(f"  {best['phone_number']} — {best.get('locality','')}, NV")
elif tf_numbers:
    print(f"\n⚠️  No local NV available. Best toll-free option:")
    best = tf_numbers[0]
    print(f"  {best['phone_number']}")
else:
    print("\n❌ No numbers found at all.")
    best = None

if best:
    print(f"\nTo purchase: {best['phone_number']}")
