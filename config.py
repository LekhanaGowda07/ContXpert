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

# ---- Storage (PostgreSQL) ----
DATABASE_URL = os.getenv("DATABASE_URL", "")          # e.g. postgresql://user:password@host:5432/dbname
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))   # CSV files used to seed an EMPTY database
AUTO_SEED_CSV = _bool("AUTO_SEED_CSV", "1")           # import ./data/*.csv when the students table is empty
CSV_SYNC = _bool("CSV_SYNC", "0")                     # 1 = wipe + re-import the CSVs on EVERY start (old behaviour)

# ---- Payments ----
PAYMENT_MODE = os.getenv("PAYMENT_MODE", "mock").lower()  # mock | razorpay
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

# ---- LLM (optional) ----
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "")   # put the Gemini model name you use here or in .env

# ---- Academic rules (EDIT THESE to match MCE regulations) ----
ATTENDANCE_THRESHOLD = float(os.getenv("ATTENDANCE_THRESHOLD", "75"))  # percent
# (csv column, label, max marks). CIE total = sum of maxima.
# !! Set the real max marks for each component below (the numbers here are placeholders) !!
CIE_COMPONENTS = [
    ("cie1", "CIE-1", 20),
    ("cie2", "CIE-2", 20),
    ("cie3", "CIE-3", 20),
    ("act1", "Activity-1", 10),
    ("act2", "Activity-2", 10),
]
CIE_MAX = sum(c[2] for c in CIE_COMPONENTS)
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
    "bonafide": ("Bonafide Certificate", int(os.getenv("CERT_FEE_BONAFIDE", "100")), "2 working days"),
    "study": ("Study Certificate", int(os.getenv("CERT_FEE_STUDY", "100")), "2 working days"),
    "conduct": ("Conduct Certificate", int(os.getenv("CERT_FEE_CONDUCT", "100")), "3 working days"),
    "transcript": ("Transcript (1 copy)", int(os.getenv("CERT_FEE_TRANSCRIPT", "500")), "5 working days"),
    "noc": ("NOC / Internship Letter", int(os.getenv("CERT_FEE_NOC", "150")), "3 working days"),
}

# ---- Registration security ----
MAX_REG_FAILS = 5
REG_LOCK_MINUTES = 30