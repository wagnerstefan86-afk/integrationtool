/**
 * Dashboard page — shows live stats from /api/dashboard.
 */

import { API, state } from '../api.js';
import { setContent, esc, badge } from '../utils.js';
import { navigate } from '../router.js';

function statCard(value, label, href) {
  return `<a href="${href}" style="text-decoration:none">
    <div class="stat-card">
      <div class="stat-value">${value ?? '—'}</div>
      <div class="stat-label">${esc(label)}</div>
    </div>
  </a>`;
}

export async function render() {
  const stats = await API.get('dashboard');

  // Update dataset selector options if we got the list
  if (stats.available_datasets?.length) {
    _updateDatasetOptions(stats.available_datasets);
  }

  const unassessed = stats.unassessed_streams || [];

  setContent(`
    <div class="page-header">
      <h1>Dashboard</h1>
      <div class="actions">
        <span class="badge badge-muted">Datensatz: ${esc(state.dataset)}</span>
      </div>
    </div>

    <div class="stat-grid">
      ${statCard(stats.area_count, 'Bereiche', '#/areas')}
      ${statCard(stats.stream_count, 'Streams', '#/streams')}
      ${statCard(stats.subprocess_count, 'Teilprozesse', '#/subprocesses')}
      ${statCard(stats.interface_count, 'Schnittstellen', '#/interfaces')}
      ${statCard(stats.stream_assessment_count, 'Bewertete Streams', '#/assessments')}
      ${statCard(stats.outcome_count, 'Ergebnisse', '#/outcomes')}
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          Nicht bewertete Streams
          <span class="badge badge-warning">${unassessed.length}</span>
        </div>
        <div class="card-body">
          ${unassessed.length === 0
            ? '<p style="color:var(--text-muted)">Alle Streams wurden bewertet.</p>'
            : `<ul style="list-style:none;padding:0">${unassessed.map(id =>
                `<li style="padding:7px 0;border-bottom:1px solid var(--border)">
                  <a href="#/streams/${encodeURIComponent(id)}" style="color:var(--primary)">${esc(id)}</a>
                </li>`).join('')}</ul>`
          }
        </div>
      </div>

      <div class="card">
        <div class="card-header">Systeminfo</div>
        <div class="card-body">
          ${_renderSystemInfo()}
          <div style="display:flex;flex-direction:column;gap:8px;margin-top:12px">
            <a href="#/streams" class="btn">Alle Streams anzeigen</a>
            <a href="#/areas" class="btn">Alle Bereiche anzeigen</a>
            <a href="#/decisions" class="btn">Entscheidungen anzeigen</a>
            <a href="#/reports" class="btn">Berichte anzeigen</a>
          </div>
        </div>
      </div>
    </div>
  `);
}

function _renderSystemInfo() {
  const h = window._harmonizer_health;
  if (!h) return '<p style="color:var(--text-muted);font-size:12px">Lädt...</p>';
  const rows = [
    ['Version', h.version || '---'],
    ['Git-Commit', h.git_commit && h.git_commit !== 'unknown' ? h.git_commit : '---'],
    ['Build-Datum', h.build_date && h.build_date !== 'unknown' ? h.build_date.slice(0, 10) : '---'],
    ['Umgebung', h.app_env || '---'],
  ];
  return `<dl class="key-value" style="font-size:12px;margin:0">${rows.map(([k, v]) =>
    `<dt>${esc(k)}</dt><dd><code>${esc(v)}</code></dd>`
  ).join('')}</dl>`;
}

function _updateDatasetOptions(datasets) {
  const sel = document.getElementById('dataset-select');
  if (!sel || sel.dataset.populated === 'true') return;
  sel.innerHTML = datasets.map(d =>
    `<option value="${esc(d)}" ${d === state.dataset ? 'selected' : ''}>${esc(d)}</option>`
  ).join('');
  sel.dataset.populated = 'true';
}
