<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,24&height=230&section=header&text=ContXpert&fontSize=72&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=AI-Based%20WhatsApp%20Chatbot%20for%20Smart%20Student%20Support&descSize=20&descAlignY=60" width="100%" alt="ContXpert"/>

<img src="https://fonts.gstatic.com/s/e/notoemoji/latest/1f393/512.gif" width="60" alt="graduation cap"/>
<img src="https://fonts.gstatic.com/s/e/notoemoji/latest/1f916/512.gif" width="60" alt="robot"/>
<img src="https://fonts.gstatic.com/s/e/notoemoji/latest/1f680/512.gif" width="60" alt="rocket"/>

<a href="https://github.com/LekhanaGowda07/ContXpert">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=1200&color=25D366&center=true&vCenter=true&width=700&lines=Check+attendance+on+WhatsApp;Get+CIE+marks+in+seconds;Request+certificates+without+queues;Powered+by+RAG+%2B+LLMs" alt="Typing animation"/>
</a>

<br/>

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![WhatsApp](https://img.shields.io/badge/WhatsApp-Cloud%20API-25D366?logo=whatsapp&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-Groq-F55036)
![RAG](https://img.shields.io/badge/RAG-Chroma%20%2F%20FAISS-8A2BE2)
![ML](https://img.shields.io/badge/ML-Insights-FF9800)
![Status](https://img.shields.io/badge/status-in%20development-orange)

</div>

---

## 📖 Overview

**ContXpert** extends the **MCE Contineo** student information system with a conversational AI layer on WhatsApp. Instead of logging in to a portal and clicking through menus, students simply text the bot and get instant, personalised answers about their academics.

It combines a **secure, identity-bound login**, a **modular Python backend**, an **ML layer** for insights, and a **Retrieval-Augmented Generation (RAG)** pipeline powered by an LLM, so the bot can answer both structured queries (marks, attendance) and free-form questions (rules, circulars, procedures).

---

## 🎬 See It in Action

<div align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=16&duration=2800&pause=900&color=128C7E&background=ECE5DD&center=false&vCenter=true&width=560&height=60&lines=You%3A+hi;Bot%3A+Welcome+to+ContXpert%21+Enter+your+USN;You%3A+4MC23CS042;Bot%3A+Enter+your+DOB+DD-MM-YYYY;You%3A+15-08-2005;Bot%3A+Verified%21+Number+matches+records;You%3A+attendance;Bot%3A+DSA+88%25%2C+OS+91%25%2C+DBMS+74%25+Low" alt="Animated chat demo"/>
  <p><i>Login, verification and an attendance query, all inside WhatsApp.</i></p>
</div>

---

## ✨ Features

| | Feature | Description |
|---|---|---|
| 📊 | **Attendance** | Subject-wise attendance with low-attendance alerts |
| 📝 | **CIE Marks** | CIE1, CIE2, CIE3, ACT1, ACT2 (10 marks each) with an aggregate calculator |
| 💰 | **Fees** | Fee status and dues at a glance |
| 🗓️ | **Timetable** | Day-wise class schedule |
| 🔔 | **Notifications** | Proactive alerts and announcements |
| 📜 | **Certificates** | Request, pay online, and track status |
| 🏫 | **Multi-department** | Supports multiple departments and sections |
| 🧠 | **AI Q&A** | RAG-backed answers to open-ended student queries |
| 🛠️ | **Admin Site** | Dashboard for staff to manage data and requests |

---

## 🔐 Secure Login Flow

Authentication binds a student's WhatsApp number to their college record. A student is authenticated **only if all three checks pass**.

```mermaid
flowchart LR
    A([Student sends message]) --> B[Bot asks for USN]
    B --> C[Bot asks for DOB]
    C --> D{USN + DOB valid<br/>AND sender number =<br/>registered mobile?}
    D -- Yes --> E[✅ Authenticated session]
    D -- No --> F[❌ Access denied]
    E --> G[Menu: Attendance · CIE · Fees · Timetable · Certificates]
```

---

## 🏗️ Architecture

```mermaid
flowchart TB
    S[👩‍🎓 Student on WhatsApp] <--> W[WhatsApp Cloud API<br/>Meta]
    W -- webhook --> API[⚙️ app.py<br/>Python server]

    subgraph Backend
        API --> BOT[🤖 bot.py<br/>Auth · Intent Router]
        BOT --> ACAD[📚 Academic Services<br/>Attendance · CIE · Fees · Timetable]
        BOT --> CERT[📜 Certificate Service]
        BOT --> RAG[🧠 RAG Pipeline]
        BOT --> ML[📈 ml/<br/>Insights]
        ALERT[🔔 alerts.py<br/>Scheduled alerts] --> W
    end

    ACAD --> DB[(🐘 PostgreSQL<br/>Neon)]
    BOT --> DB
    CERT --> DB
    ADMIN[🛠️ admin_site/] --> DB
    RAG --> VEC[(🔎 Vector Store<br/>Chroma / FAISS)]
    RAG --> LLM[🤖 Groq-hosted LLM]
    API -- reply --> W
```

### 💬 Request lifecycle

```mermaid
sequenceDiagram
    participant U as Student
    participant WA as WhatsApp Cloud API
    participant S as ContXpert Server
    participant DB as PostgreSQL
    participant R as RAG + LLM

    U->>WA: "What's my attendance?"
    WA->>S: POST /webhook
    S->>DB: Verify session and fetch records
    alt Structured query
        DB-->>S: Attendance data
    else Open-ended query
        S->>R: Retrieve context and generate
        R-->>S: Grounded answer
    end
    S->>WA: Send reply
    WA->>U: 📱 Response
```

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| **Language / Server** | Python 3 |
| **Messaging** | Meta WhatsApp Cloud API |
| **Database** | PostgreSQL (hosted on Neon) |
| **AI / NLP** | Groq-hosted LLM, Retrieval-Augmented Generation |
| **Vector Search** | Chroma / FAISS |
| **Machine Learning** | Custom models in `ml/` |
| **Dev Tooling** | ngrok (local webhook tunnelling), pytest |

---

## 📁 Project Structure

```text
ContXpert/
├── admin_site/        # Admin dashboard for staff
├── data/              # Mock data / CSV imports
├── ml/                # ML models and insights
├── tests/             # Test suite
├── .env.example       # Sample environment variables
├── .gitignore
├── alerts.py          # Attendance and notification alerts
├── app.py             # Server and WhatsApp webhook
├── bot.py             # Bot logic: auth, intents, replies
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A PostgreSQL database (e.g. [Neon](https://neon.tech))
- A Meta developer account with WhatsApp Cloud API access
- A Groq API key
- [ngrok](https://ngrok.com) for local development

### 1. Clone and install

```bash
git clone https://github.com/LekhanaGowda07/ContXpert.git
cd ContXpert
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```env
# WhatsApp Cloud API
WHATSAPP_TOKEN=your_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WEBHOOK_VERIFY_TOKEN=any_secret_string_you_choose

# Database
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require

# LLM
GROQ_API_KEY=your_groq_api_key
```

### 3. Run the server

```bash
python app.py
```

### 4. Expose it and connect WhatsApp

```bash
ngrok http 5000
```

In the Meta developer dashboard, set:

- **Callback URL:** `https://<your-ngrok-id>.ngrok-free.app/webhook`
- **Verify token:** the same value as `WEBHOOK_VERIFY_TOKEN`
- **Subscribed field:** `messages`

Then message your WhatsApp test number. 🎉

### 5. Run tests

```bash
pytest tests/
```

---

## 🗺️ Roadmap

- [x] Core WhatsApp webhook and message handling
- [x] USN + DOB + registered-number authentication
- [x] CIE scheme support (5 × 10 marks)
- [ ] Replace mock data with real CSV imports
- [ ] Attendance alert scheduler
- [ ] Certificate request + online payment + status tracking
- [ ] ML-driven insights (performance and attendance risk prediction)
- [ ] Evaluation: retrieval F1, response time, task completion

---

## 🔒 Security and Privacy

- Identity is verified with **three factors**: USN, DOB and the sender's registered phone number
- Students can only ever access **their own** records
- Secrets live in environment variables and are never committed
- Student data is stored in a managed PostgreSQL instance over TLS

---

## 👩‍💻 Author

**Lekhana**
*Computer Science and Engineering, Malnad College of Engineering, Hassan.*

---

## 📄 License

Distributed under the MIT License.

<div align="center">

⭐ If you find this project useful, consider giving it a star!

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,24&height=120&section=footer" width="100%" alt="footer"/>

</div>
