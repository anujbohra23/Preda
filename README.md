# ⚕ HealthAssist MVP

> An informational health document assistant that helps patients understand their medical records, match symptoms to possible conditions, and share summaries with their pharmacy — privately and securely.

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
3. Match symptoms to possible conditions using semantic similarity
4. Chat with their documents using a local LLM (Ollama) with cited responses
5. Generate patient-friendly or pharmacy summaries as PDFs
6. Email the pharmacy summary directly to their saved pharmacy

All processing happens locally or within the user's own infrastructure. No health data is sent to third-party AI APIs.

---

## Features

| Feature | Details |
|---|---|
| **Auth** | Email + password, session-based, CSRF protected |
| **PDF Upload** | Extract and chunk text from medical PDFs |
| **Symptom Intake** | Structured form: age, sex, complaint, duration, medications, allergies |
| **Condition Matching** | Semantic two-tower retrieval over 50+ ICD-coded conditions |
| **RAG Chat** | FAISS vector search + Ollama LLM synthesis with inline citations |
| **Safety Triage** | Emergency keyword detection across all inputs, site-wide banners |
| **Report Generation** | Patient summary + pharmacy summary PDFs via ReportLab |
| **Email Sharing** | One-click send to saved pharmacy via SMTP with explicit consent |
| **Audit Logging** | Every action logged: login, upload, consent, email, delete |
| **Delete Account** | Full data deletion including files from disk |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│          Tailwind CSS + Vanilla JS (no framework)           │
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
│  │ Retrieve │  │   RAG    │  │ Reports  │  │   Email   │  │
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
| **Auth** | Flask-Login + Werkzeug password hashing |
| **Forms / CSRF** | Flask-WTF |
| **Rate limiting** | Flask-Limiter |
| **Embeddings** | `sentence-transformers` (all-MiniLM-L6-v2) |
| **Vector search** | FAISS (faiss-cpu) |
| **Local LLM** | Ollama + llama3.2:3b |
| **PDF extraction** | PyMuPDF + pypdf |
| **PDF generation** | ReportLab |
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
│   ├── extensions.py            # db, login_manager, csrf, limiter
│   ├── models.py                # SQLAlchemy models (11 tables)
│   │
│   ├── auth/                    # Signup, login, logout
│   ├── sessions/                # Session CRUD, dashboard
│   ├── intake/                  # Symptom intake form
│   ├── upload/                  # PDF upload + extraction review
│   ├── retrieve/                # Two-tower condition matching
│   ├── rag/                     # FAISS vector store + RAG pipeline
│   ├── reports/                 # PDF report generation
│   ├── email/                   # Consent + SMTP sending
│   ├── settings/                # Pharmacy settings, delete account
│   ├── safety/                  # Emergency triage layer
│   ├── history/                 # Session history view
│   ├── main/                    # Landing page
│   │
│   ├── templates/               # Jinja2 HTML templates
│   ├── static/css/custom.css    # Chat bubbles, match highlights
│   └── uploads/                 # Uploaded PDFs + generated reports
│
├── data/
│   └── disease_catalog.csv      # 50+ ICD-coded conditions
│
├── scripts/
│   ├── init_db.py               # Create all DB tables
│   ├── seed_disease_catalog.py  # Embed diseases + seed DB
│   └── wait_for_db.py           # Docker: wait for Postgres
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

# 6. Initialise the database
python scripts/init_db.py

# 7. Seed the disease catalog
#    Downloads sentence transformer model (~80MB) on first run
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
docker-compose up --build

# Visit http://localhost:8000

# Useful commands:
docker-compose logs -f web        # App logs
docker-compose logs -f ollama     # LLM logs
docker-compose exec db psql -U healthuser -d healthassist  # DB shell
docker-compose exec web pytest tests/ -v                   # Run tests
docker-compose down               # Stop everything
docker-compose down -v            # Stop + delete volumes (fresh start)
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
| `MIN_RETRIEVAL_SCORE` | — | `0.05` | Minimum FAISS score to return a RAG answer |
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

Condition matching uses a semantic two-tower architecture:

```
Patient intake text          Disease descriptions (50+ conditions)
        ↓                               ↓
  sentence-transformers          sentence-transformers
  (all-MiniLM-L6-v2)            (all-MiniLM-L6-v2)
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

The embedding function is isolated in `app/twotower/retrieval.py` behind a single `_embed()` function — swap it for any other model without touching the pipeline.

### RAG Chat Pipeline

```
User question
      ↓
Safety check (emergency keyword detection)
      ↓
Sentence transformer → query vector
      ↓
FAISS search over confirmed document chunks
      ↓
Citation-required policy (min score threshold)
      ↓
Top-N chunks → Ollama (llama3.2:3b) with strict system prompt
      ↓
Synthesized answer with [1][2][3] inline citations
      ↓
Citations saved to DB (RagRetrieval table)
```

The system prompt strictly instructs the LLM to answer **only** from provided chunks and cite every claim. If no relevant chunks are found, the response is always "I don't know based on the available documents."

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
  ├── DB init + disease catalog seed
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
OLLAMA_BASE_URL=<your ollama host or leave blank for fallback>
MIN_RETRIEVAL_SCORE=0.05
SMTP_USER=...
SMTP_PASSWORD=...

# 4. Add deploy webhook to GitHub secrets:
#    RAILWAY_DEPLOY_WEBHOOK = <from Railway → Settings → Deploy Webhook>

# Every merge to main now auto-deploys.
```

> **Note on Ollama:** Railway's free tier (512MB RAM) cannot run Ollama. The app falls back to structured extraction when Ollama is unreachable. For full LLM answers in production, point `OLLAMA_BASE_URL` to a separate VPS running Ollama (minimum 4GB RAM).

---

## Roadmap

- [ ] **PostgreSQL optimisations** — connection pooling, Flask-Migrate for schema migrations
- [ ] **Ollama hosting** — dedicated VPS or Modal.com serverless inference
- [ ] **Better LLM** — swap llama3.2:3b for a medical-tuned model (MedLlama, OpenBioLLM)
- [ ] **Multi-document sessions** — upload multiple PDFs per session
- [ ] **Async extraction** — Celery + Redis for background PDF processing
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
- Always consult a qualified healthcare professional before making any health decisions

In an emergency, call **911 (US) / 999 (UK) / 112 (EU)** immediately.

---

*Built with Flask, PostgreSQL, sentence-transformers, FAISS, Ollama, ReportLab, and Docker.*