# ContXpert - AI WhatsApp Chatbot for Smart Student Support (MCE Contineo extension)

Students chat on WhatsApp to get attendance, CIE marks, fees, timetable, notifications, a CIE target
calculator, certificate requests with online payment, and an AI risk report.

## AI / ML inside
| Feature | Technique |
|---|---|
| Understanding free text (typos, Hinglish) | TF-IDF (word + char n-grams) + Logistic Regression intent classifier (`ml/intent.py`) |
| Academic risk report | Gradient Boosting classifier on attendance, CIE and fee features (`ml/risk.py`) |
| College FAQ answers | TF-IDF retrieval (RAG) over `data/faq.json`, optionally rephrased by an LLM (`ml/rag.py`, `llm.py`) |
| Personalised study tips | Optional LLM (Anthropic API) - rule-based tips if no key |

NOTE: the risk model is trained on *synthetic* data until you provide real history
(`ml.risk.train_from_csv("history.csv")` with columns avg_att,min_att,n_short,avg_cie_pct,fee_due_ratio,at_risk).

## 1. Run locally (no WhatsApp needed)
```
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         # Mac/Linux: cp .env.example .env
python seed_mock_data.py       # only needed if data/*.csv are missing
# put your PostgreSQL URL in .env  ->  DATABASE_URL=postgresql://user:password@localhost:5432/contxpert
python chat_cli.py             # chat in the terminal
```
Demo login: USN `4MC23CS078`, DOB `15082005` (mock). Run tests: `python -m unittest discover -s tests`.

## 2. Replace mock data with real CSVs
The CSV files in `data/` seed an empty PostgreSQL database. During local development, ContXpert now checks `data/students.csv` for file changes and UPSERTs changed student rows before student lookup, so updated USN/name/DOB data is picked up without deleting WhatsApp registrations or restarting the server. For other datasets, upload CSVs in the admin console (`/console` -> Data). The admin console remains the recommended way to update production data.
Column names:
- students.csv: usn,name,department,section,semester,dob(DDMMYYYY),email
- attendance.csv: usn,subject_code,subject_name,classes_held,classes_attended
- cie.csv: usn,subject_code,subject_name,ia1,ia2,assignment   (leave blank = not conducted yet)
- fees.csv: usn,total_fee,paid,due_date
- timetable.csv: department,section,semester,day(Mon..Sat),period,start,end,subject_code,subject_name,room,faculty
- notifications.csv: date,department(or ALL),section(or ALL),title,body
Edit marks scheme / attendance threshold in `config.py`. Certificate fees are configurable in `.env`; update the relevant `CERT_FEE_*` value and restart the app (e.g. `CERT_FEE_BONAFIDE=1` for ₹1 or `CERT_FEE_BONAFIDE=10` for ₹10). Each new certificate request uses the current configured fee; existing requests keep their original amount.

## 3. Meta WhatsApp Cloud API setup
1. Go to https://developers.facebook.com -> log in -> **My Apps -> Create App** -> choose the WhatsApp / Business use case.
2. In the app dashboard open **WhatsApp -> API Setup**. Copy the **Phone number ID** -> `WHATSAPP_PHONE_NUMBER_ID`.
   Meta gives a free test number. Copy the **temporary access token** -> `WHATSAPP_TOKEN` (expires in ~24h).
3. Under "To", add your own phone number as a recipient and verify the OTP (test numbers can only message recipients you add).
4. **Permanent token** (recommended): business.facebook.com -> Business Settings -> Users -> **System users** -> Add (Admin) ->
   Add assets (your app, full control) -> **Generate token** with `whatsapp_business_messaging` + `whatsapp_business_management`, expiry Never.
5. **App secret**: App settings -> Basic -> App secret -> `WHATSAPP_APP_SECRET` (the server verifies Meta's signature).
6. Set `WHATSAPP_MOCK=0` in `.env`. Never commit `.env` or share tokens.

## 4. Expose your server and connect the webhook
```
python app.py                  # terminal 1 (port 5000)
ngrok http 5000                # terminal 2 -> copy the https URL, e.g. https://abcd.ngrok-free.app
```
Put that URL in `.env` as `BASE_URL`, restart `python app.py`.
In Meta: **WhatsApp -> Configuration -> Webhook -> Edit**:
- Callback URL: `https://abcd.ngrok-free.app/webhook`
- Verify token: same as `WHATSAPP_VERIFY_TOKEN` in `.env`
- Click **Verify and save**, then under *Webhook fields* **subscribe to `messages`**.
Now WhatsApp the test number from your phone: "hi" -> register with USN + DOB.
For 24/7 hosting use Render (start command: `gunicorn app:app --workers 1 --threads 4 --timeout 120`) with a PostgreSQL database (see section 8).

## 5. Proactive alerts (WhatsApp rule)
Free-form messages are only allowed within 24h of the student's last message. For the daily attendance alerts to reach everyone,
create a **message template** (WhatsApp Manager -> Message templates, category Utility), e.g.
`Hi {{1}}, your attendance is below 75% in: {{2}}. Reply "attendance" for details.` Once approved, set `WHATSAPP_TEMPLATE_ALERT=<template_name>`.
Alerts run daily at `ALERT_HOUR` IST (re-sent only after `ALERT_COOLDOWN_DAYS`). Test now:
`curl -X POST "localhost:5000/admin/run-alerts?force=1" -H "X-Admin-Key: <ADMIN_KEY>"`

## 6. Certificates & payments
Student flow: Certificates -> choose -> Pay -> link. `PAYMENT_MODE=mock` serves a fake checkout at `/pay/<id>`.
For real payments set `PAYMENT_MODE=razorpay`, add the Razorpay keys, and point a Razorpay webhook
(event `payment_link.paid`) to `https://<your-url>/razorpay/webhook`.
Office marks a certificate ready (student gets a WhatsApp message):
`curl -X POST <BASE_URL>/admin/certificates/<id>/ready -H "X-Admin-Key: <ADMIN_KEY>"`  (list: `GET /admin/certificates`).

## 7. Optional LLM
Set `ANTHROPIC_API_KEY` (console.anthropic.com) for natural FAQ answers, personalised tips, and general conversational WhatsApp replies. Once configured, students can send normal messages (not only menu commands) and ContXpert will respond conversationally. Without a valid key, the structured student features continue to work, but general AI chat is unavailable.

## Project layout
app.py (Flask webhook/admin/payment pages) | bot.py (conversation logic) | services.py (attendance/CIE maths) | db.py (SQLite + CSV import) |
whatsapp.py (Cloud API client) | payments.py | alerts.py (scheduler) | ml/ (intent, risk, rag) | chat_cli.py | tests/

## 8. PostgreSQL + admin console
- Storage is PostgreSQL (`DATABASE_URL`). Tables are created automatically on start; the CSVs in `data/` seed an empty database once.
- Admin website: open `<BASE_URL>/console` and sign in with `ADMIN_KEY`. Dashboard, certificate requests (mark ready -> WhatsApp message),
  students (add / edit / fees / unlink WhatsApp), notices, CSV import/export of every dataset, attendance alerts.
- The old JSON admin API (`/admin/...` with the `X-Admin-Key` header) still works.
- Tests need an empty throw-away database: `TEST_DATABASE_URL=postgresql://... python -m unittest discover -s tests`
  (never point it at your real database - the tests create users and certificate requests).
