<div align="center">

<img src="assets/banner.svg" alt="ContXpert" width="100%"/>

<a href="https://github.com/LekhanaGowda07/ContXpert">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=1200&color=25D366&center=true&vCenter=true&width=700&lines=Check+attendance+on+WhatsApp+%F0%9F%93%8A;Get+CIE+marks+in+seconds+%F0%9F%93%9D;Request+certificates+without+queues+%F0%9F%93%9C;Powered+by+RAG+%2B+LLMs+%F0%9F%A7%A0" alt="Typing animation"/>
</a>

![Node.js](https://img.shields.io/badge/Node.js-18+-339933?logo=nodedotjs&logoColor=white)
![Express](https://img.shields.io/badge/Express-4.x-000000?logo=express&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![WhatsApp](https://img.shields.io/badge/WhatsApp-Cloud%20API-25D366?logo=whatsapp&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-Groq-F55036)
![RAG](https://img.shields.io/badge/RAG-Chroma%20%2F%20FAISS-8A2BE2)
![Status](https://img.shields.io/badge/status-in%20development-orange)

</div>

---

## 📖 Overview

**ContXpert** extends the **MCE Contineo** student information system with a conversational AI layer on WhatsApp. Instead of logging in to a portal and clicking through menus, students simply text the bot and get instant, personalised answers about their academics.

It combines a **secure, identity-bound login**, a **modular Node.js backend**, and a **Retrieval-Augmented Generation (RAG)** pipeline powered by an LLM, so the bot can answer both structured queries (marks, attendance) and free-form questions (rules, circulars, procedures).

---

## 🎬 See It in Action

<div align="center">
  <img src="assets/chat-demo.svg" alt="Animated chat demo" width="420"/>
  <p><i>Login, verification and an attendance query, all inside WhatsApp.</i></p>
</div>

---

## ⚡ Live Data Flow

<div align="center">
  <img src="assets/flow.svg" alt="Animated data flow" width="100%"/>
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
    W -- webhook --> API[⚙️ Express Server<br/>Node.js]

    subgraph Backend
        API --> AUTH[🔐 Auth Module<br/>USN · DOB · Phone]
        API --> ROUTER[🧭 Intent Router]
        ROUTER --> ACAD[📚 Academic Services<br/>Attendance · CIE · Fees · Timetable]
        ROUTER --> CERT[📜 Certificate Service]
        ROUTER --> RAG[🧠 RAG Pipeline]
    end

    ACAD --> DB[(🐘 PostgreSQL<br/>Neon)]
    AUTH --> DB
    CERT --> DB
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
| **Runtime / Server** | Node.js, Express |
| **Messaging** | Meta WhatsApp Cloud API |
| **Database** | PostgreSQL (hosted on Neon) |
| **AI / NLP** | Groq-hosted LLM, Retrieval-Augmented Generation |
| **Vector Search** | Chroma / FAISS |
| **Dev Tooling** | ngrok (local webhook tunnelling) |

---

## 📁 Project Structure

```text
ContXpert/
├── src/
│   ├── server.js            # Express app entry point
│   ├── routes/
│   │   └── webhook.js       # WhatsApp webhook (verify + receive)
│   ├── services/
│   │   ├── auth.js          # USN + DOB + phone verification
│   │   ├── attendance.js
│   │   ├── cie.js           # CIE1-3, ACT1-2, aggregate calculator
│   │   ├── fees.js
│   │   ├── timetable.js
│   │   ├── certificates.js
│   │   └── rag.js           # Retrieval + LLM generation
│   ├── db/                  # PostgreSQL connection and queries
│   └── utils/               # Logger, message builders
├── assets/                  # Animated SVGs used in this README
├── data/                    # Mock data / CSV imports
├── .env.example
├── package.json
└── README.md
```

> 📌 Adjust the tree above to match your actual folder layout.

---

## 🚀 Getting Started

### Prerequisites

- Node.js 18+
- A PostgreSQL database (e.g. [Neon](https://neon.tech))
- A Meta developer account with WhatsApp Cloud API access
- A Groq API key
- [ngrok](https://ngrok.com) for local development

### 1. Clone and install

```bash
git clone https://github.com/LekhanaGowda07/ContXpert.git
cd ContXpert
npm install
```

### 2. Configure environment

Create a `.env` file:

```env
PORT=3000

# WhatsApp Cloud API
WHATSAPP_TOKEN=your_permanent_or_temporary_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WEBHOOK_VERIFY_TOKEN=any_secret_string_you_choose

# Database
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require

# LLM
GROQ_API_KEY=your_groq_api_key
```

### 3. Run the server

```bash
npm start
```

### 4. Expose it and connect WhatsApp

```bash
ngrok http 3000
```

In the Meta developer dashboard, set:

- **Callback URL:** `https://<your-ngrok-id>.ngrok-free.app/webhook`
- **Verify token:** the same value as `WEBHOOK_VERIFY_TOKEN`
- **Subscribed field:** `messages`

Then message your WhatsApp test number. 🎉

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

---|---|
| Lekhana | Developer |


*Computer Science and Engineering, Malnad College of Engineering, Hassan.*

---


<div align="center">

⭐ If you find this project useful, consider giving it a star!

</div>
