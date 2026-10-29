"""End-to-end tests (no network). Run:  python -m unittest discover -s tests -v"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.update(WHATSAPP_MOCK="1", DISABLE_SCHEDULER="1", PAYMENT_MODE="mock", ADMIN_KEY="k",
                  WHATSAPP_APP_SECRET="s3cret", ANTHROPIC_API_KEY="", DB_PATH=tempfile.mktemp(suffix=".db"))

import app as app_module  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402
import whatsapp as wa  # noqa: E402
from ml import intent  # noqa: E402

PH = "919111111111"


def say(text="", rid=None, phone=PH):
    with wa.capture() as out:
        bot.handle_incoming(phone, text, rid)
    return out


def txt(out):
    return "\n".join(wa.render(p) for p in out)


class Flow(unittest.TestCase):
    def test_01_registration(self):
        self.assertIn("USN", txt(say("hi")))
        self.assertIn("registered mobile", txt(say("4MC23CS078")))
        self.assertIn("didn't match", txt(say("9111111111")))
        say("4MC23CS078")
        out = say("+91 90000 00078")
        self.assertIn("Verified", txt(out))
        self.assertEqual(out[-1]["interactive"]["type"], "list")
        self.assertEqual(db.get_user(PH)["usn"], "4MC23CS078")

    def test_02_other_phone_cannot_take_usn(self):
        say("hi", phone="919222222222")
        say("4MC23CS078", phone="919222222222")
        self.assertIn("already linked", txt(say("9000000078", phone="919222222222")))

    def test_03_lockout(self):
        p = "919333333333"
        for _ in range(5):
            say("4MC23CS079", phone=p)
            out = say("9111111111", phone=p)
        self.assertIn("locked", txt(out))
        self.assertIn("Too many", txt(say("4MC23CS079", phone=p)))

    def test_04_info_intents(self):
        for q, needle in [("attendance", "Attendance"), ("my internal marks", "CIE Marks"), ("fee status", "Fee Status"),
                          ("latest notices", "notifications"), ("certificate status", "no certificate requests"),
                          ("how am i doing overall", "Risk Report")]:
            self.assertIn(needle, txt(say(q)), q)
        self.assertTrue(say("timetable")[0]["interactive"]["action"]["buttons"])
        self.assertIn("Weekly timetable", txt(say("", "tt:week")))

    def test_05_menu_rows(self):
        out = say("menu")
        rows = out[0]["interactive"]["action"]["sections"][0]["rows"]
        self.assertEqual(len(rows), 9)
        for r in rows:
            self.assertLessEqual(len(r["title"]), 24)
            self.assertLessEqual(len(r.get("description", "")), 72)

    def test_06_menu_actions(self):
        for rid in ["m_attendance", "m_cie", "m_fees", "m_timetable", "m_notices", "m_calc", "m_cert", "m_risk", "m_ask"]:
            self.assertTrue(say("", rid), rid)

    def test_07_cie_calc(self):
        out = say("", "m_calc")
        code = out[0]["interactive"]["action"]["sections"][0]["rows"][0]["id"]
        out = say("", code)
        self.assertEqual(out[0]["interactive"]["type"], "button")
        self.assertIn("Marks needed in SEE", txt(say("72")))
        self.assertIn("Marks needed in SEE", txt(say("", out[0]["interactive"]["action"]["buttons"][0]["reply"]["id"])))

    def test_08_certificate_flow(self):
        out = say("I need a bonafide")
        self.assertEqual(out[0]["interactive"]["type"], "list")
        out = say("", "cert:bonafide")
        self.assertIn("Proceed", txt(out))
        self.assertIn("/pay/", txt(say("", "cert_pay:bonafide")))
        self.assertIn("unpaid request", txt(say("", "cert_pay:bonafide")))
        req = db.list_certs("4MC23CS078")[0]
        self.assertEqual(req["status"], "PENDING_PAYMENT")
        c = app_module.app.test_client()
        self.assertEqual(c.get(f"/pay/{req['id']}").status_code, 200)
        with wa.capture() as out:
            c.post(f"/pay/{req['id']}/confirm")
        self.assertIn("Payment received", txt(out))
        self.assertEqual(db.get_cert(req["id"])["status"], "PROCESSING")
        with wa.capture() as out:                                  # idempotent
            c.post(f"/pay/{req['id']}/confirm")
        self.assertEqual(out, [])
        self.assertEqual(c.post(f"/admin/certificates/{req['id']}/ready").status_code, 401)
        with wa.capture() as out:
            r = c.post(f"/admin/certificates/{req['id']}/ready", headers={"X-Admin-Key": "k"})
        self.assertTrue(r.get_json()["ok"])
        self.assertIn("ready", txt(out))
        self.assertIn("Ready", txt(say("certificate status")))

    def test_09_faq(self):
        self.assertIn("75%", txt(say("what is the minimum attendance required")))
        self.assertIn("couldn't find", txt(say("qwertyuiop zxcvb")))

    def test_10_alerts(self):
        import alerts
        with wa.capture() as out:
            n = alerts.run_attendance_alerts(force=True)
        self.assertIsInstance(n, int)

    def test_11_webhook(self):
        c = app_module.app.test_client()
        r = c.get("/webhook?hub.mode=subscribe&hub.verify_token=contxpert_verify_123&hub.challenge=777")
        self.assertEqual((r.status_code, r.get_data(as_text=True)), (200, "777"))
        self.assertEqual(c.get("/webhook?hub.mode=subscribe&hub.verify_token=bad&hub.challenge=1").status_code, 403)
        body = json.dumps({"entry": [{"changes": [{"value": {"messages": []}}]}]}).encode()
        sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        self.assertEqual(c.post("/webhook", data=body, headers={"X-Hub-Signature-256": sig}).status_code, 200)
        self.assertEqual(c.post("/webhook", data=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code, 403)
        with wa.capture() as out:                                    # message parsing
            app_module.process_message({"from": PH, "type": "interactive", "id": "x",
                                        "interactive": {"type": "list_reply", "list_reply": {"id": "m_fees", "title": "Fee"}}})
            app_module.process_message({"from": PH, "type": "image", "id": "y"})
        self.assertIn("Fee Status", txt(out))
        self.assertIn("only read text", txt(out))
        self.assertTrue(db.mark_processed("dup"))
        self.assertFalse(db.mark_processed("dup"))

    def test_12_simulate_and_logout(self):
        c = app_module.app.test_client()
        r = c.post("/simulate", json={"phone": PH, "text": "unlink my number"})
        self.assertIn("Unlink", r.get_json()[0]["text"])
        r = c.post("/simulate", json={"phone": PH, "reply_id": "logout_yes"})
        self.assertIn("unlinked", r.get_json()[0]["text"])
        self.assertIsNone(db.get_user(PH))

    def test_14_mobile_only_login(self):
        stu = db.get_student("4MC23CS080")
        phone = "91" + stu["mobile"]
        out = say("hello", phone=phone)                  # first message from the registered number -> auto login
        self.assertIn("registered mobile number", txt(out))
        self.assertEqual(db.get_user(phone)["usn"], "4MC23CS080")
        self.assertIn("Attendance", txt(say("attendance", phone=phone)))

    def test_15_strict_mode(self):
        import config
        config.STRICT_MOBILE_MATCH = True
        try:
            stu = db.get_student("4MC23CS079")
            p = "919444444444"                           # a different number than the registered one
            say("hi", phone=p)
            say("4MC23CS079", phone=p)
            self.assertIn("registered mobile number", txt(say(stu["mobile"], phone=p)))
            self.assertIsNone(db.get_user(p))
        finally:
            config.STRICT_MOBILE_MATCH = False

    def test_06a_cie_scheme(self):
        out = txt(say("cie marks"))
        for label in ("CIE-1", "CIE-2", "CIE-3", "ACT-1", "ACT-2"):
            self.assertIn(label, out)

    def test_13_intent_model(self):
        for q, want in [("attendence kitna hai", "attendance"), ("bonafide please", "certificate"),
                        ("how many marks needed in see", "cie_calc"), ("library timings", "faq")]:
            self.assertEqual(intent.predict(q)[0], want, q)


if __name__ == "__main__":
    unittest.main()