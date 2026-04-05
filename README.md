# 📚 StudyMate AI

> An AI-powered study assistant built with Flask and Google Gemini — deployed and live.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Gemini](https://img.shields.io/badge/Gemini_API-Google-4285F4?style=flat-square&logo=google&logoColor=white)](https://aistudio.google.com)
[![Deployed](https://img.shields.io/badge/Deployed-Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white)](https://railway.app)
[![Status](https://img.shields.io/badge/Status-Live-brightgreen?style=flat-square)]()

---

## What It Does

StudyMate AI is a web application that gives students an intelligent study companion powered by Google's Gemini LLM. Ask it to explain concepts, quiz you on material, summarise notes, or help you understand difficult topics — all through a clean, responsive web interface.

Built end-to-end: from the Flask backend and session management to frontend templating and production deployment on Railway.

**Live demo:** *(add your Railway URL here)*

---

## Features

- 🤖 **AI-powered Q&A** — Gemini-backed responses to any academic question
- 📝 **Note summarisation** — paste your notes and get a concise summary
- 🎯 **Concept explanation** — ask it to explain anything at multiple difficulty levels
- 🔐 **Session management** — per-user conversation context with Flask sessions
- 📱 **Responsive UI** — works on desktop and mobile
- ☁️ **Production deployed** — live on Railway with PostgreSQL

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python, Flask |
| AI / LLM | Google Gemini API |
| Database | SQLite (dev) → PostgreSQL (prod) |
| Frontend | HTML, CSS, JavaScript (Jinja2 templates) |
| Deployment | Railway |
| Config | python-dotenv, environment variables |

---

## Project Structure

```
8TH-SEM/
├── app.py              # Flask app, routes, Gemini API integration
├── migrate.py          # DB migration helper
├── templates/          # Jinja2 HTML templates
├── static/             # CSS, JS, assets
├── instance/           # SQLite DB (local only, gitignored)
├── requirements.txt
├── Procfile            # Railway/Heroku process config
├── runtime.txt         # Python version pin
├── .env.example        # Environment variable template
└── DEPLOY.md           # Deployment guide
```

---

## Local Setup

```bash
# 1. Clone
git clone https://github.com/priyanshiii7/8TH-SEM.git
cd 8TH-SEM

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — add your GEMINI_API_KEY (free at aistudio.google.com)

# 5. Initialise DB and run
python migrate.py
python app.py
```

App runs at `http://localhost:5000`

---

## Environment Variables

| Variable | Description | Where to Get |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key | [aistudio.google.com](https://aistudio.google.com) — free |
| `SECRET_KEY` | Flask session secret | Any random 50-char string |
| `DATABASE_URL` | PostgreSQL connection string | Auto-set by Railway |

---

## How It Works

```
User Input (browser)
      ↓
Flask Route (app.py)
      ↓
Session Context Retrieval
      ↓
Gemini API Call (Google Generative AI SDK)
      ↓
Response Parsed & Stored
      ↓
Rendered Template → User
```

---

**Built by [Priyanshi Rathore](https://linkedin.com/in/priyanshi-rathore-11b072217) · Bikaner, India**
