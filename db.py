"""PostgreSQL storage (psycopg2).

* Tables are created automatically on start (CREATE TABLE IF NOT EXISTS).
* The CSV files in ./data are only a ONE-TIME seed: they are imported when the `students` table is empty.
  (Set CSV_SYNC=1 to force a full re-import from ./data on every start - the old behaviour.)
* After that, PostgreSQL is the source of truth. Update data from the admin console (/console -> Data),
  which can import / export the same CSV formats.
* Every public function keeps the same name and return shape as the previous SQLite version, and SQL written with
  `?` placeholders still works (they are translated to psycopg2's `%s`), so bot.py / services.py / alerts.py /
  payments.py need no changes.
"""
import contextlib
import csv
import io
import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2 import extras, pool

import config

log = logging.getLogger("db")
_students_csv_lock = threading.Lock()
_students_csv_mtime_ns = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS students(usn TEXT PRIMARY KEY, name TEXT, department TEXT, section TEXT,
    semester INTEGER, dob TEXT, email TEXT);
CREATE TABLE IF NOT EXISTS attendance(usn TEXT, subject_code TEXT, subject_name TEXT,
    classes_held INTEGER, classes_attended INTEGER, PRIMARY KEY(usn, subject_code));
CREATE TABLE IF NOT EXISTS cie(usn TEXT, subject_code TEXT, subject_name TEXT, component TEXT,
    marks DOUBLE PRECISION, PRIMARY KEY(usn, subject_code, component));
CREATE TABLE IF NOT EXISTS fees(usn TEXT PRIMARY KEY, total_fee DOUBLE PRECISION, paid DOUBLE PRECISION, due_date TEXT);
CREATE TABLE IF NOT EXISTS timetable(department TEXT, section TEXT, semester INTEGER, day TEXT, period INTEGER,
    start TEXT, "end" TEXT, subject_code TEXT, subject_name TEXT, room TEXT, faculty TEXT);
CREATE TABLE IF NOT EXISTS notifications(id SERIAL PRIMARY KEY, date TEXT, department TEXT,
    section TEXT, title TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS users(phone TEXT PRIMARY KEY, usn TEXT UNIQUE, registered_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(phone TEXT PRIMARY KEY, state TEXT, data TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS cert_requests(id SERIAL PRIMARY KEY, usn TEXT, phone TEXT,
    cert_type TEXT, amount INTEGER, status TEXT, payment_ref TEXT, payment_link TEXT,
    created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS processed_messages(id TEXT PRIMARY KEY, ts TEXT);
CREATE TABLE IF NOT EXISTS alert_log(usn TEXT, sent_at TEXT);
CREATE INDEX IF NOT EXISTS idx_attendance_usn ON attendance(usn);
CREATE INDEX IF NOT EXISTS idx_cie_usn ON cie(usn);
CREATE INDEX IF NOT EXISTS idx_timetable_lookup ON timetable(department, section, semester, day);
CREATE INDEX IF NOT EXISTS idx_notifications_date ON notifications(date);
CREATE INDEX IF NOT EXISTS idx_cert_usn ON cert_requests(usn);
CREATE INDEX IF NOT EXISTS idx_cert_status ON cert_requests(status);
CREATE INDEX IF NOT EXISTS idx_alert_usn ON alert_log(usn);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ connection pool
_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if not config.DATABASE_URL:
                    raise RuntimeError("DATABASE_URL is not set. Put your PostgreSQL connection string in .env "
                                       "(local) or in the Render environment variables.")
                _pool = pool.ThreadedConnectionPool(
                    1, config.DB_POOL_MAX, dsn=config.DATABASE_URL, cursor_factory=extras.RealDictCursor,
                    connect_timeout=10, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5)
    return _pool


@contextlib.contextmanager
def _conn():
    """Borrow a connection; commit on success, roll back on error. Broken connections are discarded."""
    p = _get_pool()
    c = p.getconn()
    broken = False
    try:
        yield c
        c.commit()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        broken = True
        raise
    except Exception:
        with contextlib.suppress(Exception):
            c.rollback()
        raise
    finally:
        p.putconn(c, close=broken or bool(c.closed))


def _run(fn):
    """Run fn(connection); retry once if the server dropped an idle connection (common on hosted DBs)."""
    try:
        with _conn() as c:
            return fn(c)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        log.warning("database connection lost - retrying once")
        with _conn() as c:
            return fn(c)


def _adapt(sql):
    """SQLite-style `?` placeholders -> psycopg2 `%s` (literal % is escaped)."""
    return sql.replace("%", "%%").replace("?", "%s")


def query(sql, params=(), one=False):
    def go(c):
        with c.cursor() as cur:
            cur.execute(_adapt(sql), tuple(params))
            return cur.fetchall()
    rows = _run(go)
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=()):
    """Returns (id, rowcount). `id` is the first column returned when the statement has a RETURNING clause."""
    def go(c):
        with c.cursor() as cur:
            cur.execute(_adapt(sql), tuple(params))
            rid = None
            if cur.description is not None:
                row = cur.fetchone()
                rid = next(iter(row.values())) if row else None
            return rid, cur.rowcount
    return _run(go)


def ping():
    """True if the database answers (used by the admin console)."""
    try:
        return query("SELECT 1 AS ok", one=True)["ok"] == 1
    except Exception:
        log.exception("database ping failed")
        return False


# ------------------------------------------------------------------ CSV datasets (import / export)
def _cie_cols():
    return [c[0] for c in config.CIE_COMPONENTS]


# dataset -> (csv file, required columns, all columns in export order)
DATASETS = {
    "students": ("students.csv", ["usn", "name", "department", "section", "semester", "dob"],
                 ["usn", "name", "department", "section", "semester", "dob", "email"]),
    "attendance": ("attendance.csv", ["usn", "subject_code", "subject_name", "classes_held", "classes_attended"],
                   ["usn", "subject_code", "subject_name", "classes_held", "classes_attended"]),
    "cie": ("cie.csv", ["usn", "subject_code", "subject_name"] + _cie_cols(),
            ["usn", "subject_code", "subject_name"] + _cie_cols()),
    "fees": ("fees.csv", ["usn", "total_fee", "paid"], ["usn", "total_fee", "paid", "due_date"]),
    "timetable": ("timetable.csv", ["department", "section", "semester", "day", "period", "start", "end",
                                    "subject_code", "subject_name"],
                  ["department", "section", "semester", "day", "period", "start", "end", "subject_code",
                   "subject_name", "room", "faculty"]),
    "notifications": ("notifications.csv", ["date", "department", "section", "title", "body"],
                      ["date", "department", "section", "title", "body"]),
}
LOAD_ORDER = ["students", "attendance", "cie", "fees", "timetable", "notifications"]


def _num(v, cast, where):
    if v is None or v == "":
        return None
    try:
        return cast(float(v)) if cast is int else cast(v)
    except ValueError:
        raise ValueError(f"{where}: '{v}' is not a number")


def parse_csv(name, text):
    """Parse + validate CSV text for dataset `name`. Returns a list of cleaned dict rows."""
    _file, required, _cols = DATASETS[name]
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in required if c not in headers]
    if missing:
        raise ValueError(f"{name}.csv: missing column(s) {missing}. Found: {headers}")
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k} for r in reader]


def _read(name):
    path = os.path.join(config.DATA_DIR, DATASETS[name][0])
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing {path}. Run:  python seed_mock_data.py")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return parse_csv(name, f.read())


def _tuples(name, rows):
    """Convert parsed CSV rows to the tuples inserted into each table."""
    if name == "students":
        return [(r["usn"].upper(), r["name"], r["department"].upper(), r["section"].upper(),
                 _num(r["semester"], int, "students.semester"), "".join(ch for ch in r["dob"] if ch.isdigit()),
                 r.get("email", "")) for r in rows]
    if name == "attendance":
        return [(r["usn"].upper(), r["subject_code"], r["subject_name"],
                 _num(r["classes_held"], int, "attendance.classes_held") or 0,
                 _num(r["classes_attended"], int, "attendance.classes_attended") or 0) for r in rows]
    if name == "cie":
        return [(r["usn"].upper(), r["subject_code"], r["subject_name"], comp, _num(r[comp], float, f"cie.{comp}"))
                for r in rows for comp, _label, _mx in config.CIE_COMPONENTS]
    if name == "fees":
        return [(r["usn"].upper(), _num(r["total_fee"], float, "fees.total_fee") or 0,
                 _num(r["paid"], float, "fees.paid") or 0, r.get("due_date", "")) for r in rows]
    if name == "timetable":
        return [(r["department"].upper(), r["section"].upper(), _num(r["semester"], int, "timetable.semester"),
                 r["day"][:3].title(), _num(r["period"], int, "timetable.period"), r["start"], r["end"],
                 r["subject_code"], r["subject_name"], r.get("room", ""), r.get("faculty", "")) for r in rows]
    if name == "notifications":
        return [(r["date"], r["department"].upper() or "ALL", r["section"].upper() or "ALL", r["title"], r["body"])
                for r in rows]
    raise KeyError(name)


_UPSERT = {
    "students": "INSERT INTO students(usn,name,department,section,semester,dob,email) VALUES(%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(usn) DO UPDATE SET name=EXCLUDED.name, department=EXCLUDED.department, "
                "section=EXCLUDED.section, semester=EXCLUDED.semester, dob=EXCLUDED.dob, email=EXCLUDED.email",
    "attendance": "INSERT INTO attendance(usn,subject_code,subject_name,classes_held,classes_attended) "
                  "VALUES(%s,%s,%s,%s,%s) ON CONFLICT(usn,subject_code) DO UPDATE SET "
                  "subject_name=EXCLUDED.subject_name, classes_held=EXCLUDED.classes_held, "
                  "classes_attended=EXCLUDED.classes_attended",
    "cie": "INSERT INTO cie(usn,subject_code,subject_name,component,marks) VALUES(%s,%s,%s,%s,%s) "
           "ON CONFLICT(usn,subject_code,component) DO UPDATE SET subject_name=EXCLUDED.subject_name, "
           "marks=EXCLUDED.marks",
    "fees": "INSERT INTO fees(usn,total_fee,paid,due_date) VALUES(%s,%s,%s,%s) ON CONFLICT(usn) DO UPDATE SET "
            "total_fee=EXCLUDED.total_fee, paid=EXCLUDED.paid, due_date=EXCLUDED.due_date",
    "timetable": 'INSERT INTO timetable(department,section,semester,day,period,start,"end",subject_code,'
                 "subject_name,room,faculty) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    "notifications": "INSERT INTO notifications(date,department,section,title,body) VALUES(%s,%s,%s,%s,%s)",
}


def _write(cur, name, data, replace):
    if replace:
        cur.execute(f"DELETE FROM {name}")
    extras.execute_batch(cur, _UPSERT[name], data, page_size=500)


def import_rows(name, rows, replace=True):
    """Write parsed CSV rows into the database in ONE transaction.
    replace=True  -> wipe the table first (full replacement).
    replace=False -> merge: update rows with the same key, add new ones (timetable / notices are appended).
    Returns the number of CSV rows processed."""
    data = _tuples(name, rows)

    def go(c):
        with c.cursor() as cur:
            _write(cur, name, data, replace)
        return len(rows)
    return _run(go)


def _load_all_csv(cur):
    parsed = {n: _tuples(n, _read(n)) for n in LOAD_ORDER}       # validate everything before touching the tables
    for n in LOAD_ORDER:
        _write(cur, n, parsed[n], replace=True)


def load_csv_data():
    """Full re-import of every CSV in ./data (replaces the data tables) - all or nothing."""
    def go(c):
        with c.cursor() as cur:
            _load_all_csv(cur)
    _run(go)


def export_csv(name):
    """Current table contents as CSV text, in the same format that import accepts."""
    cols = DATASETS[name][2]
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(cols)
    if name == "cie":
        comps = _cie_cols()
        grid = {}
        for r in query("SELECT * FROM cie ORDER BY usn, subject_code"):
            g = grid.setdefault((r["usn"], r["subject_code"]), {"name": r["subject_name"]})
            g[r["component"]] = r["marks"]
        for (usn, code), g in grid.items():
            w.writerow([usn, code, g["name"]] + ["" if g.get(c) is None else f"{g[c]:g}" for c in comps])
    else:
        order = {"students": "usn", "attendance": "usn, subject_code", "fees": "usn",
                 "timetable": "department, section, semester, day, period", "notifications": "date DESC, id DESC"}[name]
        select = ", ".join('"end"' if c == "end" else c for c in cols)
        for r in query(f"SELECT {select} FROM {name} ORDER BY {order}"):
            w.writerow(["" if r[c] is None else r[c] for c in cols])
    return out.getvalue()


# ------------------------------------------------------------------ startup
def init_db():
    def go(c):
        with c.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(727274)")     # several gunicorn workers may start together
            cur.execute(SCHEMA)
            cur.execute("DELETE FROM processed_messages WHERE ts < %s",
                        ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds"),))
            cur.execute("SELECT COUNT(*) AS n FROM students")
            if config.CSV_SYNC or (config.AUTO_SEED_CSV and cur.fetchone()["n"] == 0):
                log.info("importing CSV files from %s into PostgreSQL", config.DATA_DIR)
                _load_all_csv(cur)                                   # same transaction -> other workers wait
    _run(go)


# ------------------------------------------------------------------ students / users
def _sync_students_csv_if_changed():
    """Refresh student records from data/students.csv when the local file changes.

    PostgreSQL remains the runtime store, but a changed development CSV is detected
    automatically. Rows are UPSERTed (not wiped), so unrelated/admin-managed records
    and WhatsApp registrations are preserved.
    """
    global _students_csv_mtime_ns
    path = os.path.join(config.DATA_DIR, DATASETS["students"][0])
    try:
        mtime_ns = os.stat(path).st_mtime_ns
    except FileNotFoundError:
        return
    if _students_csv_mtime_ns == mtime_ns:
        return
    with _students_csv_lock:
        if _students_csv_mtime_ns == mtime_ns:
            return
        try:
            rows = _read("students")
            if rows:
                import_rows("students", rows, replace=False)
            _students_csv_mtime_ns = mtime_ns
            log.info("refreshed %d student row(s) from changed CSV %s", len(rows), path)
        except Exception:
            # Do not mark the file as synced: a corrected CSV can be retried next lookup.
            log.exception("Could not refresh students.csv; keeping existing database records")


def get_student(usn):
    _sync_students_csv_if_changed()
    normalized_usn = re.sub(r"\s+", "", str(usn or "")).upper()
    r = query("SELECT * FROM students WHERE usn=?", (normalized_usn,), one=True)
    return dict(r) if r else None


def get_user(phone):
    r = query("SELECT * FROM users WHERE phone=?", (phone,), one=True)
    return dict(r) if r else None


def get_user_by_usn(usn):
    r = query("SELECT * FROM users WHERE usn=?", (usn.upper(),), one=True)
    return dict(r) if r else None


def bind_user(phone, usn):
    usn = usn.upper()

    def go(c):
        with c.cursor() as cur:
            cur.execute("DELETE FROM users WHERE usn=%s AND phone<>%s", (usn, phone))   # same as SQLite REPLACE
            cur.execute("INSERT INTO users(phone, usn, registered_at) VALUES(%s,%s,%s) "
                        "ON CONFLICT(phone) DO UPDATE SET usn=EXCLUDED.usn, registered_at=EXCLUDED.registered_at",
                        (phone, usn, now_iso()))
    _run(go)


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
    execute("INSERT INTO sessions(phone,state,data,updated_at) VALUES(?,?,?,?) ON CONFLICT(phone) DO UPDATE SET "
            "state=EXCLUDED.state, data=EXCLUDED.data, updated_at=EXCLUDED.updated_at",
            (phone, state, json.dumps(data or {}), now_iso()))


def clear_session(phone):
    execute("DELETE FROM sessions WHERE phone=?", (phone,))


# ------------------------------------------------------------------ certificates
def create_cert(usn, phone, cert_type, amount):
    now = now_iso()
    rid, _ = execute("INSERT INTO cert_requests(usn,phone,cert_type,amount,status,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,?) RETURNING id", (usn, phone, cert_type, amount, "PENDING_PAYMENT", now, now))
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
    return execute("INSERT INTO processed_messages(id, ts) VALUES(?,?) ON CONFLICT(id) DO NOTHING",
                   (msg_id, now_iso()))[1] == 1


def last_alert(usn):
    r = query("SELECT MAX(sent_at) AS t FROM alert_log WHERE usn=?", (usn,), one=True)
    return r["t"] if r and r["t"] else None


def log_alert(usn):
    execute("INSERT INTO alert_log(usn, sent_at) VALUES(?,?)", (usn, now_iso()))
