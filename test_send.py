import os
import requests
from dotenv import load_dotenv

load_dotenv()

url = f"https://graph.facebook.com/v21.0/{os.getenv('WHATSAPP_PHONE_NUMBER_ID')}/messages"
headers = {
    "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
    "Content-Type": "application/json",
}
payload = {
    "messaging_product": "whatsapp",
    "to": "918088848680",
    "type": "text",
    "text": {"body": "Hello from ContXpert"},
}
r = requests.post(url, headers=headers, json=payload, timeout=15)
print(r.status_code, r.text)