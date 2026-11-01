"""Read/write queries used only by the admin console."""
import config
import db


def _one(sql, params=()):
    r = db.query(sql, params, one=True)
    return next(iter(r.values())) if r else 0


# ------------------------------------------------------------------ dashboard
def dashboard_stats():
    thr = config.ATTENDANCE_THRESHOLD
    return {
        "students": _one("SELECT COUNT(*) FROM students"),
        "linked": _one("SELECT COUNT(*) FROM users"),
        "to_process": _one("SELECT COUNT(*) FROM cert_requests WHERE status='PROCESSING'"),
        "awaiting_payment": _one("SELECT COUNT(*) FROM cert_requests WHERE status='PENDING_PAYMENT'"),
        "low_attendance": _one("SELECT COUNT(DISTINCT usn) FROM attendance WHERE classes_held>0 "
                               "AND 100.0*classes_attended/classes_held < ?", (thr,)),
        "fee_due": _one("SELECT COUNT(*) FROM fees WHERE total_fee-paid>0"),
        "fee_due_amount": _one("SELECT COALESCE(SUM(total_fee-paid),0) FROM fees WHERE total_fee-paid>0"),
    }


def recent_certs(limit=6):
    return db.query("SELECT c.*, s.name FROM cert_requests c LEFT JOIN students s ON s.usn=c.usn "
                    "ORDER BY c.id DESC LIMIT ?", (limit,))


# ------------------------------------------------------------------ certificates
CERT_STATUSES = ["PENDING_PAYMENT", "PROCESSING", "READY", "CANCELLED"]


def cert_counts():
    out = {s: 0 for s in CERT_STATUSES}
    for r in db.query("SELECT status, COUNT(*) AS n FROM cert_requests GROUP BY status"):
        out[r["status"]] = r["n"]
    out["ALL"] = sum(out.values())
    return out


def certs(status=None, limit=300):
    sql = "SELECT c.*, s.name, s.department, s.section FROM cert_requests c LEFT JOIN students s ON s.usn=c.usn"
    params = []
    if status in CERT_STATUSES:
        sql += " WHERE c.status=?"
        params.append(status)
    sql += " ORDER BY (c.status='PROCESSING') DESC, c.id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


# ------------------------------------------------------------------ students
PAGE_SIZE = 25


def departments():
    return [r["department"] for r in db.query("SELECT DISTINCT department FROM students ORDER BY department")]


def students(q="", dept="", linked="", page=1):
    where, params = [], []
    if q:
        where.append("(s.usn ILIKE ? OR s.name ILIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if dept:
        where.append("s.department=?")
        params.append(dept)
    if linked == "1":
        where.append("u.phone IS NOT NULL")
    elif linked == "0":
        where.append("u.phone IS NULL")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    base = ("FROM students s LEFT JOIN users u ON u.usn=s.usn "
            "LEFT JOIN (SELECT usn, SUM(classes_held) AS h, SUM(classes_attended) AS a FROM attendance GROUP BY usn) att "
            "ON att.usn=s.usn LEFT JOIN fees f ON f.usn=s.usn" + w)
    total = _one("SELECT COUNT(*) " + base, tuple(params))
    page = max(1, page)
    rows = db.query("SELECT s.*, (u.phone IS NOT NULL) AS linked, "
                    "CASE WHEN att.h>0 THEN ROUND((100.0*att.a/att.h)::numeric,1) END AS att_pct, "
                    "COALESCE(f.total_fee-f.paid,0) AS fee_due " + base +
                    " ORDER BY s.usn LIMIT ? OFFSET ?", tuple(params) + (PAGE_SIZE, (page - 1) * PAGE_SIZE))
    return rows, total, page, max(1, -(-total // PAGE_SIZE))


def save_student(usn, name, department, section, semester, dob, email):
    """Insert or update one student. Blank DOB on an existing student keeps the old one."""
    usn = usn.strip().upper()
    dob = "".join(ch for ch in dob if ch.isdigit())
    if not usn or not name.strip():
        raise ValueError("USN and name are required.")
    if dob and len(dob) != 8:
        raise ValueError("Date of birth must be DDMMYYYY (8 digits).")
    try:
        sem = int(semester)
    except ValueError:
        raise ValueError("Semester must be a number.")
    existing = db.get_student(usn)
    if not existing and not dob:
        raise ValueError("Date of birth is required for a new student (students use it to verify on WhatsApp).")
    db.execute("INSERT INTO students(usn,name,department,section,semester,dob,email) VALUES(?,?,?,?,?,?,?) "
               "ON CONFLICT(usn) DO UPDATE SET name=EXCLUDED.name, department=EXCLUDED.department, "
               "section=EXCLUDED.section, semester=EXCLUDED.semester, dob=EXCLUDED.dob, email=EXCLUDED.email",
               (usn, name.strip(), department.strip().upper(), section.strip().upper(), sem,
                dob or existing["dob"], email.strip()))
    return usn


def save_fee(usn, total, paid, due_date):
    total, paid = float(total), float(paid)
    if total < 0 or paid < 0:
        raise ValueError("Amounts cannot be negative.")
    db.execute("INSERT INTO fees(usn,total_fee,paid,due_date) VALUES(?,?,?,?) ON CONFLICT(usn) DO UPDATE SET "
               "total_fee=EXCLUDED.total_fee, paid=EXCLUDED.paid, due_date=EXCLUDED.due_date",
               (usn, total, paid, due_date.strip()))


# ------------------------------------------------------------------ notices
def notices(limit=100):
    return db.query("SELECT * FROM notifications ORDER BY date DESC, id DESC LIMIT ?", (limit,))


def add_notice(date, department, section, title, body):
    if not title.strip() or not body.strip():
        raise ValueError("Title and message are required.")
    db.execute("INSERT INTO notifications(date,department,section,title,body) VALUES(?,?,?,?,?)",
               (date, (department or "ALL").upper(), (section or "ALL").upper(), title.strip(), body.strip()))


def delete_notice(nid):
    return db.execute("DELETE FROM notifications WHERE id=?", (nid,))[1]


# ------------------------------------------------------------------ alerts
def low_attendance_students():
    return db.query(
        "SELECT s.usn, s.name, s.department, s.section, (u.phone IS NOT NULL) AS linked, "
        "COUNT(*) AS n_subjects, MIN(100.0*a.classes_attended/a.classes_held) AS worst "
        "FROM attendance a JOIN students s ON s.usn=a.usn LEFT JOIN users u ON u.usn=s.usn "
        "WHERE a.classes_held>0 AND 100.0*a.classes_attended/a.classes_held < ? "
        "GROUP BY s.usn, s.name, s.department, s.section, u.phone ORDER BY worst", (config.ATTENDANCE_THRESHOLD,))


def recent_alerts(limit=15):
    return db.query("SELECT l.usn, l.sent_at, s.name FROM alert_log l LEFT JOIN students s ON s.usn=l.usn "
                    "ORDER BY l.sent_at DESC LIMIT ?", (limit,))


def dataset_counts():
    return {n: _one(f"SELECT COUNT(*) FROM {n}") for n in db.LOAD_ORDER}
