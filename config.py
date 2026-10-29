"""Central configuration. Everything can be overridden through environment variables / .env"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(name, default="0"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# ---- WhatsApp Cloud API ----
WHATSAPP_MOCK = _bool("WHATSAPP_MOCK", "1")
WA_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WA_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "contxpert_verify_123")
WA_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
GRAPH_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")
WA_TEMPLATE_ALERT = os.getenv("WHATSAPP_TEMPLATE_ALERT", "")
WA_TEMPLATE_LANG = os.getenv("WHATSAPP_TEMPLATE_LANG", "en")

# ---- Server ----
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")
PORT = int(os.getenv("PORT", "5000"))
ADMIN_KEY = os.getenv("ADMIN_KEY", "change-me")

# ---- Storage ----
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "contxpert.db"))

# ---- Payments ----
PAYMENT_MODE = os.getenv("PAYMENT_MODE", "mock").lower()  # mock | razorpay
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

# ---- LLM (optional) ----
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# ---- Academic rules (EDIT THESE to match MCE regulations) ----
ATTENDANCE_THRESHOLD = float(os.getenv("ATTENDANCE_THRESHOLD", "75"))  # percent
# (csv column, label, max marks). CIE total = sum of maxima.
CIE_COMPONENTS = [("cie1", "CIE-1", 10), ("cie2", "CIE-2", 10), ("cie3", "CIE-3", 10),
                  ("act1", "ACT-1", 10), ("act2", "ACT-2", 10)]
CIE_MAX = sum(c[2] for c in CIE_COMPONENTS)  # 50
SEE_MAX = 100          # SEE paper is conducted for 100 ...
TOTAL_MAX = 100        # ... and scaled so that CIE + scaled SEE = 100
SEE_WEIGHT = (TOTAL_MAX - CIE_MAX) / SEE_MAX  # 0.5
MIN_SEE_RAW = 35       # minimum marks (out of 100) needed in SEE to pass
PASS_TOTAL = 40        # minimum total (out of 100) to pass

# ---- Alerts ----
ALERT_HOUR = int(os.getenv("ALERT_HOUR", "9"))                   # IST
ALERT_COOLDOWN_DAYS = int(os.getenv("ALERT_COOLDOWN_DAYS", "3"))

# ---- Certificates: key -> (label, fee in INR, turnaround) ----
CERTIFICATES = {
    "bonafide": ("Bonafide Certificate", 100, "2 working days"),
    "study": ("Study Certificate", 100, "2 working days"),
    "conduct": ("Conduct Certificate", 100, "3 working days"),
    "transcript": ("Transcript (1 copy)", 500, "5 working days"),
    "noc": ("NOC / Internship Letter", 150, "3 working days"),
}

# ---- Registration security ----
# Login needs USN + DOB + the WhatsApp sender's own number == registered mobile (country code + 10 digits).
COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "91")
MAX_REG_FAILS = 5
REG_LOCK_MINUTES = 30