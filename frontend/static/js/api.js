/**
 * API client for Harmonizer backend.
 * All requests are proxied through the frontend server to /api/*.
 */

export const state = {
  dataset: localStorage.getItem('harmonizer_dataset') || 'examples',
};

async function _fetch(url, opts = {}) {
  let resp;
  try {
    resp = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
  } catch (e) {
    throw new Error('Backend nicht erreichbar: ' + e.message);
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch { /* ignore parse errors */ }
    throw new Error(`HTTP ${resp.status}: ${detail}`);
  }
  const text = await resp.text();
  if (!text) return null;
  return JSON.parse(text);
}

function datasetQS(extra = {}) {
  return new URLSearchParams({ dataset: state.dataset, ...extra }).toString();
}

export const API = {
  /**
   * GET /api/{endpoint}?dataset=X[&extra]
   */
  async get(endpoint, extra = {}) {
    return _fetch(`/api/${endpoint}?${datasetQS(extra)}`);
  },

  /**
   * GET /api/{endpoint} without dataset param (reports, enums, health)
   */
  async getGlobal(endpoint) {
    return _fetch(`/api/${endpoint}`);
  },

  /**
   * PUT /api/{endpoint}?dataset=X — create or update
   */
  async put(endpoint, data, extra = {}) {
    return _fetch(`/api/${endpoint}?${datasetQS(extra)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /**
   * POST /api/{endpoint}?dataset=X — action endpoints
   */
  async post(endpoint, data = {}, extra = {}) {
    return _fetch(`/api/${endpoint}?${datasetQS(extra)}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * DELETE /api/{endpoint}?dataset=X
   */
  async del(endpoint, extra = {}) {
    return _fetch(`/api/${endpoint}?${datasetQS(extra)}`, {
      method: 'DELETE',
    });
  },

  /**
   * GET /api/reports/{name} — returns plain text (markdown)
   */
  async getReportText(name) {
    let resp;
    try {
      resp = await fetch(`/api/reports/${encodeURIComponent(name)}`);
    } catch (e) {
      throw new Error('Backend nicht erreichbar');
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    return resp.text();
  },
};
