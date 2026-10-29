import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("WHATSAPP_TOKEN")
print("LENGTH:", len(token or ""), "| ENDS WITH:", (token or "")[-6:])

r = requests.get(
    "https://graph.facebook.com/v21.0/debug_token",
    params={"input_token": token, "access_token": token},
    timeout=15,
)
d = r.json().get("data", {})
print("VALID:", d.get("is_valid"))
print("APP:", d.get("application"), "| TYPE:", d.get("type"))
print("EXPIRES:", d.get("expires_at"), "(0 = never)")
print("SCOPES:", d.get("scopes"))
print("GRANULAR:", d.get("granular_scopes"))
print("RAW ERROR:", r.json().get("error"))