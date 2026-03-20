
function closeApiModal(e) {
  if (!e || e.target === document.getElementById('apiModal')) {
    document.getElementById('apiModal').classList.remove('open');
  }
}

async function saveApiKey() {
  const key = document.getElementById('apiKeyInput').value.trim();
  const status = document.getElementById('apiKeyStatus');
  if (!key) { status.textContent = 'Please enter an API key'; status.className = 'api-status err'; return; }
  
  await fetch('/api/settings/apikey', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ api_key: key })
  });
  status.textContent = '✓ Key saved! AI features unlocked.';
  status.className = 'api-status ok';
  setTimeout(() => { document.getElementById('apiModal').classList.remove('open'); }, 1200);
}

// ─── Sidebar Toggle ────────────────────────────────────────────────────────────
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// ─── Date Display ──────────────────────────────────────────────────────────────
function updateDate() {
  const el = document.getElementById('topbarDate');
  if (el) {
    const now = new Date();
    el.textContent = now.toLocaleDateString('en-US', { weekday:'short', month:'short', day:'numeric' });
  }
}
updateDate();

// ─── Notifications ─────────────────────────────────────────────────────────────
function showNotif(msg, type='info') {
  const existing = document.querySelector('.notif');
  if (existing) existing.remove();
  const el = document.createElement('div');
  el.className = `notif ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.4s'; setTimeout(() => el.remove(), 400); }, 3000);
}

// ─── Close modal on escape ─────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
  }
});

// AI key is managed server-side


// ─── Load topbar avatar on every page ─────────────────────────────────────────
async function loadTopbarAvatar() {
  try {
    const res = await fetch('/api/user/stats');
    const data = await res.json();
    const av = document.getElementById('topbarAvatar');
    if (!av) return;
    if (data.avatar_b64) {
      av.innerHTML = `<img src="${data.avatar_b64}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;display:block">`;
    } else {
      av.textContent = data.name[0].toUpperCase();
      av.style.background = data.avatar_color;
    }
  } catch(e) {}
}
loadTopbarAvatar();
