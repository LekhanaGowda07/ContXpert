"""Conversation logic: registration, menu, intents, multi-step flows (CIE planner, certificates)."""
import hmac
import logging
import re
import threading
from datetime import datetime, timedelta, timezone

import config
import db
import llm
import payments
import services
import whatsapp as wa
from ml import intent as intent_model
from ml import rag
from ml import risk as risk_model

log = logging.getLogger("bot")
USN_RE = re.compile(r"\b[0-9][A-Za-z]{2}\d{2}[A-Za-z]{2,3}\d{3}\b")
FOOTER = "\n\nType *menu* for options."

MENU_ROWS = [
    ("m_attendance", "📊 Attendance", "Subject-wise % and classes you can miss"),
    ("m_cie", "📝 CIE Marks", "CIE-1/2/3 and ACT-1/2 marks"),
    ("m_fees", "💰 Fee Status", "Paid, due and last date"),
    ("m_timetable", "🗓️ Timetable", "Today, tomorrow or full week"),
    ("m_notices", "🔔 Notifications", "Latest circulars for you"),
    ("m_calc", "🧮 CIE Calculator", "Marks needed in SEE for your target"),
    ("m_cert", "📜 Certificates", "Request & pay for certificates"),
    ("m_risk", "🤖 AI Risk Report", "AI analysis of your academic health"),
    ("m_ask", "💬 Ask a Question", "College rules, exams, FAQs"),
]
MENU_INTENT = {"m_attendance": "attendance", "m_cie": "cie", "m_fees": "fees", "m_timetable": "timetable",
               "m_notices": "notifications", "m_calc": "cie_calc", "m_cert": "certificate", "m_risk": "risk",
               "m_ask": "ask"}
STATUS_LABEL = {"PENDING_PAYMENT": "⏳ Awaiting payment", "PROCESSING": "🔄 Processing",
                "READY": "✅ Ready for collection", "CANCELLED": "❌ Cancelled"}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_locks, _locks_guard = {}, threading.Lock()


def _lock_for(phone):
    with _locks_guard:
        return _locks.setdefault(phone, threading.Lock())


# ====================================================================== entry point
def handle_incoming(phone, text="", reply_id=None, name=None):
    """Process one incoming WhatsApp message (text and/or interactive reply id)."""
    with _lock_for(phone):
        try:
            _handle(phone, (text or "").strip(), reply_id, name)
        except Exception:
            log.exception("Error while handling message from %s", phone)
            wa.send_text(phone, "⚠️ Something went wrong on my side. Please try again in a moment.")


def _handle(phone, text, reply_id, name):
    user = db.get_user(phone)
    if not user:
        return _registration(phone, text)
    student = db.get_student(user["usn"])
    if not student:
        db.unbind_user(phone=phone)
        wa.send_text(phone, "I couldn't find your record any more, so I've unlinked this number. "
                            "Please send your *USN* to log in again.")
        db.set_session(phone, "REG_USN", {})
        return
    low = text.lower().strip()
    if reply_id == "m_menu" or low in ("menu", "cancel", "0"):
        db.clear_session(phone)
        return send_menu(phone, student)
    if reply_id and _handle_reply(phone, user, student, reply_id):
        return
    sess = db.get_session(phone)
    if sess and _continue_flow(phone, student, sess, text):
        return
    intent, conf = intent_model.predict(text)
    log.info("intent=%s conf=%.2f text=%r", intent, conf, text[:60])
    _dispatch(phone, student, intent, text)


# ====================================================================== registration / login
# Three-factor verification. ALL must match the college record, otherwise access is denied:
#   1. USN sent by the student
#   2. Date of birth sent by the student
#   3. The WhatsApp sender's actual number (taken from Meta's webhook, not typed) == registered mobile for that USN
def _dob_candidates(text):
    d = re.sub(r"\D", "", text)
    if len(d) != 8:
        return set()
    return {d, d[6:8] + d[4:6] + d[0:4]}  # DDMMYYYY or YYYYMMDD


def _sender_matches_mobile(phone, mobile):
    digits = re.sub(r"\D", "", phone or "")
    return bool(mobile) and hmac.compare_digest(digits, config.COUNTRY_CODE + mobile)


def _registration(phone, text):
    sess = db.get_session(phone) or {"state": None, "data": {}}
    data, state = sess["data"], sess["state"]
    locked = data.get("locked_until")
    if locked:
        left = datetime.fromisoformat(locked) - datetime.now(timezone.utc)
        if left.total_seconds() > 0:
            return wa.send_text(phone, f"🔒 Too many failed attempts. Please try again in "
                                       f"{int(left.total_seconds() // 60) + 1} minutes.")
        data.pop("locked_until", None)

    m = USN_RE.search(text)
    if state == "REG_DOB" and not m:
        return _reg_dob(phone, data, text)
    if m:
        data["usn"] = m.group(0).upper()
        db.set_session(phone, "REG_DOB", data)
        return wa.send_text(phone, "Thanks! Now send your *date of birth* as DDMMYYYY (e.g. 15082005) to verify it's you.")
    if state is None:
        msg = ("Welcome to *ContXpert* 🎓 - your smart student support assistant (MCE Contineo).\n\n"
               "Let's verify you (one-time). Please send your *USN* (e.g. 4MC23CS078).")
    else:
        msg = "That doesn't look like a valid USN. Please send it like *4MC23CS078*."
    db.set_session(phone, "REG_USN", data)
    wa.send_text(phone, msg)


def _reg_dob(phone, data, text):
    usn = data.get("usn", "")
    student = db.get_student(usn) if usn else None
    dob_ok = bool(student) and student["dob"] in _dob_candidates(text)
    mobile_ok = bool(student) and _sender_matches_mobile(phone, student["mobile"])
    if not (student and dob_ok and mobile_ok):      # deliberately does not say WHICH check failed
        log.warning("login denied for ...%s", re.sub(r"\D", "", phone)[-4:])
        data["fails"] = data.get("fails", 0) + 1
        if data["fails"] >= config.MAX_REG_FAILS:
            data["fails"] = 0
            data["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=config.REG_LOCK_MINUTES)).isoformat()
            db.set_session(phone, "REG_USN", data)
            return wa.send_text(phone, f"🔒 Too many failed attempts. Login is locked for {config.REG_LOCK_MINUTES} minutes.")
        db.set_session(phone, "REG_USN", data)
        left = config.MAX_REG_FAILS - data["fails"]
        return wa.send_text(phone, f"❌ Verification failed. Your USN, date of birth and this WhatsApp number must all "
                                   f"match your college records ({left} attempts left).\nPlease send your *USN* again.")
    db.bind_user(phone, usn)    # safe to replace an older link: the sender proved they own the registered number
    db.clear_session(phone)
    wa.send_text(phone, f"✅ Verified! Welcome, *{student['name']}* ({student['department']} - Sec {student['section']}, "
                        f"Sem {student['semester']}).\nYou're logged in - no login needed next time.")
    send_menu(phone, student)


# ====================================================================== menu
def _first(student):
    return student["name"].split()[0]


def send_menu(phone, student):
    wa.send_list(phone, f"Hi {_first(student)}! 👋 What would you like to check?", "Open menu", MENU_ROWS, "ContXpert")


# ====================================================================== interactive replies
def _handle_reply(phone, user, student, rid):
    usn = user["usn"]
    if rid in MENU_INTENT:
        db.clear_session(phone)
        _dispatch(phone, student, MENU_INTENT[rid], "")
        return True
    if rid.startswith("tt:"):
        _timetable(phone, student, {"today": 0, "tomorrow": 1, "week": "week"}.get(rid[3:], 0))
        return True
    if rid.startswith("sub:"):
        _calc_subject(phone, usn, rid[4:])
        return True
    if rid.startswith("tgt:"):
        _, code, target = rid.split(":", 2)
        _calc_result(phone, usn, code, float(target))
        return True
    if rid.startswith("cert:"):
        _cert_confirm(phone, rid[5:])
        return True
    if rid.startswith("cert_pay:"):
        _cert_pay(phone, student, rid[9:])
        return True
    if rid == "cert_cancel":
        db.clear_session(phone)
        wa.send_text(phone, "Okay, cancelled." + FOOTER)
        return True
    if rid == "logout_yes":
        db.unbind_user(phone=phone)
        db.clear_session(phone)
        wa.send_text(phone, "Your number has been unlinked. Send your *USN* any time to log in again.")
        return True
    if rid == "logout_no":
        wa.send_text(phone, "Okay, nothing changed." + FOOTER)
        return True
    return False


def _continue_flow(phone, student, sess, text):
    if sess["state"] == "CALC_TARGET":
        m = re.fullmatch(r"\s*(\d{1,3}(?:\.\d+)?)\s*(?:/\s*100)?\s*", text)
        if m and 0 <= float(m.group(1)) <= 100:
            _calc_result(phone, student["usn"], sess["data"]["code"], float(m.group(1)))
            return True
    return False


# ====================================================================== intent dispatch
def _dispatch(phone, student, intent, text):
    usn = student["usn"]
    if intent not in ("thanks",):
        db.clear_session(phone)
    if intent == "greeting":
        return send_menu(phone, student)
    if intent == "menu":
        return send_menu(phone, student)
    if intent == "attendance":
        return wa.send_text(phone, _fmt_attendance(usn) + FOOTER)
    if intent == "cie":
        return wa.send_text(phone, _fmt_cie(usn) + FOOTER)
    if intent == "fees":
        return wa.send_text(phone, _fmt_fees(usn) + FOOTER)
    if intent == "timetable":
        return _timetable(phone, student, _tt_target(text))
    if intent == "notifications":
        return wa.send_text(phone, _fmt_notices(student) + FOOTER)
    if intent == "cie_calc":
        return _calc_start(phone, usn)
    if intent == "certificate":
        return _cert_menu(phone)
    if intent == "cert_status":
        return wa.send_text(phone, _fmt_cert_status(usn) + FOOTER)
    if intent == "risk":
        return wa.send_text(phone, _risk_report(usn) + FOOTER)
    if intent == "thanks":
        return wa.send_text(phone, "You're welcome! 😊 Type *menu* anytime.")
    if intent == "logout":
        return wa.send_buttons(phone, "Unlink this WhatsApp number from your USN?",
                               [("logout_yes", "Yes, unlink"), ("logout_no", "Cancel")])
    if intent == "ask":
        return wa.send_text(phone, "Sure - ask me anything about attendance rules, CIE/SEE, exams, certificates, "
                                   "library and more. Just type your question.")
    # faq / unknown -> retrieval (+ optional LLM)
    ans = rag.answer(text)
    if ans:
        return wa.send_text(phone, ans + FOOTER)
    wa.send_text(phone, "Sorry, I couldn't find that. Try one of the menu options, or contact the department office."
                 + FOOTER)


# ====================================================================== formatters
def _emoji_att(s):
    return "✅" if not s["short"] else ("🔴" if s["pct"] < config.ATTENDANCE_THRESHOLD - 5 else "⚠️")


def _fmt_attendance(usn):
    att = services.get_attendance(usn)
    if not att["subjects"]:
        return "No attendance records found yet."
    lines = [f"📊 *Attendance - {usn}*"]
    for s in att["subjects"]:
        tail = (f"attend next *{s['need']}* classes to reach {config.ATTENDANCE_THRESHOLD:g}%" if s["short"]
                else f"can miss *{s['can_miss']}* more")
        lines.append(f"{_emoji_att(s)} {s['name']}: *{s['pct']}%* ({s['attended']}/{s['held']}) - {tail}")
    lines.append(f"\n*Overall:* {att['overall']}% ({att['attended']}/{att['held']})")
    return "\n".join(lines)


def _n(x):
    return f"{x:g}"


def _fmt_cie(usn):
    subs = services.get_cie(usn)
    if not subs:
        return "No CIE marks found yet."
    lines = [f"📝 *CIE Marks - {usn}*"]
    for s in subs:
        parts = [f"{c['label']} {_n(c['marks']) if c['marks'] is not None else '-'}/{c['max']}" for c in s["components"]]
        lines.append(f"*{s['name']}*\n  " + " | ".join(parts) + f"\n  Total so far: *{_n(s['got'])}/{_n(s['done_max'])}*"
                     + (f" ({len(s['pending'])} pending)" if s["pending"] else ""))
    return "\n".join(lines)


def _fmt_fees(usn):
    f = services.get_fees(usn)
    if not f:
        return "No fee record found."
    status = "✅ All dues cleared" if f["due"] <= 0 else f"⚠️ Due: *Rs.{f['due']:,.0f}*"
    due_date = f"\nLast date: {f['due_date']}" if f["due"] > 0 and f["due_date"] else ""
    return (f"💰 *Fee Status*\nTotal: Rs.{f['total']:,.0f}\nPaid: Rs.{f['paid']:,.0f}\n{status}{due_date}")


def _fmt_notices(student):
    rows = services.get_notifications(student)
    if not rows:
        return "No new notifications."
    return "🔔 *Latest notifications*\n\n" + "\n\n".join(f"📌 *{r['title']}* ({r['date']})\n{r['body']}" for r in rows)


def _fmt_cert_status(usn):
    rows = db.list_certs(usn)
    if not rows:
        return "You have no certificate requests yet. Choose *Certificates* from the menu to apply."
    out = ["📜 *Your certificate requests*"]
    for r in rows:
        label = config.CERTIFICATES.get(r["cert_type"], (r["cert_type"],))[0]
        line = f"#{r['id']} {label} - {STATUS_LABEL.get(r['status'], r['status'])}"
        if r["status"] == "PENDING_PAYMENT" and r["payment_link"]:
            line += f"\n   Pay here: {r['payment_link']}"
        out.append(line)
    return "\n".join(out)


# ====================================================================== timetable
def _tt_target(text):
    low = text.lower()
    words = re.findall(r"[a-z]+", low)
    if "week" in low or "weekly" in low:
        return "week"
    if "tomorrow" in low or "tmrw" in words or "kal" in words:
        return 1
    today = services.now_ist().weekday()
    for i, d in enumerate(WEEKDAYS):
        if d in words or d[:3] in words:
            return (i - today) % 7
    return 0


def _timetable(phone, student, which):
    now = services.now_ist()
    if which == "week":
        out = [f"🗓️ *Weekly timetable - {student['department']} {student['section']}*"]
        for d in range(7):
            # Monday-first week, always starting from this week's Monday
            date = now + timedelta(days=d - now.weekday())
            day, rows = services.get_timetable(student, date)
            if rows:
                out.append(f"\n*{day}*\n" + "\n".join(f"{r['start']} {r['subject_name']}" for r in rows))
        return wa.send_text(phone, "\n".join(out) + FOOTER)
    date = now + timedelta(days=which)
    day, rows = services.get_timetable(student, date)
    title = "Today" if which == 0 else "Tomorrow" if which == 1 else date.strftime("%A")
    if not rows:
        body = f"🗓️ *{title} ({day})*\nNo classes scheduled 🎉"
    else:
        body = f"🗓️ *{title} ({day}, {date.strftime('%d %b')})*\n" + "\n".join(
            f"{r['start']}-{r['end']}  {r['subject_name']}" + (f" ({r['room']})" if r["room"] else "") for r in rows)
    wa.send_buttons(phone, body, [("tt:today", "Today"), ("tt:tomorrow", "Tomorrow"), ("tt:week", "Full week")])


# ====================================================================== CIE planner
def _calc_start(phone, usn):
    subs = services.get_cie(usn)
    if not subs:
        return wa.send_text(phone, "No CIE data found for you yet." + FOOTER)
    rows = [(f"sub:{s['code']}", s["name"], f"{s['code']} - CIE so far {_n(s['got'])}/{_n(s['done_max'])}") for s in subs]
    wa.send_list(phone, "🧮 *CIE planner* - which subject?", "Choose subject", rows, "Subjects")


def _calc_subject(phone, usn, code):
    subj = next((s for s in services.get_cie(usn) if s["code"] == code), None)
    if not subj:
        return wa.send_text(phone, "I couldn't find that subject." + FOOTER)
    db.set_session(phone, "CALC_TARGET", {"code": code})
    wa.send_buttons(phone, f"*{subj['name']}* - what total (out of 100) do you want?\n"
                           f"Tap a target or type any number, e.g. 85.",
                    [(f"tgt:{code}:{config.PASS_TOTAL}", f"Pass ({config.PASS_TOTAL})"),
                     (f"tgt:{code}:60", "First class (60)"), (f"tgt:{code}:75", "Distinction (75)")])


def _calc_result(phone, usn, code, target):
    db.clear_session(phone)
    res = services.cie_calc(usn, code, target)
    if not res:
        return wa.send_text(phone, "I couldn't find that subject." + FOOTER)
    s = res["subject"]
    done = " + ".join(f"{c['label']} {_n(c['marks'])}/{c['max']}" for c in s["components"] if c["marks"] is not None) or "none yet"
    pend = ", ".join(f"{p['label']} ({p['max']})" for p in s["pending"]) or "none"
    lines = [f"🧮 *{s['name']}* - target *{_n(res['target'])}/100*",
             f"CIE done: {done} = *{_n(s['got'])}/{_n(s['done_max'])}*", f"Pending: {pend}", "",
             "*Marks needed in SEE (out of 100):*"]
    for sc in res["scenarios"]:
        need = f"*{sc['need']}*" if sc["possible"] else "not possible even with full marks ❌"
        lines.append(f"• {sc['label']}: CIE {_n(sc['cie'])}/{config.CIE_MAX} -> {need}")
    lines.append(f"\nNote: you need at least {config.MIN_SEE_RAW}/100 in SEE and {config.PASS_TOTAL}/100 overall to pass.")
    wa.send_text(phone, "\n".join(lines) + FOOTER)


# ====================================================================== certificates
def _cert_menu(phone):
    rows = [(f"cert:{k}", v[0], f"Rs.{v[1]} - {v[2]}") for k, v in config.CERTIFICATES.items()]
    wa.send_list(phone, "📜 Which certificate do you need?", "Choose", rows, "Certificates")


def _cert_confirm(phone, key):
    if key not in config.CERTIFICATES:
        return wa.send_text(phone, "Unknown certificate type." + FOOTER)
    label, fee, tat = config.CERTIFICATES[key]
    wa.send_buttons(phone, f"*{label}*\nFee: Rs.{fee}\nTurnaround: {tat}\n\nProceed to payment?",
                    [(f"cert_pay:{key}", f"Pay Rs.{fee}"), ("cert_cancel", "Cancel")])


def _cert_pay(phone, student, key):
    if key not in config.CERTIFICATES:
        return wa.send_text(phone, "Unknown certificate type." + FOOTER)
    label, fee, _ = config.CERTIFICATES[key]
    usn = student["usn"]
    for r in db.list_certs(usn, 20):          # don't create duplicates - reuse an unpaid request
        if r["cert_type"] == key and r["status"] == "PENDING_PAYMENT" and r["payment_link"]:
            return wa.send_text(phone, f"You already have an unpaid request #{r['id']} for *{label}*.\n"
                                       f"Pay here: {r['payment_link']}")
    req_id = db.create_cert(usn, phone, key, fee)
    try:
        link, ref = payments.create_payment(req_id, fee, student, phone, f"{label} - {usn}")
    except Exception:
        log.exception("payment link creation failed")
        db.set_cert_status(req_id, "CANCELLED")
        return wa.send_text(phone, "Sorry, I couldn't create the payment link right now. Please try again later.")
    db.set_cert_link(req_id, link, ref)
    wa.send_text(phone, f"🧾 Request *#{req_id}* - {label} (Rs.{fee})\nPay securely here:\n{link}\n\n"
                        f"I'll confirm here once the payment is received and again when the certificate is ready.")


# ====================================================================== AI risk report
def _risk_report(usn):
    feat = services.student_features(usn)
    prob, level = risk_model.predict(feat)
    att = services.get_attendance(usn)
    shorts = [s for s in att["subjects"] if s["short"]]
    reasons, tips = [], []
    for s in shorts:
        reasons.append(f"{s['name']} attendance is {s['pct']}%")
        tips.append(f"Attend the next {s['need']} {s['name']} classes without a break.")
    if feat["avg_cie_pct"] < 0.5:
        reasons.append(f"CIE average is only {round(feat['avg_cie_pct'] * 100)}%")
        tips.append("Prioritise subjects with low CIE and aim for good scores in the remaining IA/assignment.")
    if feat["fee_due_ratio"] > 0:
        reasons.append("fee dues are pending")
        tips.append("Clear pending fee dues before the last date.")
    if not reasons:
        reasons, tips = ["attendance and CIE are on track"], ["Keep it up - maintain your attendance and revise regularly."]
    if llm.enabled():
        summary = (f"Attendance by subject: " + ", ".join(f"{s['name']} {s['pct']}%" for s in att["subjects"]) +
                   f". Average CIE: {round(feat['avg_cie_pct'] * 100)}%. Fee due ratio: {round(feat['fee_due_ratio'] * 100)}%. "
                   f"Risk level: {level}.")
        text = llm.complete("You are a friendly academic mentor for an engineering student. Give exactly 3 short, "
                            "specific, actionable tips (one line each, starting with '-'). No greeting.", summary, 250)
        if text:
            tips = [t.strip() for t in text.splitlines() if t.strip()][:3]
    icon = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}[level]
    return (f"🤖 *AI Academic Risk Report*\nRisk level: {icon} *{level}* (model score {round(prob * 100)}%)\n\n"
            f"*Key factors:*\n" + "\n".join(f"• {r}" for r in reasons) +
            "\n\n*Suggestions:*\n" + "\n".join(t if t.startswith(("-", "•")) else f"• {t}" for t in tips) +
            "\n\n_Predicted by a machine-learning model; use it as guidance, not a final verdict._")