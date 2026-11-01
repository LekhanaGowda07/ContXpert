"""Admin console routes (/console). Login = ADMIN_KEY. All pages are server-rendered Jinja templates."""
import hmac
import logging
import secrets
import time
from datetime import datetime
from functools import wraps

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template, request, session, url_for)

import alerts
import config
import db
import payments
import services

from . import queries as q

log = logging.getLogger("admin")
bp = Blueprint("console", __name__, url_prefix="/console", template_folder="templates",
               static_folder="static", static_url_path="/static")

_fails = {}                      # ip -> (count, first_fail_ts)   (per process, enough to slow down guessing)
MAX_FAILS, LOCK_SECONDS = 5, 600

CERT_LABELS = {"PENDING_PAYMENT": "Awaiting payment", "PROCESSING": "To process", "READY": "Ready",
               "CANCELLED": "Cancelled"}


# ------------------------------------------------------------------ helpers
def _ip():
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "?")


def _key_is_safe():
    k = config.ADMIN_KEY
    return config.WHATSAPP_MOCK or (len(k) >= 10 and not k.startswith("change-me"))


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("console.login", next=request.path))
        return f(*a, **kw)
    return wrapper


@bp.before_request
def _guard():
    if request.endpoint == "console.static":
        return
    session.permanent = True
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    if request.method == "POST" and not hmac.compare_digest(request.form.get("csrf", ""), session["csrf"]):
        abort(400, "Your session expired - go back, refresh the page and try again.")


@bp.after_request
def _headers(resp):
    if request.endpoint != "console.static":
        resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


@bp.app_template_filter("mask_phone")
def mask_phone(p):
    p = str(p or "")
    return ("•" * max(0, len(p) - 4) + p[-4:]) if p else "-"


@bp.app_template_filter("when")
def when(iso):
    """ISO timestamp (UTC) -> 'dd Mon, HH:MM' in IST."""
    try:
        return services_ist(iso).strftime("%d %b, %H:%M")
    except Exception:
        return iso or "-"


def services_ist(iso):
    return datetime.fromisoformat(iso).astimezone(services.IST)


@bp.app_template_filter("inr")
def inr(v):
    return f"₹{float(v or 0):,.0f}"


@bp.app_context_processor
def _ctx():
    return {"csrf": session.get("csrf", ""), "cert_labels": CERT_LABELS, "threshold": config.ATTENDANCE_THRESHOLD,
            "certificates": config.CERTIFICATES}


def _back(default="console.dashboard", **kw):
    nxt = request.form.get("next", "")
    return redirect(nxt if nxt.startswith("/console") and not nxt.startswith("//") else url_for(default, **kw))


# ------------------------------------------------------------------ login / logout
@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin"):
        return redirect(url_for("console.dashboard"))
    if request.method == "POST":
        ip = _ip()
        n, first = _fails.get(ip, (0, 0))
        if n >= MAX_FAILS and time.time() - first < LOCK_SECONDS:
            flash("Too many wrong attempts. Try again in a few minutes.", "error")
        elif not _key_is_safe():
            flash("ADMIN_KEY is still the default / too short. Set a long random ADMIN_KEY in your environment first.",
                  "error")
        elif hmac.compare_digest(request.form.get("password", "").encode(), config.ADMIN_KEY.encode()):
            _fails.pop(ip, None)
            session.clear()
            session["admin"] = True
            session["csrf"] = secrets.token_urlsafe(24)
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/console") and not nxt.startswith("//") else url_for("console.dashboard"))
        else:
            _fails[ip] = (n + 1, first if n and time.time() - first < LOCK_SECONDS else time.time())
            flash("Wrong password.", "error")
    return render_template("admin/login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("console.login"))


@bp.get("/")
@login_required
def dashboard():
    system = {
        "Database": "Connected" if db.ping() else "NOT reachable",
        "WhatsApp": "Test mode (no real messages)" if config.WHATSAPP_MOCK else "Live",
        "Payments": "Razorpay (live)" if config.PAYMENT_MODE == "razorpay" else "Mock checkout",
        "AI answers (Gemini)": "On" if config.GEMINI_API_KEY else "Off (rule-based)",
        "Daily alerts": f"{config.ALERT_HOUR:02d}:00 IST",
    }
    return render_template("admin/dashboard.html", page="dashboard", stats=q.dashboard_stats(),
                           recent=q.recent_certs(), system=system)


# ------------------------------------------------------------------ certificates
@bp.get("/certificates")
@login_required
def certificates():
    status = request.args.get("status", "")
    return render_template("admin/certificates.html", page="certificates", status=status,
                           rows=q.certs(status or None), counts=q.cert_counts())


@bp.post("/certificates/<int:req_id>/ready")
@login_required
def cert_ready(req_id):
    if payments.mark_ready(req_id):
        flash(f"Request #{req_id} marked ready - the student was notified on WhatsApp.", "ok")
    else:
        flash("Only paid requests (status 'To process') can be marked ready.", "error")
    return _back("console.certificates")


@bp.post("/certificates/<int:req_id>/cancel")
@login_required
def cert_cancel(req_id):
    if db.set_cert_status(req_id, "CANCELLED", expected="PENDING_PAYMENT"):
        flash(f"Request #{req_id} cancelled.", "ok")
    else:
        flash("Only requests that are still awaiting payment can be cancelled.", "error")
    return _back("console.certificates")


# ------------------------------------------------------------------ students
@bp.get("/students")
@login_required
def students():
    qs = request.args.get("q", "").strip()
    dept, linked = request.args.get("dept", ""), request.args.get("linked", "")
    page = request.args.get("page", 1, type=int)
    rows, total, page, pages = q.students(qs, dept, linked, page)
    return render_template("admin/students.html", page="students", rows=rows, total=total, pg=page, pages=pages,
                           qs=qs, dept=dept, linked=linked, depts=q.departments())


@bp.route("/students/new", methods=["GET", "POST"])
@login_required
def student_new():
    if request.method == "POST":
        f = request.form
        try:
            usn = q.save_student(f["usn"], f["name"], f["department"], f["section"], f["semester"], f.get("dob", ""),
                                 f.get("email", ""))
            flash(f"Saved {usn}.", "ok")
            return redirect(url_for("console.student_detail", usn=usn))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("admin/student_form.html", page="students", s=request.form or {}, is_new=True)


@bp.get("/students/<usn>")
@login_required
def student_detail(usn):
    s = db.get_student(usn)
    if not s:
        abort(404)
    return render_template("admin/student_detail.html", page="students", s=s,
                           user=db.get_user_by_usn(usn), att=services.get_attendance(usn),
                           cie=services.get_cie(usn), fees=services.get_fees(usn),
                           certs=db.list_certs(usn, 10), comps=config.CIE_COMPONENTS)


@bp.route("/students/<usn>/edit", methods=["GET", "POST"])
@login_required
def student_edit(usn):
    s = db.get_student(usn)
    if not s:
        abort(404)
    if request.method == "POST":
        f = request.form
        try:
            q.save_student(usn, f["name"], f["department"], f["section"], f["semester"], f.get("dob", ""),
                           f.get("email", ""))
            flash("Student updated.", "ok")
            return redirect(url_for("console.student_detail", usn=usn))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("admin/student_form.html", page="students", s=s, is_new=False)


@bp.post("/students/<usn>/fees")
@login_required
def student_fees(usn):
    if not db.get_student(usn):
        abort(404)
    try:
        q.save_fee(usn.upper(), request.form["total_fee"], request.form["paid"], request.form.get("due_date", ""))
        flash("Fee record updated.", "ok")
    except (ValueError, KeyError):
        flash("Enter valid fee amounts.", "error")
    return redirect(url_for("console.student_detail", usn=usn))


@bp.post("/students/<usn>/unlink")
@login_required
def student_unlink(usn):
    n = db.unbind_user(usn=usn)
    flash("WhatsApp number unlinked - the student can register again." if n else "Nothing to unlink.", "ok")
    return redirect(url_for("console.student_detail", usn=usn))


# ------------------------------------------------------------------ notices
@bp.route("/notices", methods=["GET", "POST"])
@login_required
def notices():
    if request.method == "POST":
        f = request.form
        try:
            q.add_notice(f.get("date") or datetime.now(services.IST).strftime("%Y-%m-%d"), f.get("department", "ALL"),
                         f.get("section", "ALL"), f.get("title", ""), f.get("body", ""))
            flash("Notice published - students will see it under Notifications on WhatsApp.", "ok")
            return redirect(url_for("console.notices"))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("admin/notices.html", page="notices", rows=q.notices(), depts=q.departments(),
                           today=datetime.now(services.IST).strftime("%Y-%m-%d"))


@bp.post("/notices/<int:nid>/delete")
@login_required
def notice_delete(nid):
    flash("Notice deleted." if q.delete_notice(nid) else "Notice not found.", "ok")
    return redirect(url_for("console.notices"))


# ------------------------------------------------------------------ data (CSV import / export)
DATASET_HELP = {
    "students": "Student list + date of birth (used to verify students on WhatsApp)",
    "attendance": "Classes held / attended per subject",
    "cie": "Internal marks (blank = not conducted yet)",
    "fees": "Total fee, amount paid, due date",
    "timetable": "Weekly class timetable per department / section / semester",
    "notifications": "Notices shown to students",
}
MAX_UPLOAD = 5 * 1024 * 1024


@bp.get("/data")
@login_required
def data():
    return render_template("admin/data.html", page="data", counts=q.dataset_counts(), help=DATASET_HELP,
                           cols={n: db.DATASETS[n][2] for n in db.LOAD_ORDER}, order=db.LOAD_ORDER)


@bp.post("/data/<name>/import")
@login_required
def data_import(name):
    if name not in db.DATASETS:
        abort(404)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a CSV file first.", "error")
        return redirect(url_for("console.data"))
    raw = f.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        flash("File is larger than 5 MB.", "error")
        return redirect(url_for("console.data"))
    replace = request.form.get("mode") == "replace"
    try:
        rows = db.parse_csv(name, raw.decode("utf-8-sig"))
        if replace and not rows:
            raise ValueError("The file has no data rows - refusing to wipe the table with an empty file.")
        n = db.import_rows(name, rows, replace=replace)
        flash(f"{name}: {n} row(s) {'imported (table replaced)' if replace else 'merged'}.", "ok")
    except UnicodeDecodeError:
        flash("Could not read the file - save it as CSV (UTF-8).", "error")
    except (ValueError, KeyError) as e:
        flash(f"Import failed, nothing was changed. {e}", "error")
    except Exception:
        log.exception("csv import failed")
        flash("Import failed, nothing was changed (see server logs).", "error")
    return redirect(url_for("console.data"))


@bp.get("/data/<name>/export")
@login_required
def data_export(name):
    if name not in db.DATASETS:
        abort(404)
    return Response(db.export_csv(name), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}.csv"})


# ------------------------------------------------------------------ alerts
@bp.route("/alerts", methods=["GET", "POST"])
@login_required
def alerts_page():
    if request.method == "POST":
        try:
            n = alerts.run_attendance_alerts(force=request.form.get("force") == "1")
            flash(f"Attendance alerts sent: {n}.", "ok")
        except Exception:
            log.exception("manual alert run failed")
            flash("Could not send alerts (see server logs).", "error")
        return redirect(url_for("console.alerts_page"))
    return render_template("admin/alerts.html", page="alerts", low=q.low_attendance_students(),
                           recent=q.recent_alerts())
