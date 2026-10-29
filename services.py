"""Pure academic logic: attendance maths, CIE aggregation, fee status, timetable, notices."""
import math
from datetime import datetime, timedelta, timezone

import config
import db

IST = timezone(timedelta(hours=5, minutes=30))
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def now_ist():
    return datetime.now(IST)


# ------------------------------------------------------------------ attendance
def get_attendance(usn):
    t = config.ATTENDANCE_THRESHOLD / 100
    subjects, held_all, att_all = [], 0, 0
    for r in db.query("SELECT * FROM attendance WHERE usn=? ORDER BY subject_code", (usn,)):
        h, a = r["classes_held"], r["classes_attended"]
        pct = round(100 * a / h, 1) if h else 0.0
        short = bool(h) and a / h < t
        need = max(0, math.ceil(round((t * h - a) / (1 - t), 6))) if short else 0   # classes to attend continuously
        can_miss = max(0, math.floor(round(a / t - h, 6))) if (h and not short) else 0
        subjects.append({"code": r["subject_code"], "name": r["subject_name"], "held": h, "attended": a,
                         "pct": pct, "short": short, "need": need, "can_miss": can_miss})
        held_all += h
        att_all += a
    overall = round(100 * att_all / held_all, 1) if held_all else 0.0
    return {"subjects": subjects, "overall": overall, "held": held_all, "attended": att_all}


# ------------------------------------------------------------------ CIE
def get_cie(usn):
    subjects = {}
    for r in db.query("SELECT * FROM cie WHERE usn=? ORDER BY subject_code", (usn,)):
        s = subjects.setdefault(r["subject_code"], {"code": r["subject_code"], "name": r["subject_name"], "marks": {}})
        s["marks"][r["component"]] = r["marks"]
    out = []
    for s in subjects.values():
        got = done_max = pend_max = 0.0
        comps, pending = [], []
        for key, label, mx in config.CIE_COMPONENTS:
            m = s["marks"].get(key)
            comps.append({"key": key, "label": label, "max": mx, "marks": m})
            if m is None:
                pending.append({"key": key, "label": label, "max": mx})
                pend_max += mx
            else:
                got += m
                done_max += mx
        out.append({"code": s["code"], "name": s["name"], "components": comps, "pending": pending,
                    "got": got, "done_max": done_max, "pending_max": pend_max,
                    "pct": (got / done_max) if done_max else None})
    return out


def cie_calc(usn, code, target):
    """Marks needed in SEE for a target total (out of 100) under 3 scenarios for pending CIE components."""
    subj = next((s for s in get_cie(usn) if s["code"].lower() == code.lower()), None)
    if not subj:
        return None
    target = max(0, min(config.TOTAL_MAX, float(target)))
    if subj["pending_max"] > 0:
        exp_pct = subj["pct"] if subj["pct"] is not None else 0.6
        cases = [("Worst case (pending CIE = 0)", 0.0),
                 (f"Expected (pending CIE at your {round(exp_pct * 100)}% average)", exp_pct * subj["pending_max"]),
                 ("Best case (full marks in pending CIE)", subj["pending_max"])]
    else:
        cases = [("Final CIE is complete", 0.0)]
    scenarios = []
    for label, extra in cases:
        cie_total = subj["got"] + extra
        raw = (target - cie_total) / config.SEE_WEIGHT
        need = max(config.MIN_SEE_RAW, math.ceil(round(raw, 6)))
        scenarios.append({"label": label, "cie": round(cie_total, 1), "need": need,
                          "possible": need <= config.SEE_MAX})
    return {"subject": subj, "target": target, "scenarios": scenarios}


# ------------------------------------------------------------------ fees
def get_fees(usn):
    r = db.query("SELECT * FROM fees WHERE usn=?", (usn,), one=True)
    if not r:
        return None
    due = max(0.0, r["total_fee"] - r["paid"])
    return {"total": r["total_fee"], "paid": r["paid"], "due": due, "due_date": r["due_date"],
            "ratio": (due / r["total_fee"]) if r["total_fee"] else 0.0}


# ------------------------------------------------------------------ timetable / notices
def get_timetable(student, date):
    day = DAYS[date.weekday()]
    rows = db.query("SELECT * FROM timetable WHERE department=? AND section=? AND semester=? AND day=? ORDER BY period",
                    (student["department"], student["section"], student["semester"], day))
    return day, [dict(r) for r in rows]


def get_notifications(student, limit=5):
    rows = db.query("SELECT * FROM notifications WHERE (department='ALL' OR department=?) "
                    "AND (section='ALL' OR section=?) ORDER BY date DESC, id DESC LIMIT ?",
                    (student["department"], student["section"], limit))
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ features for ML
def student_features(usn):
    att = get_attendance(usn)
    pcts = [s["pct"] for s in att["subjects"]] or [75.0]
    cie = get_cie(usn)
    got = sum(s["got"] for s in cie)
    mx = sum(s["done_max"] for s in cie)
    fees = get_fees(usn)
    return {
        "avg_att": sum(pcts) / len(pcts),
        "min_att": min(pcts),
        "n_short": sum(1 for s in att["subjects"] if s["short"]),
        "avg_cie_pct": (got / mx) if mx else 0.6,
        "fee_due_ratio": fees["ratio"] if fees else 0.0,
    }
