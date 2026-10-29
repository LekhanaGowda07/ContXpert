"""Certificate payments. PAYMENT_MODE=mock -> a fake checkout page served by this app (/pay/<id>).
PAYMENT_MODE=razorpay -> Razorpay Payment Links + signed webhook."""
import hashlib
import hmac
import json
import logging

import requests

import config
import db
import whatsapp as wa

log = logging.getLogger("payments")


def create_payment(req_id, amount, student, phone, description):
    """Returns (payment_link, reference)."""
    if config.PAYMENT_MODE == "razorpay":
        r = requests.post(
            "https://api.razorpay.com/v1/payment_links",
            auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET),
            json={"amount": int(amount) * 100, "currency": "INR", "accept_partial": False,
                  "description": description, "reference_id": f"cert-{req_id}",
                  "customer": {"name": student["name"], "contact": "+" + phone},
                  "notify": {"sms": False, "email": False}, "reminder_enable": False},
            timeout=20)
        r.raise_for_status()
        j = r.json()
        return j["short_url"], j["id"]
    return f"{config.BASE_URL}/pay/{req_id}", f"MOCK-{req_id}"


def verify_razorpay_signature(raw_body, signature):
    if not config.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(config.RAZORPAY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def mark_paid(req_id, ref=None):
    """Idempotent: only the first call (PENDING_PAYMENT -> PROCESSING) notifies the student."""
    if not db.set_cert_status(req_id, "PROCESSING", expected="PENDING_PAYMENT", payment_ref=ref):
        return False
    c = db.get_cert(req_id)
    label = config.CERTIFICATES.get(c["cert_type"], (c["cert_type"],))[0]
    wa.send_text(c["phone"], f"✅ *Payment received* - Rs.{c['amount']}\n"
                             f"Your request #{c['id']} for *{label}* is now being processed. "
                             f"I'll message you here as soon as it is ready.")
    return True


def mark_ready(req_id):
    if not db.set_cert_status(req_id, "READY", expected="PROCESSING"):
        return False
    c = db.get_cert(req_id)
    label = config.CERTIFICATES.get(c["cert_type"], (c["cert_type"],))[0]
    wa.send_text(c["phone"], f"🎉 Your *{label}* (request #{c['id']}) is *ready*! "
                             f"Please collect it from the department office with your college ID.")
    return True
