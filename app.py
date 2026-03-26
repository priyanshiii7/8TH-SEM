from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
import secrets
import hashlib

# Load .env file in development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── Server-side API key (never exposed to browser) ──────────────────────────
# Set this in your .env file or Railway/Render environment variables
# GEMINI_API_KEY=your_key_here
SERVER_API_KEY = os.environ.get('GEMINI_API_KEY', '')

# ─── Google OAuth ─────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID     = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_AUTH_URL      = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL     = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL  = 'https://www.googleapis.com/oauth2/v3/userinfo'

# ─── Server-side API key — set in environment, never exposed to users ─────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'studymate-secret-2024-change-in-prod')
# Use PostgreSQL in production (Railway/Render), SQLite locally
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///studymate.db')
# Railway gives postgres:// but SQLAlchemy needs postgresql://
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ─── Models ───────────────────────────────────────────────────────────────────

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    avatar_color = db.Column(db.String(20), default='#6C63FF')
    avatar_b64 = db.Column(db.Text, nullable=True)
    google_id  = db.Column(db.String(100), nullable=True, unique=True)
    auth_type  = db.Column(db.String(20), default='email')  # 'email' or 'google'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subjects = db.relationship('Subject', backref='user', lazy=True, cascade='all, delete-orphan')
    tasks = db.relationship('Task', backref='user', lazy=True, cascade='all, delete-orphan')
    focus_sessions = db.relationship('FocusSession', backref='user', lazy=True, cascade='all, delete-orphan')
    journal_entries = db.relationship('JournalEntry', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(20), default='#6C63FF')
    target_hours = db.Column(db.Float, default=10.0)
    studied_hours = db.Column(db.Float, default=0.0)
    exam_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    priority = db.Column(db.String(20), default='medium')
    due_date = db.Column(db.Date, nullable=True)
    completed = db.Column(db.Boolean, default=False)
    ai_generated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FocusSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False)
    session_date = db.Column(db.Date, default=date.today)
    note = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    ai_reflection = db.Column(db.Text, nullable=True)
    mood = db.Column(db.String(20), default='neutral')
    entry_date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ─── Gemini AI Helper ─────────────────────────────────────────────────────────

def call_ai(api_key_ignored, prompt, system_prompt=None):
    """
    Calls AI using the server-side GEMINI_API_KEY environment variable.
    The api_key parameter is ignored — key is never sent to or stored by clients.
    """
    if not GEMINI_API_KEY:
        raise Exception("AI not configured. Set GEMINI_API_KEY environment variable on the server.")
    return _call_ai(GEMINI_API_KEY, prompt, system_prompt)

def _call_openrouter(api_key, prompt, system_prompt=None):
    """OpenRouter - free tier at openrouter.ai, no credit card needed"""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Free models on OpenRouter — tries each until one works
    free_models = [
        "meta-llama/llama-3.2-3b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "google/gemma-2-9b-it:free",
        "microsoft/phi-3-mini-128k-instruct:free",
        "qwen/qwen-2-7b-instruct:free",
    ]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "StudyMate AI"
    }

    last_err = "No free models available"
    for model in free_models:
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7
        }).encode('utf-8')
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload, headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return result['choices'][0]['message']['content']
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code in (401, 403):
                raise Exception("Invalid OpenRouter key. Get a free one at openrouter.ai")
            last_err = f"{model.split('/')[1]}: {e.code}"
            continue
        except Exception as e:
            last_err = str(e)
            continue
    raise Exception(f"All OpenRouter free models failed. Last: {last_err}. Try adding credits at openrouter.ai")

def _call_anthropic(api_key, prompt, system_prompt=None):
    """Anthropic Claude API"""
    messages = [{"role": "user", "content": prompt}]
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "messages": messages
    }
    if system_prompt:
        body["system"] = system_prompt
    
    payload = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result['content'][0]['text']
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code in (401, 403):
            raise Exception("Invalid Anthropic key. Get one at console.anthropic.com")
        raise Exception(f"Anthropic error {e.code}: {body[:200]}")

def _call_ai(api_key, prompt, system_prompt=None):
    """Google Gemini API"""
    full_prompt = (system_prompt + "\n\n" + prompt) if system_prompt else prompt
    payload = json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"maxOutputTokens": 600, "temperature": 0.7}
    }).encode('utf-8')

    # Only models confirmed available for this key
    candidates = [
        ("v1beta", "gemini-2.0-flash"),
        ("v1beta", "gemini-2.0-flash-lite"),
        ("v1beta", "gemini-2.5-flash"),
        ("v1beta", "gemini-flash-latest"),
    ]
    last_err = "No Gemini models available"
    for version, model in candidates:
        url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                result = json.loads(resp.read().decode())
                return result['candidates'][0]['content']['parts'][0]['text']
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code in (401, 403):
                raise Exception("Invalid Gemini key. Get a free one at aistudio.google.com")
            if e.code == 429:
                import time
                time.sleep(5)
                try:
                    with urllib.request.urlopen(req, timeout=25) as resp2:
                        result = json.loads(resp2.read().decode())
                        return result['candidates'][0]['content']['parts'][0]['text']
                except:
                    last_err = f"{model} rate limited (429) — wait 60s and retry"
                    continue
            if e.code == 400:
                raise Exception(f"Gemini bad request: {body[:200]}")
            last_err = f"{model}({e.code})"
            continue
        except Exception as e:
            last_err = str(e)
            continue
    raise Exception(f"Gemini failed: {last_err}")

# ─── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        user = User.query.filter_by(email=data['email']).first()
        if user and check_password_hash(user.password, data['password']):
            session['user_id'] = user.id
            session['user_name'] = user.name
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid email or password'})
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'success': False, 'error': 'Email already registered'})
        import random
        colors = ['#7C6FF7','#F87171','#4ADE80','#22D3EE','#FCD34D','#F472B6','#A78BFA','#34D399']
        user = User(
            name=data['name'],
            email=data['email'],
            password=generate_password_hash(data['password']),
            avatar_color=random.choice(colors)
        )
        db.session.add(user)
        db.session.flush()
        for i, subj in enumerate(data.get('subjects', [])):
            name = subj.get('name', '').strip()
            if not name:
                continue
            s = Subject(
                user_id=user.id,
                name=name,
                color=colors[i % len(colors)],
                target_hours=float(subj.get('target_hours', 20)),
                exam_date=datetime.strptime(subj['exam_date'], '%Y-%m-%d').date() if subj.get('exam_date') else None
            )
            db.session.add(s)
        db.session.commit()
        session['user_id'] = user.id
        session['user_name'] = user.name
        return jsonify({'success': True})
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Google OAuth Routes ──────────────────────────────────────────────────────

@app.route('/auth/google')
def google_login():
    if not GOOGLE_CLIENT_ID:
        return redirect(url_for('login') + '?error=oauth_not_configured')
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    base_url = os.environ.get('APP_URL', 'http://localhost:5000')
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': f"{base_url}/auth/callback",
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'access_type': 'online',
    }
    url = GOOGLE_AUTH_URL + '?' + urllib.parse.urlencode(params)
    return redirect(url)


@app.route('/auth/callback')
def google_callback():
    error = request.args.get('error')
    if error:
        return redirect(url_for('login') + '?error=' + error)
    state = request.args.get('state')
    if state != session.pop('oauth_state', None):
        return redirect(url_for('login') + '?error=invalid_state')
    code = request.args.get('code')
    if not code:
        return redirect(url_for('login') + '?error=no_code')
    base_url = os.environ.get('APP_URL', 'http://localhost:5000')
    redirect_uri = f"{base_url}/auth/callback"
    token_data = urllib.parse.urlencode({
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }).encode('utf-8')
    try:
        token_req = urllib.request.Request(
            GOOGLE_TOKEN_URL, data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        with urllib.request.urlopen(token_req, timeout=10) as resp:
            tokens = json.loads(resp.read().decode())
    except Exception as e:
        return redirect(url_for('login') + '?error=token_failed')
    access_token = tokens.get('access_token')
    if not access_token:
        return redirect(url_for('login') + '?error=no_token')
    try:
        info_req = urllib.request.Request(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'}
        )
        with urllib.request.urlopen(info_req, timeout=10) as resp:
            user_info = json.loads(resp.read().decode())
    except Exception:
        return redirect(url_for('login') + '?error=userinfo_failed')
    google_id = user_info.get('sub')
    email     = user_info.get('email')
    name      = user_info.get('name', email.split('@')[0] if email else 'User')
    picture   = user_info.get('picture', '')
    if not google_id or not email:
        return redirect(url_for('login') + '?error=missing_info')
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        existing = User.query.filter_by(email=email).first()
        if existing:
            existing.google_id = google_id
            existing.auth_type = 'google'
            db.session.commit()
            user = existing
        else:
            import random, base64
            colors = ['#5B7FFF','#F87171','#4ADE80','#38BDF8','#818CF8','#F472B6','#A78BFA','#34D399']
            user = User(
                name=name, email=email,
                password=generate_password_hash(secrets.token_hex(32)),
                avatar_color=random.choice(colors),
                google_id=google_id, auth_type='google'
            )
            if picture:
                try:
                    pic_req = urllib.request.Request(picture)
                    with urllib.request.urlopen(pic_req, timeout=5) as pr:
                        pic_data = base64.b64encode(pr.read()).decode()
                        user.avatar_b64 = f"data:image/jpeg;base64,{pic_data}"
                except:
                    pass
            db.session.add(user)
            db.session.commit()
    session['user_id']   = user.id
    session['user_name'] = user.name
    return redirect(url_for('dashboard'))

# ─── Page Routes ──────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/planner')
@login_required
def planner():
    return render_template('planner.html')

@app.route('/focus')
@login_required
def focus():
    return render_template('focus.html')

@app.route('/journal')
@login_required
def journal():
    return render_template('journal.html')

@app.route('/tutor')
@login_required
def tutor():
    return render_template('tutor.html')

@app.route('/progress')
@login_required
def progress():
    return render_template('progress.html')

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

# ─── API: User Stats ──────────────────────────────────────────────────────────

@app.route('/api/user/stats')
@login_required
def user_stats():
    uid = session['user_id']
    user = db.session.get(User, uid)
    today = date.today()
    week_ago = today - timedelta(days=7)

    total_focus = db.session.query(db.func.sum(FocusSession.duration_minutes))\
        .filter_by(user_id=uid).scalar() or 0
    week_focus = db.session.query(db.func.sum(FocusSession.duration_minutes))\
        .filter(FocusSession.user_id == uid, FocusSession.session_date >= week_ago).scalar() or 0
    tasks_done = Task.query.filter_by(user_id=uid, completed=True).count()
    tasks_total = Task.query.filter_by(user_id=uid).count()
    subjects = Subject.query.filter_by(user_id=uid).all()

    streak = 0
    check_date = today
    while True:
        has_session = FocusSession.query.filter_by(user_id=uid, session_date=check_date).first()
        if has_session:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    daily_focus = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        mins = db.session.query(db.func.sum(FocusSession.duration_minutes))\
            .filter(FocusSession.user_id == uid, FocusSession.session_date == d).scalar() or 0
        daily_focus.append({'date': d.strftime('%a'), 'minutes': mins})

    recent_tasks = Task.query.filter_by(user_id=uid, completed=False)\
        .order_by(Task.created_at.desc()).limit(5).all()

    return jsonify({
        'name': user.name,
        'avatar_color': user.avatar_color,
        'avatar_b64': user.avatar_b64 or '',
        'total_focus_hours': round(total_focus / 60, 1),
        'week_focus_hours': round(week_focus / 60, 1),
        'tasks_done': tasks_done,
        'tasks_total': tasks_total,
        'streak': streak,
        'subjects_count': len(subjects),
        'daily_focus': daily_focus,
        'recent_tasks': [{'id': t.id, 'title': t.title, 'priority': t.priority, 'completed': t.completed} for t in recent_tasks],
        'subjects': [{'name': s.name, 'color': s.color, 'studied': s.studied_hours, 'target': s.target_hours} for s in subjects]
    })

# ─── API: Tasks ───────────────────────────────────────────────────────────────

@app.route('/api/tasks', methods=['GET'])
@login_required
def get_tasks():
    uid = session['user_id']
    tasks = Task.query.filter_by(user_id=uid).order_by(Task.created_at.desc()).all()
    subjects = {s.id: s.name for s in Subject.query.filter_by(user_id=uid).all()}
    return jsonify([{
        'id': t.id, 'title': t.title, 'priority': t.priority,
        'completed': t.completed, 'ai_generated': t.ai_generated,
        'subject': subjects.get(t.subject_id, 'General'),
        'due_date': t.due_date.strftime('%Y-%m-%d') if t.due_date else None
    } for t in tasks])

@app.route('/api/tasks', methods=['POST'])
@login_required
def add_task():
    data = request.get_json()
    task = Task(
        user_id=session['user_id'],
        title=data['title'],
        priority=data.get('priority', 'medium'),
        subject_id=data.get('subject_id') or None,
        due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None
    )
    db.session.add(task)
    db.session.commit()
    return jsonify({'success': True, 'id': task.id})

@app.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=session['user_id']).first_or_404()
    task.completed = not task.completed
    db.session.commit()
    return jsonify({'success': True, 'completed': task.completed})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=session['user_id']).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True})

# ─── API: Subjects ────────────────────────────────────────────────────────────

@app.route('/api/subjects', methods=['GET'])
@login_required
def get_subjects():
    subjects = Subject.query.filter_by(user_id=session['user_id']).all()
    return jsonify([{
        'id': s.id, 'name': s.name, 'color': s.color,
        'target_hours': s.target_hours, 'studied_hours': s.studied_hours,
        'exam_date': s.exam_date.strftime('%Y-%m-%d') if s.exam_date else None
    } for s in subjects])

@app.route('/api/subjects', methods=['POST'])
@login_required
def add_subject():
    data = request.get_json()
    subject = Subject(
        user_id=session['user_id'],
        name=data['name'],
        color=data.get('color', '#6C63FF'),
        target_hours=float(data.get('target_hours', 10)),
        exam_date=datetime.strptime(data['exam_date'], '%Y-%m-%d').date() if data.get('exam_date') else None
    )
    db.session.add(subject)
    db.session.commit()
    return jsonify({'success': True, 'id': subject.id})

# ─── API: Focus ───────────────────────────────────────────────────────────────

@app.route('/api/focus', methods=['POST'])
@login_required
def log_focus():
    data = request.get_json()
    uid = session['user_id']
    mins = int(data.get('duration_minutes', 0))
    if mins < 1:
        return jsonify({'success': False, 'error': 'Too short'})
    fs = FocusSession(
        user_id=uid,
        subject_id=data.get('subject_id') or None,
        duration_minutes=mins,
        note=data.get('note', 'Focus Timer')
    )
    db.session.add(fs)
    if data.get('subject_id'):
        subj = Subject.query.filter_by(id=data['subject_id'], user_id=uid).first()
        if subj:
            subj.studied_hours = round(subj.studied_hours + mins / 60, 2)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/focus_beacon')
@login_required
def focus_beacon():
    try:
        mins = int(request.args.get('uid', 0))
        sid = request.args.get('sid', '') or None
        uid = session['user_id']
        if mins >= 1:
            fs = FocusSession(user_id=uid, subject_id=sid, duration_minutes=mins, note='Focus Timer (partial)')
            db.session.add(fs)
            if sid:
                subj = Subject.query.filter_by(id=sid, user_id=uid).first()
                if subj:
                    subj.studied_hours = round(subj.studied_hours + mins / 60, 2)
            db.session.commit()
    except:
        pass
    return '', 204

@app.route('/api/focus/history')
@login_required
def focus_history():
    uid = session['user_id']
    today = date.today()
    sessions = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        mins = db.session.query(db.func.sum(FocusSession.duration_minutes))\
            .filter(FocusSession.user_id == uid, FocusSession.session_date == d).scalar() or 0
        sessions.append({'date': d.strftime('%Y-%m-%d'), 'minutes': mins})
    return jsonify(sessions)

# ─── API: Manual Study Log ────────────────────────────────────────────────────

@app.route('/api/study/manual-log', methods=['POST'])
@login_required
def manual_log():
    data = request.get_json()
    uid = session['user_id']
    mins = int(data.get('minutes', 0))
    if mins < 1:
        return jsonify({'success': False, 'error': 'Enter at least 1 minute'})
    study_date = date.today()
    if data.get('study_date'):
        try:
            study_date = datetime.strptime(data['study_date'], '%Y-%m-%d').date()
        except:
            pass
    fs = FocusSession(
        user_id=uid,
        subject_id=data.get('subject_id') or None,
        duration_minutes=mins,
        session_date=study_date,
        note=data.get('note', 'Manual Log')
    )
    db.session.add(fs)
    if data.get('subject_id'):
        subj = Subject.query.filter_by(id=data['subject_id'], user_id=uid).first()
        if subj:
            subj.studied_hours = round(subj.studied_hours + mins / 60, 2)
    db.session.commit()
    return jsonify({'success': True})

# ─── API: Journal ─────────────────────────────────────────────────────────────

@app.route('/api/journal', methods=['GET'])
@login_required
def get_journal():
    entries = JournalEntry.query.filter_by(user_id=session['user_id'])\
        .order_by(JournalEntry.created_at.desc()).limit(20).all()
    return jsonify([{
        'id': e.id, 'content': e.content, 'ai_reflection': e.ai_reflection,
        'mood': e.mood, 'date': e.entry_date.strftime('%B %d, %Y')
    } for e in entries])

@app.route('/api/journal', methods=['POST'])
@login_required
def save_journal():
    data = request.get_json()
    uid = session['user_id']
    ai_reflection = None
    if GEMINI_API_KEY:
        try:
            ai_reflection = call_ai(
                api_key,
                f"A student wrote this journal entry: '{data['content']}'\n\nWrite a warm 2-3 sentence reflection. Acknowledge feelings, highlight something positive, give one actionable insight for tomorrow. Be genuine not generic."
            )
        except:
            ai_reflection = "Keep pushing — every session counts. Consistency beats perfection."
    entry = JournalEntry(
        user_id=uid,
        content=data['content'],
        ai_reflection=ai_reflection,
        mood=data.get('mood', 'neutral')
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'ai_reflection': ai_reflection})

# ─── API: Profile ─────────────────────────────────────────────────────────────

@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    uid = session['user_id']
    user = db.session.get(User, uid)
    subjects = Subject.query.filter_by(user_id=uid).all()
    return jsonify({
        'name': user.name,
        'email': user.email,
        'avatar_color': user.avatar_color,
        'avatar_b64': user.avatar_b64 or '',
        'member_since': user.created_at.strftime('%B %Y'),
        'subjects': [{
            'id': s.id, 'name': s.name, 'color': s.color,
            'target_hours': s.target_hours, 'studied_hours': s.studied_hours,
            'exam_date': s.exam_date.strftime('%Y-%m-%d') if s.exam_date else None
        } for s in subjects]
    })

@app.route('/api/profile', methods=['POST'])
@login_required
def update_profile():
    data = request.get_json()
    uid = session['user_id']
    user = db.session.get(User, uid)
    if data.get('name'):
        user.name = data['name']
        session['user_name'] = data['name']
    if data.get('avatar_color'):
        user.avatar_color = data['avatar_color']
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/profile/picture', methods=['POST'])
@login_required
def upload_picture():
    data = request.get_json()
    uid = session['user_id']
    b64 = data.get('image_b64', '')
    if not b64 or len(b64) > 2_000_000:
        return jsonify({'success': False, 'error': 'Image too large (max 1.5MB)'})
    user = db.session.get(User, uid)
    user.avatar_b64 = b64
    db.session.commit()
    return jsonify({'success': True})

# ─── API: AI ──────────────────────────────────────────────────────────────────

@app.route('/api/ai/generate-plan', methods=['POST'])
@login_required
def generate_plan():
    data = request.get_json()
    uid = session['user_id']
    subjects = Subject.query.filter_by(user_id=uid).all()
    context = data.get('context', 'Generate a study plan for today')
    today_str = date.today().strftime('%B %d, %Y')

    subject_info = "\n".join([
        f"- {s.name}: studied {s.studied_hours}h of {s.target_hours}h target"
        + (f", exam on {s.exam_date}" if s.exam_date else "")
        for s in subjects
    ]) or "No subjects added yet"

    pending_tasks = Task.query.filter_by(user_id=uid, completed=False).count()

    if not GEMINI_API_KEY:
        subject_name = subjects[0].name if subjects else 'your subject'
        day_match = re.search(r'(\d+)\s*days?', context.lower())
        days = int(day_match.group(1)) if day_match else None
        if days and days > 1:
            plan = [
                {"title": f"Day 1-{max(1,days//3)}: Study core concepts and theory of {subject_name}", "priority": "high"},
                {"title": f"Day {max(2,days//3+1)}-{max(2,days*2//3)}: Work through past papers and practice problems", "priority": "high"},
                {"title": f"Day {max(3,days*2//3+1)}-{max(3,days-1)}: Target weak areas and fill gaps", "priority": "medium"},
                {"title": f"Day {days}: Final revision — notes, flashcards, key formulas only", "priority": "medium"},
                {"title": "Night before exam: 8 hours sleep — brain consolidates memory during sleep", "priority": "low"},
            ]
        else:
            plan = [
                {"title": f"Read through {subject_name} lecture notes from last session", "priority": "high"},
                {"title": f"Solve 10 practice problems on {subject_name} — timed", "priority": "high"},
                {"title": "Review starred or difficult topics", "priority": "medium"},
                {"title": "Create a one-page summary of key concepts", "priority": "medium"},
                {"title": "Watch a supplementary video or re-read a confusing section", "priority": "low"},
            ]
        return jsonify({'success': True, 'tasks': plan, 'note': 'AI not configured on server'})

    try:
        prompt = f"""You are a smart study coach. Today is {today_str}.

Student profile:
{subject_info}
Pending tasks: {pending_tasks}
Request: "{context}"

Create a specific personalized study plan. If exam in X days, give a DAY-BY-DAY schedule. Otherwise give specific today-tasks.

Rules: use actual subject names, be specific about chapters/problem types/hours, order by importance, sound like a smart senior student.

Return ONLY a JSON array, no markdown fences, no extra text:
[{{"title": "specific task", "priority": "high|medium|low"}}]

Generate 5-7 tasks."""

        raw = call_ai('', prompt).strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw, flags=re.MULTILINE).strip().rstrip('`').strip()
        tasks_data = json.loads(raw)
        saved = []
        for t in tasks_data[:7]:
            task = Task(user_id=uid, title=t['title'], priority=t.get('priority', 'medium'), ai_generated=True)
            db.session.add(task)
            saved.append({'title': t['title'], 'priority': t.get('priority', 'medium')})
        db.session.commit()
        return jsonify({'success': True, 'tasks': saved})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ai/tutor', methods=['POST'])
@login_required
def ai_tutor():
    data = request.get_json()
    question = data.get('message', '')
    history = data.get('history', [])
    uid = session['user_id']

    db.session.add(ChatMessage(user_id=uid, role='user', content=question))

    if not GEMINI_API_KEY:
        response = "I'm Nova, your AI tutor! The AI service is not configured on this server yet."
        db.session.add(ChatMessage(user_id=uid, role='assistant', content=response))
        db.session.commit()
        return jsonify({'response': response})

    try:
        subjects = Subject.query.filter_by(user_id=uid).all()
        subject_names = ', '.join([s.name for s in subjects]) or 'various subjects'
        history_text = ""
        for h in history[-8:]:
            role = "Student" if h['role'] == 'user' else "Nova"
            history_text += f"{role}: {h['content']}\n"

        system = f"""You are Nova, a brilliant AI study tutor. Student is studying: {subject_names}.
Be warm, clear, and use analogies. Keep responses concise — 3-5 sentences max unless asked for detail.
Use simple formatting: bold for key terms, bullet points for lists. End with one follow-up question.

Recent conversation:
{history_text}"""

        response = call_ai('', f"Student: {question}\nNova:", system_prompt=system)
        db.session.add(ChatMessage(user_id=uid, role='assistant', content=response))
        db.session.commit()
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'response': f"Error: {str(e)}"})

@app.route('/api/ai/analyze-progress', methods=['POST'])
@login_required
def analyze_progress():
    data = request.get_json()
    uid = session['user_id']
    subjects = Subject.query.filter_by(user_id=uid).all()
    today = date.today()
    week_focus = db.session.query(db.func.sum(FocusSession.duration_minutes))\
        .filter(FocusSession.user_id == uid,
                FocusSession.session_date >= today - timedelta(days=7)).scalar() or 0
    tasks_done = Task.query.filter_by(user_id=uid, completed=True).count()
    tasks_total = Task.query.filter_by(user_id=uid).count()

    if not GEMINI_API_KEY:
        return jsonify({'analysis': f"You've studied {round(week_focus/60,1)} hours this week and completed {tasks_done}/{tasks_total} tasks. Add your Gemini API key for detailed AI analysis."})

    try:
        subject_data = "\n".join([f"- {s.name}: {s.studied_hours}h of {s.target_hours}h target" for s in subjects])
        analysis = call_ai('', f"""Student weekly data:
- Focus this week: {round(week_focus/60,1)} hours
- Tasks: {tasks_done}/{tasks_total} completed
- Subjects:
{subject_data}

Write 3-4 sentences: specific numbers, one strength, one area to improve, one concrete recommendation. Encouraging but honest.""")
        return jsonify({'analysis': analysis})
    except Exception as e:
        return jsonify({'analysis': f'Could not generate analysis: {str(e)}'})


@app.route('/api/settings/apikey', methods=['POST'])
@login_required
def save_api_key():
    # API key is now server-side only — this endpoint kept for compatibility
    return jsonify({'success': True})

@app.route('/api/settings/apikey', methods=['GET'])
@login_required
def get_api_key():
    return jsonify({'has_key': bool(GEMINI_API_KEY)})

@app.route('/api/ai/status')
@login_required
def ai_status():
    return jsonify({'available': bool(GEMINI_API_KEY)})

# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)