# StudyMate AI

## Local Development

1. Install dependencies:
   pip install -r requirements.txt

2. Create .env file:
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY

3. Run:
   python app.py

## Deploy to Railway (free)

1. Push to GitHub
2. Go to railway.app → New Project → Deploy from GitHub
3. Add environment variables:
   - GEMINI_API_KEY = your key from aistudio.google.com
   - SECRET_KEY = any random 50-char string
   - DATABASE_URL = (Railway auto-provides PostgreSQL if you add it)
4. Done — live in 2 minutes

## Environment Variables

| Variable | Description |
|----------|-------------|
| GEMINI_API_KEY | Get free at aistudio.google.com |
| SECRET_KEY | Random secret string for sessions |
| DATABASE_URL | Auto-set by Railway/Render |
