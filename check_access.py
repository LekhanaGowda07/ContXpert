import os
import requests
from dotenv import load_dotenv

load_dotenv()

h = {"Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}"}
waba = "1015908851039978"
phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

for label, url in [
    ("WABA", f"https://graph.facebook.com/v21.0/{waba}?fields=id,name"),
    ("PHONE", f"https://graph.facebook.com/v21.0/{phone_id}?fields=id,display_phone_number"),
]:
    r = requests.get(url, headers=h, timeout=15)
    print(label, r.status_code, r.text)