/**
 * Streams page — list view and detail view.
 */

import { API } from '../api.js';
import { setContent, esc, badge, scoreBarHtml, decisionBadge, classificationBadge, confidenceBadge } from '../utils.js';

// ─── List view ────────────────────────────────────────────────────────────────

export async function render(id) {
  if (id) {
    return renderDetail(id);
  }

  const [streams, areas, assessments] = await Promise.all([
    API.get('streams'),
    API.get('areas'),
    API.get('assessments'),
  ]);

  const areaMap = Object.fromEntries(areas.map(a => [a.id, a.name]));
  const assMap = Object.fromEntries(
    assessments
      .filter(a => a.assessed_object_type === 'stream')
      .map(a => [a.assessed_object_id, a])
  );

  // Collect unique values for filters
  const areaIds = [...new Set(streams.map(s => s.area_id).filter(Boolean))];
  const types = [...new Set(streams.map(s => s.stream_type).filter(Boolean))];

  const areaOpts = [
    '<option value="">All Areas</option>',
    ...areaIds.map(id => `<option value="${esc(id)}">${esc(areaMap[id] || id)}</option>`),
  ].join('');

  const typeOpts = [
    '<option value="">All Types</option>',
    ...types.map(t => `<option value="${esc(t)}">${esc(t)}</option>`),
  ].join('');

  // Pre-select area from hash query (?area=X)
  const hashQuery = location.hash.includes('?') ? location.hash.split('?')[1] : '';
  const preArea = new URLSearchParams(hashQuery).get('area') || '';

  const rows = streams.map(s => {
    const ass = assMap[s.id];
    const hasAssessment = !!ass;
    return `<tr class="clickable stream-row"
              data-area="${esc(s.area_id || '')}"
              data-type="${esc(s.stream_type || '')}"
              data-name="${esc(s.name.toLowerCase())}"
              onclick="location.hash='#/streams/${encodeURIComponent(s.id)}'">
      <td>
        <strong>${esc(s.name)}</strong>
        <br><code style="font-size:11px;color:var(--text-muted)">${esc(s.id)}</code>
      </td>
      <td>${esc(areaMap[s.area_id] || s.area_id || '—')}</td>
      <td>${badge('badge-info', s.stream_type || '—')}</td>
      <td>${badge('badge-muted', s.country_scope || '—')} ${badge('badge-muted', s.tenant_scope || '—')}</td>
      <td>${hasAssessment ? badge('badge-success', 'assessed') : badge('badge-muted', 'pending')}</td>
    </tr>`;
  }).join('');

  setContent(`
    <div class="page-header">
      <h1>Streams</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:13px">${streams.length} streams</span>
      </div>
    </div>

    <div class="filters">
      <select id="filter-area" onchange="filterStreams()">${areaOpts}</select>
      <select id="filter-type" onchange="filterStreams()">${typeOpts}</select>
      <input id="filter-q" type="search" placeholder="Search by name…"
             oninput="filterStreams()"
             style="padding:6px 10px;border:1px solid var(--border);border-radius:4px;font-size:12px;min-width:180px">
    </div>

    <div class="card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Area</th>
              <th>Type</th>
              <th>Scope</th>
              <th>Assessment</th>
            </tr>
          </thead>
          <tbody id="streams-body">${rows}</tbody>
        </table>
      </div>
    </div>
  `);

  // Apply pre-selected area filter
  if (preArea) {
    const sel = document.getElementById('filter-area');
    if (sel) { sel.value = preArea; filterStreams(); }
  }
}

// Exposed globally so onclick handlers can call it
window.filterStreams = function () {
  const area = document.getElementById('filter-area')?.value || '';
  const type = document.getElementById('filter-type')?.value || '';
  const q = (document.getElementById('filter-q')?.value || '').toLowerCase().trim();

  document.querySelectorAll('#streams-body .stream-row').forEach(row => {
    const areaMatch = !area || row.dataset.area === area;
    const typeMatch = !type || row.dataset.type === type;
    const qMatch = !q || row.dataset.name.includes(q) || row.textContent.toLowerCase().includes(q);
    row.style.display = areaMatch && typeMatch && qMatch ? '' : 'none';
  });
};

// ─── Detail view ──────────────────────────────────────────────────────────────

async function renderDetail(streamId) {
  const [stream, subprocesses, allAssessments] = await Promise.all([
    API.get(`streams/${encodeURIComponent(streamId)}`),
    API.get('subprocesses'),
    API.get('assessments'),
  ]);

  const streamSPs = subprocesses.filter(sp => sp.stream_id === streamId);
  const assessment = allAssessments.find(a => a.assessed_object_id === streamId);

  const regulatoryBadges = (stream.regulatory_context || [])
    .map(r => badge('badge-muted', r)).join(' ');

  const assessmentSection = assessment
    ? _renderAssessmentSummary(assessment)
    : `<p style="color:var(--text-muted)">No assessment recorded for this stream.</p>`;

  const spRows = streamSPs.map(sp => `
    <tr>
      <td>${esc(sp.name)}</td>
      <td style="color:var(--text-muted);font-size:12px">${esc(sp.purpose || sp.description || '—')}</td>
      <td>${badge('badge-muted', sp.country_scope || '')} ${badge('badge-muted', sp.tenant_scope || '')}</td>
    </tr>
  `).join('');

  setContent(`
    <div class="detail-header">
      <div>
        <h1>${esc(stream.name)}</h1>
        <div class="detail-meta">
          ${badge('badge-info', stream.stream_type || '—')}
          ${badge('badge-muted', stream.country_scope || '')}
          ${badge('badge-muted', stream.tenant_scope || '')}
        </div>
      </div>
      <div class="actions">
        <a href="#/streams" class="btn">← Streams</a>
      </div>
    </div>

    <div class="grid-2">
      <div>
        <div class="detail-section">
          <h3>Stream Info</h3>
          <dl class="key-value">
            <dt>ID</dt>        <dd><code>${esc(stream.id)}</code></dd>
            <dt>Area</dt>      <dd>${esc(stream.area_id || '—')}</dd>
            <dt>Owner</dt>     <dd>${esc(stream.owner_role || '—')}</dd>
            <dt>Description</dt><dd>${esc(stream.description || '—')}</dd>
            <dt>Notes</dt>     <dd>${esc(stream.notes || '—')}</dd>
            <dt>Regulatory</dt><dd>${regulatoryBadges || '—'}</dd>
          </dl>
        </div>

        <div class="detail-section">
          <h3>Assessment</h3>
          ${assessmentSection}
        </div>
      </div>

      <div>
        <div class="detail-section">
          <h3>Subprocesses (${streamSPs.length})</h3>
          ${streamSPs.length === 0
            ? '<p style="color:var(--text-muted)">No subprocesses defined.</p>'
            : `<div class="table-wrap"><table>
                <thead><tr><th>Name</th><th>Purpose</th><th>Scope</th></tr></thead>
                <tbody>${spRows}</tbody>
              </table></div>`
          }
        </div>
      </div>
    </div>
  `);
}

function _renderAssessmentSummary(a) {
  const dims = (a.answers || []);
  const constraints = (a.hard_constraints || []);

  const dimRows = dims.map(d => {
    const pct = Math.round((d.score / 5) * 100);
    const cls = pct >= 70 ? 'high' : pct >= 45 ? 'medium' : 'low';
    return `<tr>
      <td style="font-size:12px">${esc(d.dimension.replace(/_/g, ' '))}</td>
      <td>
        <div class="score-bar" style="min-width:120px">
          <div class="score-bar-track">
            <div class="score-bar-fill ${cls}" style="width:${pct}%"></div>
          </div>
          <span>${d.score}/5</span>
        </div>
      </td>
      <td style="font-size:11px;color:var(--text-muted)">${esc(d.rationale || '')}</td>
    </tr>`;
  }).join('');

  const constraintBadges = constraints.length
    ? constraints.map(c => badge('badge-danger', c.replace(/_/g, ' '))).join(' ')
    : badge('badge-success', 'none');

  return `
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr>
        <th style="padding:6px 8px;font-size:11px;color:var(--text-muted);text-align:left">Dimension</th>
        <th style="padding:6px 8px;font-size:11px;color:var(--text-muted)">Score</th>
        <th style="padding:6px 8px;font-size:11px;color:var(--text-muted)">Rationale</th>
      </tr></thead>
      <tbody>${dimRows}</tbody>
    </table>
    <div style="margin-top:10px">
      <span style="font-size:12px;color:var(--text-muted)">Hard constraints:</span>
      <span style="margin-left:6px">${constraintBadges}</span>
    </div>
  `;
}
