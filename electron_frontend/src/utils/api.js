import { API_URL } from './constants';

export async function fetchConfig() {
  const res = await fetch(`${API_URL}/api/config`);
  if (!res.ok) throw new Error(`Failed to fetch config: ${res.status}`);
  return res.json();
}

export async function fetchProviders() {
  const res = await fetch(`${API_URL}/api/providers/profiles`);
  if (!res.ok) throw new Error(`Failed to fetch providers: ${res.status}`);
  return res.json();
}

export async function fetchModels(provider, forceRefresh = false) {
  const url = `${API_URL}/api/models?provider=${encodeURIComponent(provider)}${forceRefresh ? '&refresh=1' : ''}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch models: ${res.status}`);
  return res.json();
}

export async function fetchAllModels() {
  const res = await fetch(`${API_URL}/api/models`).catch(() => ({ ok: false }));
  if (!res.ok) return {};
  return res.json();
}

export async function saveProviderKey(provider, apiKey) {
  const res = await fetch(`${API_URL}/api/providers/keys/${encodeURIComponent(provider)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  });
  return res.ok;
}

export async function deleteProviderKey(provider) {
  const res = await fetch(`${API_URL}/api/providers/keys/${encodeURIComponent(provider)}`, {
    method: 'DELETE',
  });
  return res.ok;
}

export async function testProviderKey(provider, apiKey) {
  const res = await fetch(`${API_URL}/api/providers/${encodeURIComponent(provider)}/key/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) return { ok: false, message: `HTTP ${res.status}` };
  return res.json();
}

export async function fetchVoiceList() {
  const res = await fetch(`${API_URL}/api/tts/voices`).catch(() => ({ ok: false }));
  if (!res.ok) return [];
  const data = await res.json();
  return data.voices || [];
}

export async function fetchSystemInfo() {
  const [sysRes, infoRes] = await Promise.all([
    fetch(`${API_URL}/api/system`).catch(() => ({ ok: false })),
    fetch(`${API_URL}/api/info`).catch(() => ({ ok: false })),
  ]);
  const sysData = sysRes.ok ? await sysRes.json() : {};
  const infoData = infoRes.ok ? await infoRes.json() : {};
  return { ...sysData, ...infoData };
}

export async function updateConfig(key, value) {
  const res = await fetch(`${API_URL}/api/config/${key}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error(`Failed to set ${key}: ${res.status}`);
  return res.json();
}

export async function fetchSessions() {
  const res = await fetch(`${API_URL}/api/sessions`);
  if (!res.ok) throw new Error(`Failed to fetch sessions: ${res.status}`);
  const data = await res.json();
  return data.sessions || [];
}

export async function createSession(title = 'New Session') {
  const res = await fetch(`${API_URL}/api/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
  return res.json();
}

export async function fetchMemory() {
  const res = await fetch(`${API_URL}/api/memory`).catch(() => ({ ok: false }));
  if (!res.ok) return {};
  return res.json();
}

export async function saveMemory(data) {
  const res = await fetch(`${API_URL}/api/memory`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Failed to save memory: ${res.status}`);
  return res.json();
}

export async function fetchTools() {
  const res = await fetch(`${API_URL}/api/tools`).catch(() => ({ ok: false }));
  if (!res.ok) return [];
  const data = await res.json();
  return data.tools || data;
}

export async function fetchSkills() {
  const res = await fetch(`${API_URL}/api/skills`).catch(() => ({ ok: false }));
  if (!res.ok) return [];
  const data = await res.json();
  return data.skills || [];
}

export async function reloadSkills() {
  const res = await fetch(`${API_URL}/api/skills/reload`, { method: 'POST' }).catch(() => ({ ok: false }));
  if (!res.ok) return false;
  return true;
}

export async function importSkillFolder(folderPath) {
  const res = await fetch(`${API_URL}/api/skills/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: folderPath }),
  }).catch(() => ({ ok: false }));
  if (!res.ok) return { success: false, error: `HTTP ${res.status}` };
  return res.json();
}

export async function importSkillGitHub(repoUrl) {
  const res = await fetch(`${API_URL}/api/skills/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ github: repoUrl }),
  }).catch(() => ({ ok: false }));
  if (!res.ok) return { success: false, error: `HTTP ${res.status}` };
  return res.json();
}

export async function fetchSessionHistory(sessionId) {
  const res = await fetch(`${API_URL}/api/sessions/${sessionId}/history`);
  if (!res.ok) throw new Error(`Failed to fetch session history: ${res.status}`);
  const data = await res.json();
  return data.messages || [];
}

export async function fetchLastSession() {
  const res = await fetch(`${API_URL}/api/sessions/last`).catch(() => ({ ok: false }));
  if (!res.ok) return null;
  const data = await res.json();
  return data;
}

export async function touchSession(sessionId) {
  const res = await fetch(`${API_URL}/api/sessions/${encodeURIComponent(sessionId)}/touch`, {
    method: 'POST',
  });
  return res.ok;
}

export async function checkForUpdate() {
  const res = await fetch(`${API_URL}/api/update/check`, { method: 'POST' }).catch(() => ({ ok: false }));
  if (!res.ok) return { error: 'Could not check for updates' };
  return res.json();
}

export async function applyUpdate() {
  const res = await fetch(`${API_URL}/api/update/apply`, { method: 'POST' }).catch(() => ({ ok: false }));
  if (!res.ok) return { success: false, message: 'Could not apply update' };
  return res.json();
}

export async function getUpdateStatus() {
  const res = await fetch(`${API_URL}/api/update`).catch(() => ({ ok: false }));
  if (!res.ok) return {};
  return res.json();
}
