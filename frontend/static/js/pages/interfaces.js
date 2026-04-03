/**
 * Schnittstellen-Listenseite — Übersicht aller Schnittstellen.
 */

import { API } from '../api.js';
import { setContent, esc, badge } from '../utils.js';

export async function render() {
  const [ifaces, sps, streams] = await Promise.all([
    API.get('interfaces'),
    API.get('subprocesses'),
    API.get('streams'),
  ]);

  const nameMap = Object.fromEntries([
    ...sps.map(sp => [sp.id, sp.name]),
    ...streams.map(s => [s.id, s.name]),
  ]);
  // Map subprocess → stream for linking
  const spStreamMap = Object.fromEntries(sps.map(sp => [sp.id, sp.stream_id]));

  const typeSet = [...new Set(ifaces.map(i => i.interface_type).filter(Boolean))];
  const typeOpts = [
    '<option value="">Alle Typen</option>',
    ...typeSet.map(t => `<option value="${esc(t)}">${esc(t)}</option>`),
  ].join('');

  function processLink(pid) {
    const streamId = spStreamMap[pid] || (streams.find(s => s.id === pid) ? pid : null);
    if (streamId) {
      return `<a href="#/streams/${encodeURIComponent(streamId)}" onclick="event.stopPropagation()"
               style="color:var(--primary)">${esc(nameMap[pid] || pid)}</a>
              <br><code style="font-size:10px;color:var(--text-muted)">${esc(pid)}</code>`;
    }
    return `<code>${esc(pid)}</code>`;
  }

  const rows = ifaces.map(i => `
    <tr class="iface-row" data-type="${esc(i.interface_type || '')}">
      <td style="font-size:12px">${processLink(i.source_process_id)}</td>
      <td style="text-align:center">${badge('badge-info', i.interface_type || '—')}</td>
      <td style="font-size:12px">${processLink(i.target_process_id)}</td>
      <td style="color:var(--text-muted);font-size:12px;max-width:250px">${esc(i.description || '—')}</td>
    </tr>`).join('');

  setContent(`
    <div class="page-header">
      <h1>Schnittstellen</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:13px">${ifaces.length} gesamt</span>
      </div>
    </div>
    <div class="filters">
      <select id="filter-if-type" onchange="window._filterIfaces()">${typeOpts}</select>
      <input id="filter-if-q" type="search" placeholder="Suchen…" oninput="window._filterIfaces()"
             style="padding:6px 10px;border:1px solid var(--border);border-radius:4px;font-size:12px;min-width:180px">
    </div>
    <div class="card"><div class="table-wrap">
      <table><thead><tr><th>Quelle</th><th>Typ</th><th>Ziel</th><th>Beschreibung</th></tr></thead>
      <tbody id="iface-body">${rows}</tbody></table>
    </div></div>
    <p style="color:var(--text-muted);font-size:12px;margin-top:8px">
      Um Schnittstellen hinzuzufügen oder zu bearbeiten, navigieren Sie zur Detailseite eines Streams.
    </p>
  `);
}

window._filterIfaces = function () {
  const type = document.getElementById('filter-if-type')?.value || '';
  const q = (document.getElementById('filter-if-q')?.value || '').toLowerCase().trim();
  document.querySelectorAll('#iface-body .iface-row').forEach(row => {
    const ok = (!type || row.dataset.type === type)
            && (!q || row.textContent.toLowerCase().includes(q));
    row.style.display = ok ? '' : 'none';
  });
};
