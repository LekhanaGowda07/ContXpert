"""Generate MOCK CSV files in ./data. Replace these CSVs with real exports later
(keep the same column names) and restart the app - data is re-imported on every start.

Usage:  python seed_mock_data.py
"""
import csv
import os
import random

import config

rng = random.Random(42)
dob_rng = random.Random(7)   # separate stream: keeps all other mock CSVs unchanged
os.makedirs(config.DATA_DIR, exist_ok=True)

SUBJECTS = {
    "CSE": [("CS701", "Machine Learning"), ("CS702", "Cloud Computing"), ("CS703", "Compiler Design"),
            ("CS704", "Information Security"), ("CS705", "Software Testing")],
    "ISE": [("IS701", "Data Mining"), ("IS702", "Computer Networks"), ("IS703", "Operating Systems"),
            ("IS704", "Web Technologies"), ("IS705", "Software Engineering")],
    "ECE": [("EC701", "VLSI Design"), ("EC702", "Embedded Systems"), ("EC703", "Wireless Communication"),
            ("EC704", "Digital Signal Processing"), ("EC705", "Antenna Theory")],
}
BRANCH = {"CSE": "CS", "ISE": "IS", "ECE": "EC"}
SEM = 7

# (department, section, first USN number, names)
GROUPS = [
    ("CSE", "A", 49, ["Aarav M", "Bhavana K", "Chetan R", "Gowtham V", "Harini S", "Imran P"]),
    ("CSE", "B", 75, ["Ananya R", "Rohan K", "Lakshmi SM", "Lekhana BS", "Vikram S", "Divya H"]),
    ("ISE", "A", 1, ["Karthik N", "Meghana T", "Nikhil G", "Pooja D", "Rakesh B", "Sneha L"]),
    ("ECE", "A", 101, ["Tejas J", "Usha C", "Varun A", "Yash Q", "Zoya F", "Abhishek W"]),
]
DOB_OVERRIDE = {"4MC23CS078": "15082005"}   # demo login (MOCK)
MOBILE_OVERRIDE = {"4MC23CS078": "9000000078"}  # handy demo login (MOCK number, replace with real data)


def write(name, header, rows):
    with open(os.path.join(config.DATA_DIR, name), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


students, attendance, cie, fees = [], [], [], []
counter = 0
for dept, sec, start, names in GROUPS:
    for i, nm in enumerate(names):
        usn = f"4MC23{BRANCH[dept]}{start + i:03d}"
        counter += 1
        mobile = MOBILE_OVERRIDE.get(usn) or f"98{counter:08d}"
        dob = DOB_OVERRIDE.get(usn) or f"{dob_rng.randint(1, 28):02d}{dob_rng.randint(1, 12):02d}{dob_rng.choice([2004, 2005])}"
        students.append([usn, nm, dept, sec, SEM, dob, mobile, f"{nm.split()[0].lower()}.{usn.lower()}@example.com"])
        base = rng.choice([0.62, 0.68, 0.74, 0.80, 0.85, 0.90, 0.94])
        for code, sname in SUBJECTS[dept]:
            held = rng.randint(38, 46)
            pct = min(1.0, max(0.3, base + rng.uniform(-0.09, 0.09)))
            attendance.append([usn, code, sname, held, round(held * pct)])
            quality = min(1.0, max(0.25, base + rng.uniform(-0.2, 0.15)))
            r5 = lambda x: round(x * 2) / 2
            row = [usn, code, sname]
            for chance in (1.0, 0.9, 0.7, 0.8, 0.5):   # cie1, cie2, cie3, act1, act2 (blank = not conducted yet)
                row.append(r5(10 * min(1, max(0, quality + rng.uniform(-0.12, 0.12)))) if rng.random() < chance else "")
            cie.append(row)
        total = 150000
        paid = rng.choice([total, total, total, 100000, 75000, 50000])
        fees.append([usn, total, paid, "2026-11-30"])

write("students.csv", ["usn", "name", "department", "section", "semester", "dob", "mobile", "email"], students)
write("attendance.csv", ["usn", "subject_code", "subject_name", "classes_held", "classes_attended"], attendance)
write("cie.csv", ["usn", "subject_code", "subject_name", "cie1", "cie2", "cie3", "act1", "act2"], cie)
write("fees.csv", ["usn", "total_fee", "paid", "due_date"], fees)

# ---- timetable ----
SLOTS = [("09:00", "10:00"), ("10:00", "11:00"), ("11:15", "12:15"), ("12:15", "13:15"), ("14:00", "15:00"), ("15:00", "16:00")]
FACULTY = ["Dr. Rao", "Prof. Sharma", "Dr. Nair", "Prof. Gowda", "Dr. Iyer"]
tt = []
for dept, sec, _, _ in GROUPS:
    subs = SUBJECTS[dept]
    for d_i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
        slots = SLOTS if day != "Sat" else SLOTS[:4]
        for p, (st, en) in enumerate(slots):
            code, sname = subs[(p + d_i) % len(subs)]
            tt.append([dept, sec, SEM, day, p + 1, st, en, code, sname, f"LH-{300 + (p + d_i) % 5 + 1}", FACULTY[(p + d_i) % 5]])
write("timetable.csv", ["department", "section", "semester", "day", "period", "start", "end",
                        "subject_code", "subject_name", "room", "faculty"], tt)

# ---- notifications (department/section can be ALL) ----
write("notifications.csv", ["date", "department", "section", "title", "body"], [
    ["2026-10-05", "ALL", "ALL", "IA-2 schedule released", "IA-2 tests begin on 20 Oct. Detailed timetable is on the notice board."],
    ["2026-10-03", "ALL", "ALL", "Fee payment reminder", "Last date to pay semester fees without fine is 30 Nov 2026."],
    ["2026-10-01", "CSE", "ALL", "ML lab internals", "Machine Learning lab internals on 14 Oct, bring your record books."],
    ["2026-09-28", "ALL", "ALL", "Gandhi Jayanti holiday", "College remains closed on 2 Oct."],
    ["2026-09-25", "CSE", "B", "Mentor meeting", "Section B mentor meeting on Friday 4 PM in Seminar Hall."],
    ["2026-09-20", "ALL", "ALL", "Placement training", "Aptitude training for 7th semester students starts next week."],
])
print("Mock CSV files written to", config.DATA_DIR)
print("Demo login: message from WhatsApp number 919000000078, USN 4MC23CS078, DOB 15082005")