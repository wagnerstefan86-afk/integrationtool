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
        <span class="badge badge-muted">Dataset: ${esc(state.dataset)}</span>
      </div>
    </div>

    <div class="stat-grid">
      ${statCard(stats.area_count, 'Areas', '#/areas')}
      ${statCard(stats.stream_count, 'Streams', '#/streams')}
      ${statCard(stats.subprocess_count, 'Subprocesses', '#/subprocesses')}
      ${statCard(stats.interface_count, 'Interfaces', '#/interfaces')}
      ${statCard(stats.stream_assessment_count, 'Assessed Streams', '#/assessments')}
      ${statCard(stats.outcome_count, 'Outcomes', '#/outcomes')}
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          Unassessed Streams
          <span class="badge badge-warning">${unassessed.length}</span>
        </div>
        <div class="card-body">
          ${unassessed.length === 0
            ? '<p style="color:var(--text-muted)">All streams have assessments.</p>'
            : `<ul style="list-style:none;padding:0">${unassessed.map(id =>
                `<li style="padding:7px 0;border-bottom:1px solid var(--border)">
                  <a href="#/streams/${encodeURIComponent(id)}" style="color:var(--primary)">${esc(id)}</a>
                </li>`).join('')}</ul>`
          }
        </div>
      </div>

      <div class="card">
        <div class="card-header">Quick Navigation</div>
        <div class="card-body">
          <div style="display:flex;flex-direction:column;gap:8px">
            <a href="#/streams" class="btn">View all Streams</a>
            <a href="#/areas" class="btn">View all Areas</a>
            <a href="#/reports" class="btn">View Reports</a>
          </div>
        </div>
      </div>
    </div>
  `);
}

function _updateDatasetOptions(datasets) {
  const sel = document.getElementById('dataset-select');
  if (!sel || sel.dataset.populated === 'true') return;
  sel.innerHTML = datasets.map(d =>
    `<option value="${esc(d)}" ${d === state.dataset ? 'selected' : ''}>${esc(d)}</option>`
  ).join('');
  sel.dataset.populated = 'true';
}
