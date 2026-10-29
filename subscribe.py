import os
import requests
from dotenv import load_dotenv

load_dotenv()

waba = os.getenv("WABA_ID")
headers = {"Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}"}
url = f"https://graph.facebook.com/v21.0/{waba}/subscribed_apps"

r = requests.post(url, headers=headers, timeout=15)
print("SUBSCRIBE:", r.status_code, r.text)

r = requests.get(url, headers=headers, timeout=15)
print("CURRENT:", r.status_code, r.text)