/**
 * Teilprozesse list page — overview of all subprocesses across all streams.
 */

import { API } from '../api.js';
import { setContent, esc, badge } from '../utils.js';

export async function render() {
  const [sps, streams] = await Promise.all([
    API.get('subprocesses'),
    API.get('streams'),
  ]);
  const streamMap = Object.fromEntries(streams.map(s => [s.id, s.name]));

  const streamOpts = [
    '<option value="">Alle Streams</option>',
    ...streams.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`),
  ].join('');

  const rows = sps.map(sp => `
    <tr class="clickable sp-row" data-stream="${esc(sp.stream_id || '')}"
        onclick="location.hash='#/streams/${encodeURIComponent(sp.stream_id || '')}'">
      <td><strong>${esc(sp.name)}</strong>
        <br><code style="font-size:11px;color:var(--text-muted)">${esc(sp.id)}</code></td>
      <td><a href="#/streams/${encodeURIComponent(sp.stream_id || '')}" onclick="event.stopPropagation()"
             style="color:var(--primary)">${esc(streamMap[sp.stream_id] || sp.stream_id || '—')}</a></td>
      <td style="color:var(--text-muted);font-size:12px;max-width:300px">${esc(sp.purpose || sp.description || '—')}</td>
      <td>${badge('badge-muted', sp.country_scope || '')} ${badge('badge-muted', sp.tenant_scope || '')}</td>
    </tr>`).join('');

  setContent(`
    <div class="page-header">
      <h1>Teilprozesse</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:13px">${sps.length} gesamt</span>
      </div>
    </div>
    <div class="filters">
      <select id="filter-sp-stream" onchange="window._filterSPs()">${streamOpts}</select>
      <input id="filter-sp-q" type="search" placeholder="Suchen…" oninput="window._filterSPs()"
             style="padding:6px 10px;border:1px solid var(--border);border-radius:4px;font-size:12px;min-width:180px">
    </div>
    <div class="card"><div class="table-wrap">
      <table><thead><tr><th>Name</th><th>Stream</th><th>Zweck</th><th>Bereich</th></tr></thead>
      <tbody id="sp-body">${rows}</tbody></table>
    </div></div>
    <p style="color:var(--text-muted);font-size:12px;margin-top:8px">
      Um Teilprozesse hinzuzufügen oder zu bearbeiten, navigieren Sie zur Detailseite des übergeordneten Streams.
    </p>
  `);
}

window._filterSPs = function () {
  const stream = document.getElementById('filter-sp-stream')?.value || '';
  const q = (document.getElementById('filter-sp-q')?.value || '').toLowerCase().trim();
  document.querySelectorAll('#sp-body .sp-row').forEach(row => {
    const ok = (!stream || row.dataset.stream === stream)
            && (!q || row.textContent.toLowerCase().includes(q));
    row.style.display = ok ? '' : 'none';
  });
};
