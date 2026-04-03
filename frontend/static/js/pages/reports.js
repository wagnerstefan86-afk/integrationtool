/**
 * Reports page — lists generated reports and renders selected report content.
 */

import { API } from '../api.js';
import { setContent, esc, badge, mdToHtml } from '../utils.js';

export async function render(reportName) {
  if (reportName) {
    return renderReport(reportName);
  }
  return renderList();
}

async function renderList() {
  const reports = await API.getGlobal('reports');

  if (reports.length === 0) {
    setContent(`
      <div class="page-header"><h1>Reports</h1></div>
      <div class="card card-body">
        <p style="color:var(--text-muted)">
          No reports found. Run an analysis via the API to generate a report.
        </p>
      </div>
    `);
    return;
  }

  const rows = reports.map(r => `
    <tr class="clickable" onclick="location.hash='#/reports/${encodeURIComponent(r.name)}'">
      <td><strong>${esc(r.name)}</strong></td>
      <td>${badge(r.category === 'generated' ? 'badge-info' : 'badge-success', r.category)}</td>
      <td style="color:var(--text-muted)">${esc(r.created)}</td>
      <td style="color:var(--text-muted)">${(r.size_bytes / 1024).toFixed(1)} KB</td>
    </tr>
  `).join('');

  setContent(`
    <div class="page-header">
      <h1>Reports</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:13px">${reports.length} report${reports.length !== 1 ? 's' : ''}</span>
      </div>
    </div>
    <div class="card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Category</th>
              <th>Created</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `);
}

async function renderReport(name) {
  const text = await API.getReportText(name);
  const content = mdToHtml(text);

  setContent(`
    <div class="page-header">
      <div style="min-width:0">
        <h1 style="font-size:16px;word-break:break-all">${esc(name)}</h1>
      </div>
      <div class="actions" style="flex-shrink:0">
        <a href="#/reports" class="btn">← Reports</a>
      </div>
    </div>
    <div class="card card-body" style="font-size:14px;line-height:1.7;max-width:none">
      ${content}
    </div>
  `);

  // Trigger mermaid rendering if available
  if (window.mermaid) {
    const nodes = document.querySelectorAll('.mermaid');
    if (nodes.length) mermaid.run({ nodes });
  }
}
