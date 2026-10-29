import os
import requests
from dotenv import load_dotenv

load_dotenv()

USN = "4MC23CS078"  # replace with the real USN from students.csv

r = requests.post(
    f"http://localhost:5000/admin/unlink/{USN}",
    headers={"X-Admin-Key": os.getenv("ADMIN_KEY")},
    timeout=15,
)
print(r.status_code, r.text)