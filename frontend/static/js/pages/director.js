/**
 * Director Dashboard — management cockpit for DE/AT harmonization decisions.
 */

import { API } from '../api.js';
import { setContent, esc, badge } from '../utils.js';

// ─── Entry point ─────────────────────────────────────────────────────────────

export async function render() {
  let data;
  try {
    data = await API.get('director/overview');
  } catch (e) {
    setContent(`<div class="card card-body" style="color:var(--danger)">
      Failed to load director overview: ${esc(e.message)}</div>`);
    return;
  }

  const s = data.summary;
  const dist = data.recommendation_distribution;
  const streams = data.streams || [];
  const needsAction = streams.filter(r => r.needs_action);

  setContent(`
    <div class="page-header">
      <h1>Director Dashboard</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:13px">${s.total_streams} streams under review</span>
      </div>
    </div>

    ${_renderProgress(s)}
    ${_renderDistribution(dist, s.total_streams)}
    ${_renderTargetPicture(streams)}
    ${_renderAttention(needsAction)}
    ${_renderStreamTable(streams)}
  `);
}

// ─── Progress cards ──────────────────────────────────────────────────────────

function _renderProgress(s) {
  const pct = (n) => s.total_streams ? Math.round((n / s.total_streams) * 100) : 0;

  const card = (value, total, label, color) => {
    const p = total ? Math.round((value / total) * 100) : 0;
    return `<div class="stat-card" style="position:relative;overflow:hidden">
      <div style="position:absolute;bottom:0;left:0;height:4px;width:${p}%;background:${color}"></div>
      <div class="stat-value">${value}<span style="font-size:14px;color:var(--text-muted)">/${total}</span></div>
      <div class="stat-label">${esc(label)}</div>
    </div>`;
  };

  return `
    <div class="stat-grid" style="margin-bottom:20px">
      ${card(s.as_is_complete, s.total_streams, 'AS-IS Complete', 'var(--primary)')}
      ${card(s.delta_ready, s.total_streams, 'Delta Available', 'var(--primary)')}
      ${card(s.options_complete, s.total_streams, 'All 3 Options Assessed', '#8b5cf6')}
      ${card(s.recommendations_ready, s.total_streams, 'Recommendation Ready', 'var(--success)')}
      ${card(s.reviewed, s.total_streams, 'Reviewed', 'var(--success)')}
      ${card(s.total_streams - s.blocked, s.total_streams, 'No Issues', '#22c55e')}
    </div>`;
}

// ─── Recommendation distribution ─────────────────────────────────────────────

function _renderDistribution(dist, total) {
  if (!total) return '';

  const bar = (label, count, color) => {
    const pct = total ? Math.round((count / total) * 100) : 0;
    return `<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
      <span style="width:110px;font-size:12px;text-align:right">${esc(label)}</span>
      <div style="flex:1;background:var(--bg-light);border-radius:4px;height:22px;position:relative">
        <div style="width:${pct}%;background:${color};height:100%;border-radius:4px;min-width:${count ? '2px' : '0'}"></div>
      </div>
      <span style="width:50px;font-size:13px;font-weight:600">${count}</span>
    </div>`;
  };

  return `<div class="card" style="margin-bottom:20px">
    <div class="card-header">Recommendation Distribution</div>
    <div class="card-body">
      ${bar('DE Standard', dist.de_standard, '#3b82f6')}
      ${bar('AT Standard', dist.at_standard, '#8b5cf6')}
      ${bar('Central', dist.central, '#22c55e')}
      ${bar('No Decision', dist.none, '#94a3b8')}
    </div>
  </div>`;
}

// ─── Target operating model picture ──────────────────────────────────────────

function _renderTargetPicture(streams) {
  const groups = {
    local: [],   // keep_local or no recommendation
    de: [],      // de_standard
    at: [],      // at_standard
    central: [], // central
  };

  for (const r of streams) {
    const eff = r.reviewed_decision || r.recommended_option;
    if (eff === 'de_standard') groups.de.push(r);
    else if (eff === 'at_standard') groups.at.push(r);
    else if (eff === 'central') groups.central.push(r);
    else groups.local.push(r);
  }

  const col = (title, color, items) => {
    const names = items.map(r =>
      `<a href="#/streams/${encodeURIComponent(r.stream_id)}" style="display:block;padding:4px 0;font-size:12px;color:var(--primary);border-bottom:1px solid var(--border)">${esc(r.stream_name)}</a>`
    ).join('');
    return `<div style="flex:1;min-width:160px">
      <div style="padding:8px 12px;background:${color};color:#fff;border-radius:6px 6px 0 0;font-size:13px;font-weight:600">
        ${esc(title)} <span style="float:right">${items.length}</span>
      </div>
      <div style="border:1px solid var(--border);border-top:none;border-radius:0 0 6px 6px;padding:6px 10px;min-height:40px">
        ${names || '<span style="color:var(--text-muted);font-size:12px">---</span>'}
      </div>
    </div>`;
  };

  return `<div class="card" style="margin-bottom:20px">
    <div class="card-header">Target Operating Model Picture</div>
    <div class="card-body">
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        ${col('Adopt DE', '#3b82f6', groups.de)}
        ${col('Adopt AT', '#8b5cf6', groups.at)}
        ${col('Central / Unified', '#22c55e', groups.central)}
        ${col('Local / Undecided', '#94a3b8', groups.local)}
      </div>
    </div>
  </div>`;
}

// ─── Management attention ────────────────────────────────────────────────────

function _renderAttention(items) {
  if (!items.length) {
    return `<div class="card" style="margin-bottom:20px">
      <div class="card-header">Management Attention</div>
      <div class="card-body"><p style="color:var(--text-muted)">No streams require escalation.</p></div>
    </div>`;
  }

  const rows = items.map(r => `
    <tr>
      <td><a href="#/streams/${encodeURIComponent(r.stream_id)}" style="color:var(--primary);font-weight:600">${esc(r.stream_name)}</a></td>
      <td style="font-size:12px">${r.action_reasons.map(reason => `<span style="display:inline-block;padding:2px 6px;margin:1px 2px;background:#fef2f2;border:1px solid var(--danger);border-radius:3px;font-size:11px;color:var(--danger)">${esc(reason)}</span>`).join('')}</td>
      <td style="white-space:nowrap">
        <a href="#/streams/${encodeURIComponent(r.stream_id)}" class="btn btn-sm">Stream</a>
        <a href="#/decisions/${encodeURIComponent(r.stream_id)}" class="btn btn-sm">Decision</a>
      </td>
    </tr>
  `).join('');

  return `<div class="card" style="margin-bottom:20px">
    <div class="card-header">Management Attention <span class="badge badge-danger">${items.length}</span></div>
    <div class="card-body">
      <div class="table-wrap"><table>
        <thead><tr><th>Stream</th><th>Issues</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>
  </div>`;
}

// ─── Full stream table ───────────────────────────────────────────────────────

function _renderStreamTable(streams) {
  const optLabel = (opt) => {
    const map = { de_standard: 'DE Standard', at_standard: 'AT Standard', central: 'Central' };
    return map[opt] || '---';
  };
  const optBadge = (opt) => {
    if (!opt) return badge('badge-muted', 'none');
    const cls = { de_standard: 'badge-primary', at_standard: 'badge-info', central: 'badge-success' };
    return badge(cls[opt] || 'badge-muted', optLabel(opt));
  };
  const statusBadge = (status) => {
    const cls = { not_started: 'badge-muted', draft: 'badge-warning', completed: 'badge-info', reviewed: 'badge-success' };
    return badge(cls[status] || 'badge-muted', (status || 'not started').replace(/_/g, ' '));
  };
  const deltaCell = (d) => {
    const parts = [];
    if (d.high) parts.push(`<span style="color:var(--danger);font-weight:600">${d.high}H</span>`);
    if (d.medium) parts.push(`<span style="color:var(--warning)">${d.medium}M</span>`);
    if (d.low) parts.push(`<span style="color:var(--success)">${d.low}L</span>`);
    return parts.length ? parts.join(' ') : '<span style="color:var(--text-muted)">---</span>';
  };

  const rows = streams.map(r => `
    <tr class="clickable" onclick="location.hash='#/decisions/${encodeURIComponent(r.stream_id)}'">
      <td>
        <strong>${esc(r.stream_name)}</strong>
        <br><span style="font-size:11px;color:var(--text-muted)">${esc(r.stream_id)}</span>
      </td>
      <td>${r.as_is_complete ? badge('badge-success', 'complete') : badge('badge-danger', 'incomplete')}</td>
      <td>${deltaCell(r.delta_summary)}</td>
      <td>${r.option_count}/3</td>
      <td>${optBadge(r.recommended_option)}</td>
      <td>${r.reviewed_decision ? optBadge(r.reviewed_decision) : '<span style="color:var(--text-muted)">---</span>'}</td>
      <td>${statusBadge(r.review_status)}</td>
      <td>${r.needs_action ? badge('badge-danger', 'action needed') : badge('badge-success', 'ok')}</td>
    </tr>
  `).join('');

  return `<div class="card">
    <div class="card-header">All Streams — Recommendation Overview</div>
    <div class="card-body">
      <div class="table-wrap"><table>
        <thead><tr>
          <th>Stream</th><th>AS-IS</th><th>Delta</th><th>Options</th>
          <th>Recommended</th><th>Reviewed</th><th>Status</th><th>Action</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>
  </div>`;
}
