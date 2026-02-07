// Simple metrics client for DAU tracking
import api from './api';

const ANON_KEY = 'anon_id_v1';

function ensureAnonId() {
  let id = localStorage.getItem(ANON_KEY);
  if (!id) {
    try {
      id = crypto.randomUUID();
    } catch (e) {
      id = 'anon-' + Math.random().toString(36).slice(2, 12);
    }
    localStorage.setItem(ANON_KEY, id);
  }
  return id;
}

async function trackEvent(event = 'page_view', extra = {}) {
  const anon_id = ensureAnonId();
  const payload = {
    anon_id,
    event,
    timestamp: new Date().toISOString(),
    source: extra.source || 'site'
  };

  try {
    // Fire-and-forget; don't block UI
    await fetch((import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api/metrics/track', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
  } catch (e) {
    // swallow errors to avoid breaking app
    console.warn('metrics track failed', e);
  }
}

async function getDAU(start = null, end = null) {
  const query = [];
  if (start) query.push('start=' + encodeURIComponent(start));
  if (end) query.push('end=' + encodeURIComponent(end));
  const qs = query.length ? ('?' + query.join('&')) : '';
  return api._fetchWithAutoRefresh((import.meta.env.VITE_API_URL || 'http://localhost:8000') + `/api/metrics/admin/dau${qs}`, {
    headers: {
      ...api._getAuthHeaders()
    }
  }).then(r => r.json());
}

export default {
  ensureAnonId,
  trackEvent,
  getDAU
};
