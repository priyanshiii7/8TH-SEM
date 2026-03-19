from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import json
import os
import re
import urllib.request
import urllib.error

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'studymate-secret-2024-change-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///studymate.db'
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

def call_gemini(api_key, prompt, system_prompt=None):
    """Call Google Gemini API — free key at aistudio.google.com"""
    full_prompt = (system_prompt + "\n\n" + prompt) if system_prompt else prompt
    payload = json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7}
    }).encode('utf-8')

    candidates = [
        ("v1beta", "gemini-2.0-flash"),
        ("v1beta", "gemini-2.0-flash-lite"),
        ("v1beta", "gemini-1.5-flash"),
        ("v1",     "gemini-1.5-flash"),
        ("v1beta", "gemini-1.0-pro"),
    ]
    last_err = "No models available"
    for version, model in candidates:
        url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read().decode())
                return result['candidates'][0]['content']['parts'][0]['text']
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code in (401, 403):
                raise Exception("Invalid API key. Get a free key at aistudio.google.com")
            if e.code == 400:
                raise Exception(f"Bad request: {body[:200]}")
            last_err = f"{model} not available ({e.code})"
            continue
        except Exception as e:
            last_err = str(e)
            continue
    raise Exception(f"All Gemini models failed. Last error: {last_err}")

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
    api_key = data.get('api_key', '')
    ai_reflection = None
    if api_key:
        try:
            ai_reflection = call_gemini(
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
    api_key = data.get('api_key', '')
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

    if not api_key:
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
        return jsonify({'success': True, 'tasks': plan, 'note': 'Add Gemini API key for fully personalized plans'})

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

        raw = call_gemini(api_key, prompt).strip()
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
    api_key = data.get('api_key', '')
    question = data.get('message', '')
    history = data.get('history', [])
    uid = session['user_id']

    db.session.add(ChatMessage(user_id=uid, role='user', content=question))

    if not api_key:
        response = "I'm Nova, your AI tutor! Add a free Gemini API key (click 'API Key' in the sidebar) to unlock me. Get one free at aistudio.google.com — no credit card needed!"
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

        system = f"""You are Nova, an enthusiastic and brilliant AI study tutor. Student is studying: {subject_names}.
Personality: warm, encouraging, uses analogies, explains simply, emojis occasionally, asks follow-up questions.
Always give clear examples, check understanding, suggest next steps.

Recent conversation:
{history_text}"""

        response = call_gemini(api_key, f"Student: {question}\nNova:", system_prompt=system)
        db.session.add(ChatMessage(user_id=uid, role='assistant', content=response))
        db.session.commit()
        return jsonify({'response': response})
    except Exception as e:
        return jsonify({'response': f"Error: {str(e)}"})

@app.route('/api/ai/analyze-progress', methods=['POST'])
@login_required
def analyze_progress():
    data = request.get_json()
    api_key = data.get('api_key', '')
    uid = session['user_id']
    subjects = Subject.query.filter_by(user_id=uid).all()
    today = date.today()
    week_focus = db.session.query(db.func.sum(FocusSession.duration_minutes))\
        .filter(FocusSession.user_id == uid,
                FocusSession.session_date >= today - timedelta(days=7)).scalar() or 0
    tasks_done = Task.query.filter_by(user_id=uid, completed=True).count()
    tasks_total = Task.query.filter_by(user_id=uid).count()

    if not api_key:
        return jsonify({'analysis': f"You've studied {round(week_focus/60,1)} hours this week and completed {tasks_done}/{tasks_total} tasks. Add your Gemini API key for detailed AI analysis."})

    try:
        subject_data = "\n".join([f"- {s.name}: {s.studied_hours}h of {s.target_hours}h target" for s in subjects])
        analysis = call_gemini(api_key, f"""Student weekly data:
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
    data = request.get_json()
    session['api_key'] = data.get('api_key', '')
    return jsonify({'success': True})

@app.route('/api/settings/apikey', methods=['GET'])
@login_required
def get_api_key():
    return jsonify({'has_key': bool(session.get('api_key', ''))})

# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)