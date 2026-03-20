# Deploy StudyMate to Railway (Free)

## Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "StudyMate AI - initial commit"
```
Create a repo on github.com, then:
```bash
git remote add origin https://github.com/YOUR_USERNAME/studymate.git
git push -u origin main
```

## Step 2 — Deploy on Railway (Free tier)
1. Go to railway.app → Login with GitHub
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your studymate repo
4. Railway auto-detects Python and deploys

## Step 3 — Set Environment Variables on Railway
In your Railway project → Variables tab, add:
```
GEMINI_API_KEY = AIza...your_key_here
SECRET_KEY     = any-random-string-here
```

## Step 4 — Add PostgreSQL (Free on Railway)
1. In Railway project → "New" → "Database" → "PostgreSQL"
2. Railway auto-sets DATABASE_URL — your app picks it up automatically

## That's it! Your app is live.

---

## Alternative: Render.com (also free)
1. render.com → New → Web Service → Connect GitHub
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `gunicorn app:app`
4. Add same environment variables

---

## Local Development
```bash
pip install -r requirements.txt
# Edit .env file with your GEMINI_API_KEY
python app.py
```
