"""SQLite storage + CSV importer. Academic tables are re-imported from ./data/*.csv on every start,
so replacing the CSV files and restarting is all you need to do to use real data."""
import contextlib
import csv
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS students(usn TEXT PRIMARY KEY, name TEXT, department TEXT, section TEXT,
    semester INTEGER, dob TEXT, mobile TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS attendance(usn TEXT, subject_code TEXT, subject_name TEXT,
    classes_held INTEGER, classes_attended INTEGER, PRIMARY KEY(usn, subject_code));
CREATE TABLE IF NOT EXISTS cie(usn TEXT, subject_code TEXT, subject_name TEXT, component TEXT, marks REAL,
    PRIMARY KEY(usn, subject_code, component));
CREATE TABLE IF NOT EXISTS fees(usn TEXT PRIMARY KEY, total_fee REAL, paid REAL, due_date TEXT);
CREATE TABLE IF NOT EXISTS timetable(department TEXT, section TEXT, semester INTEGER, day TEXT, period INTEGER,
    start TEXT, end TEXT, subject_code TEXT, subject_name TEXT, room TEXT, faculty TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, department TEXT,
    section TEXT, title TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS users(phone TEXT PRIMARY KEY, usn TEXT UNIQUE, registered_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(phone TEXT PRIMARY KEY, state TEXT, data TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS cert_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, usn TEXT, phone TEXT,
    cert_type TEXT, amount INTEGER, status TEXT, payment_ref TEXT, payment_link TEXT,
    created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS processed_messages(id TEXT PRIMARY KEY, ts TEXT);
CREATE TABLE IF NOT EXISTS alert_log(usn TEXT, sent_at TEXT);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def last10(value):
    """Last 10 digits of a phone number (so +91 98765 43210, 919876543210 and 9876543210 all compare equal)."""
    return re.sub(r"\D", "", value or "")[-10:]


def _connect():
    c = sqlite3.connect(config.DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def query(sql, params=(), one=False):
    with contextlib.closing(_connect()) as c:
        rows = c.execute(sql, params).fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=()):
    """Returns (lastrowid, rowcount)."""
    with contextlib.closing(_connect()) as c:
        with c:
            cur = c.execute(sql, params)
            return cur.lastrowid, cur.rowcount


# ------------------------------------------------------------------ CSV import
def _read(name, required):
    path = os.path.join(config.DATA_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing {path}. Run:  python seed_mock_data.py")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in required if c not in headers]
        if missing:
            raise ValueError(f"{name}: missing column(s) {missing}. Found: {headers}")
        return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k} for r in reader]


def _num(v, cast, where):
    if v == "":
        return None
    try:
        return cast(float(v)) if cast is int else cast(v)
    except ValueError:
        raise ValueError(f"{where}: '{v}' is not a number")


def load_csv_data():
    students = _read("students.csv", ["usn", "name", "department", "section", "semester", "dob", "mobile"])
    attendance = _read("attendance.csv", ["usn", "subject_code", "subject_name", "classes_held", "classes_attended"])
    cie = _read("cie.csv", ["usn", "subject_code", "subject_name"] + [c[0] for c in config.CIE_COMPONENTS])
    fees = _read("fees.csv", ["usn", "total_fee", "paid"])
    tt = _read("timetable.csv", ["department", "section", "semester", "day", "period", "start", "end",
                                 "subject_code", "subject_name"])
    notes = _read("notifications.csv", ["date", "department", "section", "title", "body"])

    with contextlib.closing(_connect()) as c:
        with c:
            for t in ("students", "attendance", "cie", "fees", "timetable", "notifications"):
                c.execute(f"DELETE FROM {t}")
            c.executemany("INSERT OR REPLACE INTO students VALUES(?,?,?,?,?,?,?,?)", [
                (r["usn"].upper(), r["name"], r["department"].upper(), r["section"].upper(),
                 _num(r["semester"], int, "students.semester"), "".join(ch for ch in r["dob"] if ch.isdigit()),
                 last10(r["mobile"]), r.get("email", "")) for r in students])
            c.executemany("INSERT OR REPLACE INTO attendance VALUES(?,?,?,?,?)", [
                (r["usn"].upper(), r["subject_code"], r["subject_name"],
                 _num(r["classes_held"], int, "attendance.classes_held") or 0,
                 _num(r["classes_attended"], int, "attendance.classes_attended") or 0) for r in attendance])
            rows = []
            for r in cie:
                for comp, _label, _mx in config.CIE_COMPONENTS:
                    rows.append((r["usn"].upper(), r["subject_code"], r["subject_name"], comp,
                                 _num(r[comp], float, f"cie.{comp}")))
            c.executemany("INSERT OR REPLACE INTO cie VALUES(?,?,?,?,?)", rows)
            c.executemany("INSERT OR REPLACE INTO fees VALUES(?,?,?,?)", [
                (r["usn"].upper(), _num(r["total_fee"], float, "fees.total_fee") or 0,
                 _num(r["paid"], float, "fees.paid") or 0, r.get("due_date", "")) for r in fees])
            c.executemany("INSERT INTO timetable VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
                (r["department"].upper(), r["section"].upper(), _num(r["semester"], int, "timetable.semester"),
                 r["day"][:3].title(), _num(r["period"], int, "timetable.period"), r["start"], r["end"],
                 r["subject_code"], r["subject_name"], r.get("room", ""), r.get("faculty", "")) for r in tt])
            c.executemany("INSERT INTO notifications(date,department,section,title,body) VALUES(?,?,?,?,?)", [
                (r["date"], r["department"].upper() or "ALL", r["section"].upper() or "ALL", r["title"], r["body"])
                for r in notes])


def init_db():
    with contextlib.closing(_connect()) as c:
        with c:
            c.execute("DROP TABLE IF EXISTS students")   # always re-imported from CSV (lets the schema change)
            c.executescript(SCHEMA)
    load_csv_data()


# ------------------------------------------------------------------ students / users
def get_student(usn):
    r = query("SELECT * FROM students WHERE usn=?", (usn.upper(),), one=True)
    return dict(r) if r else None


def get_user(phone):
    r = query("SELECT * FROM users WHERE phone=?", (phone,), one=True)
    return dict(r) if r else None


def get_user_by_usn(usn):
    r = query("SELECT * FROM users WHERE usn=?", (usn.upper(),), one=True)
    return dict(r) if r else None


def bind_user(phone, usn):
    execute("INSERT OR REPLACE INTO users(phone, usn, registered_at) VALUES(?,?,?)", (phone, usn.upper(), now_iso()))


def unbind_user(phone=None, usn=None):
    if phone:
        return execute("DELETE FROM users WHERE phone=?", (phone,))[1]
    return execute("DELETE FROM users WHERE usn=?", (usn.upper(),))[1]


def all_users():
    return [dict(r) for r in query("SELECT * FROM users")]


# ------------------------------------------------------------------ sessions
def get_session(phone):
    r = query("SELECT * FROM sessions WHERE phone=?", (phone,), one=True)
    if not r or not r["state"]:
        return None
    return {"state": r["state"], "data": json.loads(r["data"] or "{}")}


def set_session(phone, state, data=None):
    execute("INSERT OR REPLACE INTO sessions(phone,state,data,updated_at) VALUES(?,?,?,?)",
            (phone, state, json.dumps(data or {}), now_iso()))


def clear_session(phone):
    execute("DELETE FROM sessions WHERE phone=?", (phone,))


# ------------------------------------------------------------------ certificates
def create_cert(usn, phone, cert_type, amount):
    now = now_iso()
    rid, _ = execute("INSERT INTO cert_requests(usn,phone,cert_type,amount,status,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,?)", (usn, phone, cert_type, amount, "PENDING_PAYMENT", now, now))
    return rid


def get_cert(req_id):
    r = query("SELECT * FROM cert_requests WHERE id=?", (req_id,), one=True)
    return dict(r) if r else None


def set_cert_link(req_id, link, ref):
    execute("UPDATE cert_requests SET payment_link=?, payment_ref=?, updated_at=? WHERE id=?",
            (link, ref, now_iso(), req_id))


def set_cert_status(req_id, status, expected=None, payment_ref=None):
    """Atomic status change. If `expected` is given, only update when current status matches."""
    sql, params = "UPDATE cert_requests SET status=?, updated_at=?", [status, now_iso()]
    if payment_ref:
        sql += ", payment_ref=?"
        params.append(payment_ref)
    sql += " WHERE id=?"
    params.append(req_id)
    if expected:
        sql += " AND status=?"
        params.append(expected)
    return execute(sql, tuple(params))[1]


def list_certs(usn, limit=5):
    return [dict(r) for r in query("SELECT * FROM cert_requests WHERE usn=? ORDER BY id DESC LIMIT ?", (usn, limit))]


def list_all_certs(status=None):
    if status:
        rows = query("SELECT * FROM cert_requests WHERE status=? ORDER BY id DESC", (status,))
    else:
        rows = query("SELECT * FROM cert_requests ORDER BY id DESC LIMIT 200")
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ misc
def mark_processed(msg_id):
    """True if this WhatsApp message id is new (Meta retries webhooks, so we de-duplicate)."""
    if not msg_id:
        return True
    return execute("INSERT OR IGNORE INTO processed_messages(id, ts) VALUES(?,?)", (msg_id, now_iso()))[1] == 1


def last_alert(usn):
    r = query("SELECT MAX(sent_at) AS t FROM alert_log WHERE usn=?", (usn,), one=True)
    return r["t"] if r and r["t"] else None


def log_alert(usn):
    execute("INSERT INTO alert_log(usn, sent_at) VALUES(?,?)", (usn, now_iso()))