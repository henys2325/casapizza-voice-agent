"""Verify Authorize.net credentials."""
import requests, json

api_login = '6j2x2ZVhyuV3'
trans_key = '7a4MCPj4Q74a43v6'

payload = {
    'authenticateTestRequest': {
        'merchantAuthentication': {
            'name': api_login,
            'transactionKey': trans_key
        }
    }
}

r = requests.post('https://api.authorize.net/xml/v1/request.api', json=payload, timeout=15)
# Handle BOM
text = r.text.lstrip('\ufeff')
data = json.loads(text)
result = data.get('messages', {}).get('resultCode', 'Unknown')
msg = data.get('messages', {}).get('message', [{}])[0].get('text', '')
print(f'Status: {r.status_code}')
print(f'Result: {result}')
print(f'Message: {msg}')
if result == 'Ok':
    print('✅ Authorize.net credentials are VALID (Production)')
else:
    print('❌ Credentials invalid or sandbox mode needed')
