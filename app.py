"""Flask server: WhatsApp webhook, mock payment page, Razorpay webhook, admin endpoints."""
import hashlib
import hmac
import html
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, Response, jsonify, request

import alerts
import bot
import config
import db
import payments
import whatsapp as wa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=4)


# ------------------------------------------------------------------ health
@app.get("/")
def health():
    return jsonify(status="ok", service="ContXpert", whatsapp_mock=config.WHATSAPP_MOCK,
                   payment_mode=config.PAYMENT_MODE)


# ------------------------------------------------------------------ WhatsApp webhook
@app.get("/webhook")
def webhook_verify():
    """Meta calls this once when you click 'Verify and save'."""
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == config.WA_VERIFY_TOKEN:
        return Response(request.args.get("hub.challenge", ""), 200, mimetype="text/plain")
    return Response("Forbidden", 403)


@app.post("/webhook")
def webhook_receive():
    raw = request.get_data()
    if config.WA_APP_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(config.WA_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return Response("Invalid signature", 403)
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        return Response("Bad JSON", 400)
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                log.info("INCOMING from=%s type=%s text=%s", msg.get("from"), msg.get("type"),
                         (msg.get("text") or {}).get("body"))
                if db.mark_processed(msg.get("id")):          # Meta retries -> de-duplicate
                    executor.submit(process_message, msg, names.get(msg.get("from")))
    return "OK", 200                                          # always answer fast; work happens in background


def process_message(msg, name=None):
    try:
        phone, mtype = msg["from"], msg.get("type")
        text, rid = "", None
        if mtype == "text":
            text = msg["text"]["body"]
        elif mtype == "interactive":
            i = msg["interactive"]
            r = i.get("button_reply") or i.get("list_reply") or {}
            rid, text = r.get("id"), r.get("title", "")
        elif mtype == "button":                               # quick-reply button of a template message
            text = (msg.get("button") or {}).get("text", "")
        else:
            return wa.send_text(phone, "I can only read text messages for now. Type *menu* to see what I can do.")
        bot.handle_incoming(phone, text, rid, name)
    except Exception:
        log.exception("failed to process message")


# ------------------------------------------------------------------ payments
PAY_PAGE = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>Mock payment</title><style>body{{font-family:system-ui;max-width:420px;margin:12vh auto;padding:0 20px;text-align:center}}
button{{background:#16a34a;color:#fff;border:0;padding:14px 28px;font-size:18px;border-radius:10px;cursor:pointer}}</style></head>
<body><h2>ContXpert - Mock Checkout</h2><p>{label}<br><b>Rs.{amount}</b></p>{body}</body></html>"""


@app.get("/pay/<int:req_id>")
def pay_page(req_id):
    c = db.get_cert(req_id)
    if config.PAYMENT_MODE != "mock" or not c:
        return Response("Not found", 404)
    label = html.escape(config.CERTIFICATES.get(c["cert_type"], (c["cert_type"],))[0])
    if c["status"] == "PENDING_PAYMENT":
        body = f'<form method="post" action="/pay/{req_id}/confirm"><button type="submit">Pay now (mock)</button></form>'
    else:
        body = "<p>✅ Already paid. You can close this page and return to WhatsApp.</p>"
    return PAY_PAGE.format(label=label, amount=c["amount"], body=body)


@app.post("/pay/<int:req_id>/confirm")
def pay_confirm(req_id):
    if config.PAYMENT_MODE != "mock" or not db.get_cert(req_id):
        return Response("Not found", 404)
    payments.mark_paid(req_id, f"MOCK-PAID-{req_id}")
    return PAY_PAGE.format(label="Payment successful", amount=db.get_cert(req_id)["amount"],
                           body="<p>✅ Done! Return to WhatsApp - you'll get a confirmation there.</p>")


@app.post("/razorpay/webhook")
def razorpay_webhook():
    raw = request.get_data()
    if not payments.verify_razorpay_signature(raw, request.headers.get("X-Razorpay-Signature", "")):
        return Response("Invalid signature", 403)
    event = json.loads(raw)
    if event.get("event") == "payment_link.paid":
        ent = event["payload"]["payment_link"]["entity"]
        ref = str(ent.get("reference_id", ""))
        if ref.startswith("cert-") and ref[5:].isdigit():
            payments.mark_paid(int(ref[5:]), ent.get("id"))
    return "OK", 200


# ------------------------------------------------------------------ admin (certificate office)
def _admin_ok():
    return hmac.compare_digest(request.headers.get("X-Admin-Key", ""), config.ADMIN_KEY)


@app.get("/admin/certificates")
def admin_list():
    if not _admin_ok():
        return Response("Unauthorized", 401)
    return jsonify(db.list_all_certs(request.args.get("status")))


@app.post("/admin/certificates/<int:req_id>/ready")
def admin_ready(req_id):
    if not _admin_ok():
        return Response("Unauthorized", 401)
    ok = payments.mark_ready(req_id)
    return jsonify(ok=ok, note=None if ok else "Request must exist and be in PROCESSING (paid) state")


@app.post("/admin/unlink/<usn>")
def admin_unlink(usn):
    if not _admin_ok():
        return Response("Unauthorized", 401)
    return jsonify(unlinked=db.unbind_user(usn=usn))


@app.post("/admin/run-alerts")
def admin_alerts():
    if not _admin_ok():
        return Response("Unauthorized", 401)
    return jsonify(sent=alerts.run_attendance_alerts(force=request.args.get("force") == "1"))


# ------------------------------------------------------------------ simulator (mock mode only)
@app.post("/simulate")
def simulate():
    """curl -X POST localhost:5000/simulate -H 'Content-Type: application/json' -d '{"phone":"919999999999","text":"hi"}'"""
    if not config.WHATSAPP_MOCK:
        return Response("Disabled when WHATSAPP_MOCK=0", 403)
    j = request.get_json(force=True, silent=True) or {}
    with wa.capture() as out:
        bot.handle_incoming(str(j.get("phone", "910000000000")), j.get("text", ""), j.get("reply_id"))
    return jsonify([{"text": wa.render(p), "options": wa.options(p)} for p in out])


# ------------------------------------------------------------------ startup
def init():
    db.init_db()
    if os.getenv("DISABLE_SCHEDULER") != "1":
        alerts.start_scheduler()
    if not config.WHATSAPP_MOCK and not (config.WA_TOKEN and config.WA_PHONE_ID):
        log.warning("WHATSAPP_MOCK=0 but WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID are not set!")
    if not config.WA_APP_SECRET:
        log.warning("WHATSAPP_APP_SECRET not set - webhook signatures are NOT being verified.")


init()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=False)