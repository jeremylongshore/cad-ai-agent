import { auth } from './firebase';

const API_BASE = import.meta.env.VITE_API_URL || '';

async function getToken() {
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');
  return user.getIdToken();
}

async function request(path, options = {}) {
  const token = await getToken();
  const url = `${API_BASE}${path}`;

  const res = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${token}`,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error: ${res.status}`);
  }

  return res;
}

export async function healthCheck() {
  const res = await fetch(`${API_BASE}/api/health`);
  return res.json();
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await request('/api/upload', {
    method: 'POST',
    body: formData,
  });
  return res.json();
}

export async function planEdit(sessionId, prompt) {
  const res = await request('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, prompt }),
  });
  return res.json();
}

export async function applyChanges(sessionId, selectedOps = null) {
  const res = await request('/api/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, selected_ops: selectedOps }),
  });
  return res.json();
}

export function getRenderUrl(sessionId, type = 'original') {
  return `${API_BASE}/api/render?session_id=${sessionId}&type=${type}`;
}

export async function getRenderBlob(sessionId, type = 'original') {
  const res = await request(`/api/render?session_id=${sessionId}&type=${type}`);
  return res.blob();
}

export async function downloadFile(sessionId) {
  const res = await request(`/api/download?session_id=${sessionId}`);
  const blob = await res.blob();

  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?(.+?)"?$/);
  const filename = match ? match[1] : 'edited.dxf';

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
