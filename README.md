# ⚕ HealthAssist

> An informational health document assistant that helps patients understand their medical records, match symptoms to possible conditions, track lab trends over time, and share summaries with their pharmacy — privately and securely.

**Not a medical device. Not a substitute for professional care.**

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development (without Docker)](#local-development-without-docker)
  - [Local Development (with Docker)](#local-development-with-docker)
- [Environment Variables](#environment-variables)
- [How It Works](#how-it-works)
  - [Two-Tower Retrieval](#two-tower-retrieval)
  - [RAG Chat Pipeline](#rag-chat-pipeline)
  - [Lab Value Extraction](#lab-value-extraction)
  - [Safety Layer](#safety-layer)
- [CI/CD](#cicd)
- [Deployment (Railway)](#deployment-railway)
- [Roadmap](#roadmap)
- [Disclaimer](#disclaimer)

---

## Overview

HealthAssist is a Flask-based MVP that allows users to:

1. Describe their symptoms via an intake form
2. Upload medical PDF documents (lab reports, referral letters)
3. Match symptoms to possible conditions using semantic similarity over 621 ICD-10 coded conditions
4. Chat with their documents using a local LLM (Ollama) with cited responses
5. Ask any general medical question — the pipeline intelligently switches between document-grounded and general-knowledge mode
6. Automatically extract and track lab values (HbA1c, cholesterol, creatinine, etc.) across sessions with trend charts
7. Log and summarise appointments via audio recording, PDF upload, or manual entry
8. Generate patient-friendly or pharmacy summaries as PDFs
9. Email the pharmacy summary directly to their saved pharmacy
10. Use the app in Hindi (हिंदी) with full UI and LLM response translation

All processing happens locally or within the user's own infrastructure. No health data is sent to third-party AI APIs.

---

## Features

| Feature | Details |
|---|---|
| **Auth** | Email + password, session-based, CSRF protected |
| **PDF Upload** | Extract and chunk text from medical PDFs |
| **Symptom Intake** | Structured form: age, sex, complaint, duration, medications, allergies |
| **Condition Matching** | Semantic two-tower retrieval over 621 ICD-10 coded conditions |
| **RAG Chat** | FAISS vector search + Ollama LLM synthesis with inline citations |
| **Two-mode RAG** | Document-grounded (cited) when relevant chunks found; general medical knowledge mode for broader questions |
| **Lab Value Extraction** | Automatic extraction of 40+ lab test types from uploaded PDFs via Ollama |
| **Lab Trend Charts** | Cross-session line charts per test (HbA1c, LDL, Creatinine, etc.) using Chart.js |
| **Appointment Memory** | Record, upload, or manually enter appointment notes; Ollama generates structured summaries + action plans |
| **Hindi Support** | Full UI translation + Ollama responds in Hindi when language toggled |
| **Safety Triage** | Emergency keyword detection across all inputs, site-wide banners |
| **Report Generation** | Patient summary + pharmacy summary PDFs via ReportLab |
| **Email Sharing** | One-click send to saved pharmacy via SMTP with explicit consent |
| **Audit Logging** | Every action logged: login, upload, consent, email, delete |
| **Delete Account** | Full data deletion including files from disk |
| **Dashboard** | Health summary stats, abnormal lab alerts, activity feed, session cards with inline lab snapshots |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│     Tailwind CSS + Vanilla JS + Chart.js (no framework)     │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────────┐
│                   Flask Application                         │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │   Auth   │  │ Sessions │  │  Intake  │  │  Upload   │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Retrieve │  │   RAG    │  │   Labs   │  │   Email   │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Reports  │  │  Appts   │  │   Lang   │  │ Settings  │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Safety Triage Layer                    │   │
│  └─────────────────────────────────────────────────────┘   │
└──────┬───────────────────┬──────────────────┬──────────────┘
       │                   │                  │
┌──────▼──────┐   ┌────────▼───────┐  ┌──────▼──────┐
│  PostgreSQL │   │ Sentence Trans │  │   Ollama    │
│  (via       │   │ (MiniLM-L6-v2) │  │ llama3.2:3b │
│  SQLAlchemy)│   │ + FAISS index  │  │ local LLM   │
└─────────────┘   └────────────────┘  └─────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Web framework** | Flask 3.0 |
| **Database** | PostgreSQL 16 (SQLite for local dev) |
| **ORM** | SQLAlchemy 2.0 + Flask-SQLAlchemy |
| **Migrations** | Flask-Migrate (Alembic) |
| **Auth** | Flask-Login + Werkzeug password hashing |
| **Forms / CSRF** | Flask-WTF |
| **Rate limiting** | Flask-Limiter |
| **Embeddings** | `sentence-transformers` (all-MiniLM-L6-v2, 384 dims) |
| **Vector search** | FAISS (faiss-cpu) |
| **Local LLM** | Ollama + llama3.2:3b |
| **PDF extraction** | PyMuPDF + pypdf |
| **PDF generation** | ReportLab |
| **Audio transcription** | faster-whisper (local) |
| **Charts** | Chart.js 4 (CDN) |
| **Internationalisation** | Flask-Babel (English + Hindi) |
| **Email** | Python smtplib (SMTP/TLS) |
| **Frontend** | Tailwind CSS CDN + Vanilla JS |
| **Production server** | Gunicorn |
| **Containerisation** | Docker + Docker Compose |
| **CI/CD** | GitHub Actions |
| **Deployment** | Railway |

---

## Project Structure

```
health-assistant/
│
├── app/
│   ├── __init__.py              # App factory
│   ├── config.py                # Config classes (dev/prod)
│   ├── extensions.py            # db, login_manager, csrf, limiter, babel
│   ├── models.py                # SQLAlchemy models (13 tables)
│   │
│   ├── auth/                    # Signup, login, logout
│   ├── sessions/                # Session CRUD, dashboard
│   ├── intake/                  # Symptom intake form
│   ├── upload/                  # PDF upload + extraction review
│   ├── retrieve/                # Two-tower condition matching
│   ├── rag/                     # FAISS vector store + RAG pipeline
│   ├── labs/                    # Lab value extraction + trend routes
│   ├── appointments/            # Appointment capture + Ollama summaries
│   ├── reports/                 # PDF report generation
│   ├── email/                   # Consent + SMTP sending
│   ├── settings/                # Pharmacy settings, delete account
│   ├── safety/                  # Emergency triage layer
│   ├── lang/                    # Language toggle (EN/HI) helpers
│   ├── history/                 # Session history view
│   ├── main/                    # Landing page
│   │
│   ├── templates/               # Jinja2 HTML templates
│   │   ├── labs/                # trends.html, session_labs.html
│   │   ├── appointments/        # list, detail, new
│   │   └── sessions/            # dashboard, detail, new_session
│   ├── static/css/custom.css    # Chat bubbles, match highlights
│   └── uploads/                 # Uploaded PDFs + generated reports
│
├── data/
│   ├── disease_catalog.csv      # Original 51 conditions
│   └── disease_catalog_v2.csv   # 621 ICD-10 conditions (enriched)
│
├── scripts/
│   ├── init_db.py               # Create all DB tables
│   ├── seed_disease_catalog.py  # Embed diseases + seed DB
│   ├── enrich_disease_catalog.py # Generate descriptions via Ollama (~20 min)
│   └── wait_for_db.py           # Docker: wait for Postgres
│
├── migrations/                  # Alembic migration versions
│   └── versions/
│       ├── 0001_initial_schema.py
│       ├── 0002_appointments.py
│       ├── 0003_preferred_language.py
│       └── 0004_lab_values.py
│
├── tests/
│   ├── conftest.py
│   └── test_smoke.py
│
├── .github/workflows/
│   ├── test.yml                 # Run on every push
│   └── deploy.yml               # Deploy on merge to main
│
├── Dockerfile
├── docker-compose.yml           # Local dev
├── docker-compose.prod.yml      # Production overrides
├── .dockerignore
├── .env.example
├── requirements.txt
└── run.py
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) installed and running
- (Optional) Docker + Docker Compose for containerised setup

### Local Development (without Docker)

```bash
# 1. Clone the repo
git clone https://github.com/your-username/health-assistant.git
cd health-assistant

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY at minimum

# 5. Start Ollama and pull the model
ollama serve
ollama pull llama3.2:3b

# 6. Run database migrations
flask db upgrade

# 7. Enrich and seed the disease catalog (621 conditions)
#    Step 1 — generate descriptions via Ollama (~20 min, resumable)
python scripts/enrich_disease_catalog.py
#    Step 2 — embed and seed into DB
python scripts/seed_disease_catalog.py

# 8. Run the development server
flask --app run:app run --debug

# Visit http://127.0.0.1:5000
```

### Local Development (with Docker)

```bash
# 1. Clone the repo
git clone https://github.com/your-username/health-assistant.git
cd health-assistant

# 2. Create Docker env file
cp .env.example .env.docker
# Edit .env.docker if needed (defaults work out of the box)

# 3. Build and start all services
#    First run downloads ~2GB (Ollama model) — be patient
docker compose up --build

# Visit http://localhost:8000

# Useful commands:
docker compose logs -f web        # App logs
docker compose logs -f ollama     # LLM logs
docker compose exec db psql -U healthuser -d healthassist  # DB shell
docker compose exec web pytest tests/ -v                   # Run tests
docker compose down               # Stop everything
docker compose down -v            # Stop + delete volumes (fresh start)
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | ✅ | — | Flask secret key — use a long random string in production |
| `DATABASE_URL` | — | `sqlite:///health.db` | Postgres connection string |
| `UPLOAD_FOLDER` | — | `app/uploads` | Where PDFs and reports are stored |
| `OLLAMA_BASE_URL` | — | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | — | `llama3.2:3b` | Ollama model name |
| `OLLAMA_TIMEOUT` | — | `60` | Seconds to wait for Ollama response |
| `GOOD_RETRIEVAL_THRESHOLD` | — | `0.25` | Score above which RAG answers from document; below uses general knowledge |
| `SMTP_HOST` | — | `smtp.gmail.com` | SMTP server for email sending |
| `SMTP_PORT` | — | `587` | SMTP port |
| `SMTP_USER` | — | — | SMTP username (your Gmail address) |
| `SMTP_PASSWORD` | — | — | Gmail App Password (not your Gmail password) |
| `SMTP_FROM` | — | `SMTP_USER` | From address shown in emails |
| `FLASK_ENV` | — | `development` | Set to `production` in prod |

**Generate a strong SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Gmail App Password setup:**
1. Enable 2-Step Verification on your Google account
2. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
3. Search "App passwords" → Create → Copy the 16-character password
4. Use that as `SMTP_PASSWORD` (no spaces)

---

## How It Works

### Two-Tower Retrieval

Condition matching uses a semantic two-tower architecture over **621 ICD-10 coded conditions** spanning 16 chapters:

```
Patient intake text          Disease descriptions (621 conditions)
        ↓                               ↓
  sentence-transformers          sentence-transformers
  (all-MiniLM-L6-v2)            (all-MiniLM-L6-v2, 384 dims)
        ↓                               ↓
   Query vector              Disease vectors (stored in DB)
        └──────── cosine similarity ────┘
                        ↓
                   Top-10 ranked matches
                        ↓
              Explainability layer
         (per-field contributions + matched terms)
```

Unlike TF-IDF, sentence transformers encode **meaning** — so "chest pressure" correctly matches "myocardial discomfort" even with no shared words.

### RAG Chat Pipeline

The pipeline operates in two modes depending on how well the patient's question matches their uploaded documents:

```
User question
      ↓
Safety check (emergency keyword detection)
      ↓
Sentence transformer → query vector
      ↓
FAISS search over confirmed document chunks
      ↓
Score check (GOOD_RETRIEVAL_THRESHOLD = 0.25)
      ↓
  ┌──────────────────────┬──────────────────────────┐
  │   score >= 0.25      │     score < 0.25         │
  │   DOC-GROUNDED       │   GENERAL KNOWLEDGE      │
  │                      │                          │
  │  Answer from chunks  │  Answer from Ollama      │
  │  Cite with [1][2][3] │  general medical         │
  │                      │  knowledge; document     │
  │  Citations shown     │  used as context only    │
  │                      │  No citations shown      │
  └──────────────────────┴──────────────────────────┘
```

This means patients can ask both specific questions ("what was my creatinine?") and general questions ("what does high creatinine mean?") and get useful answers in both cases.

### Lab Value Extraction

When a patient confirms their uploaded PDF text, lab values are automatically extracted in the background:

```
Confirmed document chunks
        ↓
Ollama (structured JSON extraction prompt)
        ↓  (fallback if Ollama offline)
Regex pattern matcher
        ↓
Normalisation (40+ canonical names: HbA1c, LDL, Creatinine, TSH…)
        ↓
lab_values table
(user_id, session_id, test_name, value, unit,
 reference_range, status, report_date)
        ↓
/labs/trends — Chart.js cross-session line graphs
```

Supported categories: Blood Sugar, Lipids, Kidney, Liver, Blood Count, Thyroid, Vitamins, Electrolytes, Inflammatory markers.

Status (High / Normal / Low) is extracted from the report and used to colour-code chart lines and surface alerts on the dashboard.

### Safety Layer

Emergency keywords are checked at three points:

| Where | What is checked |
|---|---|
| Intake form | Chief complaint, duration, additional notes |
| Chat input | Every user message before RAG runs |
| Chat response | If triggered: emergency message returned, no RAG |

Trigger categories: `cardiac`, `stroke`, `respiratory`, `mental_health_crisis`, `severe_allergic`, `unconscious`

When triggered:
- Session `safety_flagged` is set to `1`
- Red emergency banner shown site-wide
- Pharmacy report email disabled for that session
- Audit log entry created

---

## CI/CD

Every push runs the test pipeline. Merges to `main` trigger deployment.

```
Push to any branch
        ↓
  GitHub Actions: test.yml
  ├── flake8 lint
  ├── Postgres service (ephemeral)
  ├── DB migrations (flask db upgrade)
  ├── Disease catalog seed
  └── pytest smoke tests

Merge to main
        ↓
  GitHub Actions: deploy.yml
  ├── Build Docker image
  ├── Push to ghcr.io/<repo>:latest
  └── Trigger Railway webhook → redeploy
```

**Required GitHub Secrets:**

| Secret | Where to get it |
|---|---|
| `GITHUB_TOKEN` | Automatic — provided by GitHub Actions |
| `RAILWAY_DEPLOY_WEBHOOK` | Railway project → Settings → Deploy Webhook |

---

## Deployment (Railway)

```bash
# 1. Push to GitHub
git push origin main

# 2. Railway setup (one time)
#    railway.app → New Project → Deploy from GitHub repo
#    Add PostgreSQL plugin → DATABASE_URL auto-set

# 3. Set environment variables in Railway dashboard:
SECRET_KEY=<generated>
FLASK_ENV=production
UPLOAD_FOLDER=app/uploads
OLLAMA_BASE_URL=<your ollama host>
GOOD_RETRIEVAL_THRESHOLD=0.25
SMTP_USER=...
SMTP_PASSWORD=...

# 4. Add deploy webhook to GitHub secrets:
#    RAILWAY_DEPLOY_WEBHOOK = <from Railway → Settings → Deploy Webhook>

# Every merge to main now auto-deploys.
```

> **Note on Ollama:** Railway's free tier (512MB RAM) cannot run Ollama. The app falls back to structured extraction when Ollama is unreachable. For full LLM answers in production, point `OLLAMA_BASE_URL` to a separate VPS running Ollama (minimum 4GB RAM for llama3.2:3b).

---

## Roadmap

- [ ] **Redis for Flask-Limiter** — replace in-memory rate limit storage warning
- [ ] **Doctor visit prep** — auto-generate "what to tell your doctor" one-pager before appointments
- [ ] **Follow-up question suggestions** — suggest 3 doctor questions after each RAG response
- [ ] **Async extraction** — Celery + Redis for background PDF processing
- [ ] **Better LLM** — swap llama3.2:3b for a medical-tuned model (MedLlama, OpenBioLLM)
- [ ] **HIPAA considerations** — encryption at rest, audit log export, BAA
- [ ] **Admin dashboard** — usage stats, safety alert monitoring
- [ ] **Mobile app** — React Native wrapper over the existing API

---

## Disclaimer

HealthAssist is an **informational tool only**.

- It is **not a medical device**
- It does **not provide diagnoses**
- It does **not replace professional medical advice**
- All condition matching results are based on **semantic similarity only**
- Lab value extraction is automated and may not be 100% accurate — always verify against your original report
- Always consult a qualified healthcare professional before making any health decisions

In an emergency, call **911 (US) / 999 (UK) / 112 (EU)** immediately.

---

*Built with Flask, PostgreSQL, sentence-transformers, FAISS, Ollama, faster-whisper, Chart.js, Flask-Babel, ReportLab, and Docker.*