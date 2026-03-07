import { auth } from './firebase';

const API_BASE = import.meta.env.VITE_API_URL || '';
const DEFAULT_TIMEOUT_MS = 60_000;   // 60s for most requests
const UPLOAD_TIMEOUT_MS = 300_000;   // 5min for large PDF uploads

async function getToken() {
  const user = auth.currentUser;
  if (!user) throw new Error('Not authenticated');
  return user.getIdToken();
}

/** Turn network-level errors into user-friendly messages */
function friendlyError(err) {
  if (err.name === 'AbortError') {
    return 'Request timed out — the server took too long to respond. Please try again.';
  }
  if (err instanceof TypeError && /fetch|network/i.test(err.message)) {
    return 'Unable to reach the server. Check your internet connection and try again.';
  }
  return err.message;
}

async function request(path, options = {}) {
  const token = await getToken();
  const url = `${API_BASE}${path}`;
  const timeoutMs = options._timeout || DEFAULT_TIMEOUT_MS;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res;
  try {
    res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        ...options.headers,
        Authorization: `Bearer ${token}`,
      },
    });
  } catch (err) {
    // Network-level failure (timeout, offline, DNS, etc.)
    throw new Error(friendlyError(err));
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error: ${res.status}`);
  }

  return res;
}

export async function healthCheck() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
    return res.json();
  } catch (err) {
    throw new Error(friendlyError(err));
  } finally {
    clearTimeout(timer);
  }
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await request('/api/upload', {
    method: 'POST',
    body: formData,
    _timeout: UPLOAD_TIMEOUT_MS,
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

export async function v2Prompt(sessionId, prompt, selectedRegions = null) {
  const body = { session_id: sessionId, prompt };
  if (selectedRegions) body.selected_regions = selectedRegions;
  const res = await request('/api/v2/prompt', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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

export async function clearHistory(sessionId) {
  const res = await request('/api/clear-history', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
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

export async function getDxfBlob(sessionId, type = 'original') {
  const res = await request(`/api/dxf?session_id=${sessionId}&type=${type}`);
  return res.blob();
}

export async function fetchProfiles() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/api/profiles`, { signal: controller.signal });
    if (!res.ok) {
      throw new Error(`Failed to fetch profiles: ${res.status}`);
    }
    return res.json();
  } catch (err) {
    throw new Error(friendlyError(err));
  } finally {
    clearTimeout(timer);
  }
}

export async function compareFiles(sessionId, revisionFile, profile = null) {
  const formData = new FormData();
  formData.append('file', revisionFile);

  let url = `/api/compare?session_id=${sessionId}`;
  if (profile) {
    url += `&profile=${encodeURIComponent(profile)}`;
  }

  const res = await request(url, {
    method: 'POST',
    body: formData,
  });
  return res.json();
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

export async function revisionUpload(sessionId, file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await request(`/api/revision/upload?session_id=${sessionId}`, {
    method: 'POST',
    body: formData,
    _timeout: UPLOAD_TIMEOUT_MS,
  });
  return res.json();
}

export async function revisionAlign(sessionId, controlPoints = null) {
  const res = await request('/api/revision/align', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, control_points: controlPoints }),
  });
  return res.json();
}

export async function revisionDiff(sessionId, profile = null) {
  const res = await request('/api/revision/diff', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, profile }),
  });
  return res.json();
}

export async function revisionApprove(sessionId, approvals) {
  const res = await request('/api/revision/approve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, approvals }),
  });
  return res.json();
}

export async function revisionApply(sessionId) {
  const res = await request('/api/revision/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  return res.json();
}

export function revisionDownloadUrl(sessionId) {
  return `${API_BASE}/api/revision/download?session_id=${sessionId}`;
}

// --- v2 Preview / Approve / Apply (EPIC-CAD-08) ---

export async function v2Preview(sessionId) {
  const res = await request('/api/v2/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  return res.json();
}

export async function v2Approve(sessionId, planId, approved, notes = '') {
  const res = await request('/api/v2/approve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, plan_id: planId, approved, notes }),
  });
  return res.json();
}

export async function v2Apply(sessionId) {
  const res = await request('/api/v2/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  return res.json();
}
