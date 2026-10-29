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
python chat_cli.py             # chat in the terminal
```
Demo login (mock): USN `4MC23CS078` + mobile `9000000078`, or run `python chat_cli.py 919000000078` to try mobile-only login. Run tests: `python -m unittest discover -s tests`.

## Login
- **Mobile-only:** if the WhatsApp number matches exactly one student's `mobile` in students.csv, they are logged in automatically on their first message.
- **USN + mobile:** otherwise the bot asks for the USN, then the registered mobile number. A USN can be linked to one WhatsApp number only.
- Set `STRICT_MOBILE_MATCH=1` in `.env` to make USN + mobile login work only from the registered number itself (safer, since a mobile number is easy to know).

## 2. Replace mock data with real CSVs
Overwrite the files in `data/` keeping the same column names, then restart. Data is re-imported on every start.
- students.csv: usn,name,department,section,semester,mobile(10 digits),email
- attendance.csv: usn,subject_code,subject_name,classes_held,classes_attended
- cie.csv: usn,subject_code,subject_name,cie1,cie2,cie3,act1,act2   (each out of 10; blank = not conducted yet)
- fees.csv: usn,total_fee,paid,due_date
- timetable.csv: department,section,semester,day(Mon..Sat),period,start,end,subject_code,subject_name,room,faculty
- notifications.csv: date,department(or ALL),section(or ALL),title,body
Edit marks scheme / attendance threshold / certificate fees in `config.py`.

## 3. Meta WhatsApp Cloud API setup
1. Go to https://developers.facebook.com -> log in -> **My Apps -> Create App** -> choose the WhatsApp / Business use case.
2. In the app dashboard open **WhatsApp -> API Setup**. Copy the **Phone number ID** -> `WHATSAPP_PHONE_NUMBER_ID`.
   Meta gives a free test number. Copy the **temporary access token** -> `WHATSAPP_TOKEN` (expires in ~24h).
3. Under "To", add your own phone number as a recipient and verify the OTP (test numbers can only message recipients you add).
4. **Permanent token** (recommended):    -> Business Settings -> Users -> **System users** -> Add (Admin) ->
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
For 24/7 hosting use Render/Railway (start command: `gunicorn app:app --workers 1 --threads 4`); SQLite files are wiped on free tiers, so use a persistent disk or a hosted DB.

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
Set `ANTHROPIC_API_KEY` (console.anthropic.com) for natural FAQ answers and personalised tips. Everything works without it.

## Project layout
app.py (Flask webhook/admin/payment pages) | bot.py (conversation logic) | services.py (attendance/CIE maths) | db.py (SQLite + CSV import) |
whatsapp.py (Cloud API client) | payments.py | alerts.py (scheduler) | ml/ (intent, risk, rag) | chat_cli.py | tests/


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
python chat_cli.py             # chat in the terminal
```
Demo login (mock): USN `4MC23CS078`, DOB `15082005`; the CLI simulates sender `919000000078`, which is that student's mobile. Run tests: `python -m unittest discover -s tests`.

## Login (three-factor verification)
The bot asks for the **USN**, then the **date of birth** (DDMMYYYY). It also compares the **WhatsApp number the message
actually came from** (taken from Meta's webhook, not typed) with the registered `mobile` of that USN in students.csv.
Access is granted only if **all three match**. A failure never says which check failed, 5 failures lock the number for
30 minutes, and owning a registered number alone does not log you in. Country code is set by `DEFAULT_COUNTRY_CODE` (default 91).

## 2. Replace mock data with real CSVs
Overwrite the files in `data/` keeping the same column names, then restart. Data is re-imported on every start.
- students.csv: usn,name,department,section,semester,dob(DDMMYYYY),mobile(10 digits),email
- attendance.csv: usn,subject_code,subject_name,classes_held,classes_attended
- cie.csv: usn,subject_code,subject_name,cie1,cie2,cie3,act1,act2   (each out of 10; blank = not conducted yet)
- fees.csv: usn,total_fee,paid,due_date
- timetable.csv: department,section,semester,day(Mon..Sat),period,start,end,subject_code,subject_name,room,faculty
- notifications.csv: date,department(or ALL),section(or ALL),title,body
Edit marks scheme / attendance threshold / certificate fees in `config.py`.

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
For 24/7 hosting use Render/Railway (start command: `gunicorn app:app --workers 1 --threads 4`); SQLite files are wiped on free tiers, so use a persistent disk or a hosted DB.

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
Set `ANTHROPIC_API_KEY` (console.anthropic.com) for natural FAQ answers and personalised tips. Everything works without it.

## Project layout
app.py (Flask webhook/admin/payment pages) | bot.py (conversation logic) | services.py (attendance/CIE maths) | db.py (SQLite + CSV import) |
whatsapp.py (Cloud API client) | payments.py | alerts.py (scheduler) | ml/ (intent, risk, rag) | chat_cli.py | tests/#   C o n t X p e r t - - - M a l n a d  
 