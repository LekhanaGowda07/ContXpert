"""Automated attendance alerts + scheduler."""
import logging
from datetime import datetime, timedelta, timezone

import config
import db
import services
import whatsapp as wa

log = logging.getLogger("alerts")


def _recently_alerted(usn):
    last = db.last_alert(usn)
    if not last:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(days=config.ALERT_COOLDOWN_DAYS)


def run_attendance_alerts(force=False):
    """Send an alert to every registered student below the threshold. Returns number of alerts sent."""
    sent = 0
    for u in db.all_users():
        student = db.get_student(u["usn"])
        if not student:
            continue
        low = [s for s in services.get_attendance(u["usn"])["subjects"] if s["short"]]
        if not low or (not force and _recently_alerted(u["usn"])):
            continue
        lines = [f"• {s['name']}: {s['pct']}% (attend next {s['need']} classes to reach {config.ATTENDANCE_THRESHOLD:g}%)"
                 for s in low]
        first = student["name"].split()[0]
        text = (f"⚠️ *Attendance alert*\nHi {first}, your attendance is below {config.ATTENDANCE_THRESHOLD:g}% in:\n"
                + "\n".join(lines) + "\n\nReply *attendance* for full details.")
        ok = wa.send_text(u["phone"], text)
        if not ok and config.WA_TEMPLATE_ALERT:   # outside the 24h window free text is rejected -> use template
            summary = ", ".join(f"{s['name']} {s['pct']}%" for s in low)
            ok = wa.send_template(u["phone"], config.WA_TEMPLATE_ALERT, [first, summary])
        if ok:
            db.log_alert(u["usn"])
            sent += 1
    log.info("attendance alerts sent: %d", sent)
    return sent


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler(timezone="Asia/Kolkata", daemon=True)
    sched.add_job(run_attendance_alerts, "cron", hour=config.ALERT_HOUR, minute=0, id="attendance_alerts",
                  misfire_grace_time=3600, coalesce=True)
    sched.start()
    return sched
