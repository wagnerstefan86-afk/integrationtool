/**
 * Areas page — lists all areas with their stream counts.
 */

import { API } from '../api.js';
import { setContent, esc, badge } from '../utils.js';

export async function render() {
  const [areas, streams] = await Promise.all([
    API.get('areas'),
    API.get('streams'),
  ]);

  // Count streams per area
  const streamCounts = {};
  for (const s of streams) {
    streamCounts[s.area_id] = (streamCounts[s.area_id] || 0) + 1;
  }

  const rows = areas.map(a => `
    <tr class="clickable" onclick="location.hash='#/streams?area=${encodeURIComponent(a.id)}'">
      <td>
        <strong>${esc(a.name)}</strong>
        <br><code style="font-size:11px;color:var(--text-muted)">${esc(a.id)}</code>
      </td>
      <td style="color:var(--text-muted)">${esc(a.description || '—')}</td>
      <td style="text-align:center">${badge('badge-primary', String(streamCounts[a.id] || 0))}</td>
    </tr>
  `).join('');

  setContent(`
    <div class="page-header">
      <h1>Areas</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:13px">${areas.length} areas</span>
      </div>
    </div>

    <div class="card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Area</th>
              <th>Description</th>
              <th style="text-align:center">Streams</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `);
}
