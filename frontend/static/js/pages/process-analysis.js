/**
 * Process Analysis page — structured DE vs AT process capture per stream.
 *
 * Shows 6 default process phases, each with entity variants side-by-side.
 * Highlights differences, missing WHYs, and completeness gaps.
 */

import { API } from '../api.js';
import { setContent, esc, badge, toast } from '../utils.js';
import { openModal, closeModal } from '../components/modal.js';
import { textField, textArea, selectField, formRow, val } from '../components/forms.js';

// ─── Entry point ─────────────────────────────────────────────────────────────

export async function render(streamId) {
  if (!streamId) return renderIndex();
  return renderAnalysis(streamId);
}

// ─── Index: list all streams with analysis status ────────────────────────────

async function renderIndex() {
  const [streams, analyses] = await Promise.all([
    API.get('streams'),
    API.get('process-analysis'),
  ]);
  const analysisMap = Object.fromEntries((analyses || []).map(a => [a.stream_id, a]));

  const rows = streams.map(s => {
    const a = analysisMap[s.id];
    const status = a?.status || 'none';
    const statusCls = { none: 'badge-muted', draft: 'badge-warning', completed: 'badge-success' };
    return `<tr class="clickable" onclick="location.hash='#/process-analysis/${encodeURIComponent(s.id)}'">
      <td><strong>${esc(s.name)}</strong><br><code style="font-size:11px;color:var(--text-muted)">${esc(s.id)}</code></td>
      <td>${badge('badge-info', s.stream_type || '---')}</td>
      <td>${badge(statusCls[status] || 'badge-muted', status === 'none' ? 'not started' : status)}</td>
      <td>${a ? `${a.process_steps?.length || 0} steps` : '---'}</td>
    </tr>`;
  }).join('');

  setContent(`
    <div class="page-header"><h1>Process Analysis</h1></div>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr><th>Stream</th><th>Type</th><th>Analysis</th><th>Steps</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div></div>
  `);
}

// ─── Main analysis view ──────────────────────────────────────────────────────

async function renderAnalysis(streamId) {
  const stream = await API.get(`streams/${encodeURIComponent(streamId)}`);
  let analysis;
  try {
    analysis = await API.get(`process-analysis/${encodeURIComponent(streamId)}`);
  } catch {
    analysis = null;
  }

  if (!analysis) {
    setContent(`
      <div class="page-header">
        <div><h1>Process Analysis: ${esc(stream.name)}</h1></div>
        <div class="actions">
          <a href="#/process-analysis" class="btn">&larr; Back</a>
          <a href="#/streams/${encodeURIComponent(streamId)}" class="btn">Stream Detail</a>
        </div>
      </div>
      <div class="card card-body" style="text-align:center;padding:40px">
        <p style="color:var(--text-muted);margin-bottom:16px">No structured process analysis exists for this stream yet.</p>
        <button class="btn btn-primary" id="btn-scaffold">Create Process Analysis (DE / AT)</button>
      </div>
    `);
    document.getElementById('btn-scaffold')?.addEventListener('click', async () => {
      try {
        await API.post(`process-analysis/${encodeURIComponent(streamId)}/scaffold`);
        toast('Process analysis created');
        renderAnalysis(streamId);
      } catch (e) { toast(e.message, true); }
    });
    return;
  }

  // Load completeness + deltas
  let completeness = {}, deltas = [];
  try {
    [completeness, deltas] = await Promise.all([
      API.get(`process-analysis/${encodeURIComponent(streamId)}/completeness`),
      API.get(`process-analysis/${encodeURIComponent(streamId)}/deltas`),
    ]);
  } catch { /* non-critical */ }

  const entities = analysis.entities || ['DE', 'AT'];
  const steps = analysis.process_steps || [];
  const stepScores = completeness.step_scores || {};

  // Build sections
  const sections = steps.map(step => {
    const sid = step.step_id;
    const sc = stepScores[sid] || {};
    const stepDeltas = deltas.filter(d => d.step_id === sid);
    return _renderStep(streamId, step, entities, sc, stepDeltas);
  }).join('');

  // Summary bar
  const totalScore = completeness.score || 0;
  const missingWhys = completeness.missing_whys || 0;
  const highDeltas = deltas.filter(d => d.impact === 'high').length;

  setContent(`
    <div class="page-header">
      <div>
        <h1>Process Analysis: ${esc(stream.name)}</h1>
        <div class="detail-meta">
          ${badge('badge-info', stream.stream_type || '---')}
          ${_completeBadge(totalScore)}
          ${missingWhys ? badge('badge-danger', missingWhys + ' missing WHY') : ''}
          ${highDeltas ? badge('badge-danger', highDeltas + ' high-impact deltas') : ''}
        </div>
      </div>
      <div class="actions">
        <a href="#/process-analysis" class="btn">&larr; All Analyses</a>
        <a href="#/streams/${encodeURIComponent(streamId)}" class="btn">Stream Detail</a>
      </div>
    </div>

    ${_renderSummaryCards(completeness, deltas, entities)}
    ${sections}
  `);

  // Wire edit buttons
  document.querySelectorAll('[data-edit-variant]').forEach(btn => {
    btn.addEventListener('click', () => {
      const [stepId, entityId] = btn.dataset.editVariant.split('::');
      const step = steps.find(s => s.step_id === stepId);
      const variant = step?.entity_variants?.find(v => v.entity_id === entityId) || {};
      openVariantEditor(streamId, step, entityId, variant);
    });
  });
}

function _completeBadge(score) {
  if (score >= 80) return badge('badge-success', score + '% complete');
  if (score >= 50) return badge('badge-warning', score + '% complete');
  return badge('badge-danger', score + '% complete');
}

// ─── Summary cards ───────────────────────────────────────────────────────────

function _renderSummaryCards(compl, deltas, entities) {
  const high = deltas.filter(d => d.impact === 'high').length;
  const med = deltas.filter(d => d.impact === 'medium').length;
  const missingRationale = deltas.filter(d => d.delta_type === 'missing_rationale').length;

  return `<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">
    <div class="stat-card">
      <div class="stat-value">${compl.score || 0}%</div>
      <div class="stat-label">Completeness</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${compl.missing_whys || 0}</div>
      <div class="stat-label">Missing WHYs</div>
    </div>
    <div class="stat-card" ${high ? 'style="border-color:var(--danger)"' : ''}>
      <div class="stat-value" ${high ? 'style="color:var(--danger)"' : ''}>${high}</div>
      <div class="stat-label">High-Impact Deltas</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${med}</div>
      <div class="stat-label">Medium Deltas</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${entities.length}</div>
      <div class="stat-label">Entities</div>
    </div>
  </div>`;
}

// ─── Single process step ─────────────────────────────────────────────────────

function _renderStep(streamId, step, entities, scores, stepDeltas) {
  const sid = step.step_id;
  const variants = step.entity_variants || [];
  const avgScore = scores.score || 0;

  // Entity columns side by side
  const cols = entities.map(eid => {
    const v = variants.find(x => x.entity_id === eid) || {};
    const es = (scores.entity_scores || {})[eid] || {};
    return _renderVariantCol(streamId, sid, eid, v, es);
  }).join('');

  // Deltas for this step
  const deltaRows = stepDeltas.length ? `
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">
      <strong style="font-size:11px;color:var(--text-muted);text-transform:uppercase">Detected Differences</strong>
      ${stepDeltas.map(d => `
        <div style="display:flex;gap:8px;align-items:center;margin-top:4px;font-size:12px">
          ${_impactBadge(d.impact)}
          ${_deltaTypeBadge(d.delta_type)}
          <span>${esc(d.description)}</span>
        </div>
      `).join('')}
    </div>` : '';

  return `<div class="card" style="margin-bottom:16px">
    <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
      <span><strong>${esc(step.sort_order)}. ${esc(step.step_name)}</strong></span>
      <span>${_completeBadge(avgScore)}</span>
    </div>
    <div class="card-body">
      <div style="display:flex;gap:16px;flex-wrap:wrap">
        ${cols}
      </div>
      ${deltaRows}
    </div>
  </div>`;
}

function _impactBadge(impact) {
  const cls = { high: 'badge-danger', medium: 'badge-warning', low: 'badge-success' };
  return badge(cls[impact] || 'badge-muted', impact);
}

function _deltaTypeBadge(dtype) {
  const labels = {
    system_difference: 'System',
    channel_difference: 'Channel',
    role_difference: 'Role',
    variant_difference: 'Variant',
    missing_rationale: 'Missing WHY',
  };
  return `<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:#f3f4f6;color:var(--text-muted)">${labels[dtype] || dtype}</span>`;
}

// ─── Entity variant column ───────────────────────────────────────────────────

function _renderVariantCol(streamId, stepId, entityId, v, scores) {
  const score = scores.score || 0;
  const warnings = scores.warnings || [];
  const missingFields = scores.missing_fields || [];

  const list = (items, fallback) => {
    if (!items || !items.length) return `<span style="color:var(--text-muted)">${fallback || '---'}</span>`;
    return items.map(i => {
      if (typeof i === 'object' && i.role) return `${esc(i.role)} (${esc(i.responsibility || '')})`;
      return esc(String(i));
    }).join(', ');
  };

  const whyItems = v.why_is_it_done_this_way || [];
  const hasWhy = Array.isArray(whyItems) ? whyItems.some(w => String(w).trim()) : Boolean(whyItems);
  const whyClass = hasWhy ? '' : 'style="background:#fef2f2;border:1px solid var(--danger);border-radius:4px;padding:4px 8px"';

  return `<div style="flex:1;min-width:250px;border:1px solid var(--border);border-radius:6px;padding:10px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <strong>${esc(entityId)}</strong>
      <div>
        ${_completeBadge(score)}
        <button class="btn btn-sm" data-edit-variant="${esc(stepId)}::${esc(entityId)}" style="margin-left:4px">Edit</button>
      </div>
    </div>

    ${v.description ? `<p style="font-size:13px;margin:0 0 8px">${esc(v.description)}</p>` : '<p style="color:var(--danger);font-size:12px">No description</p>'}

    <div style="font-size:12px">
      ${v.trigger ? `<div><strong>Trigger:</strong> ${esc(v.trigger)}</div>` : ''}
      ${(v.input_channels||[]).length ? `<div><strong>Channels:</strong> ${list(v.input_channels)}</div>` : ''}
      <div><strong>Systems:</strong> ${missingFields.includes('systems_used') ? '<span style="color:var(--danger)">missing</span>' : list(v.systems_used)}</div>
      <div><strong>Roles:</strong> ${missingFields.includes('roles_involved') ? '<span style="color:var(--danger)">missing</span>' : list(v.roles_involved)}</div>
      ${v.output ? `<div><strong>Output:</strong> ${esc(v.output)}</div>` : ''}
      ${v.sla_or_target ? `<div><strong>SLA/Target:</strong> ${esc(v.sla_or_target)}</div>` : ''}
      ${v.approx_volume ? `<div><strong>Volume:</strong> ${esc(v.approx_volume)}</div>` : ''}
    </div>

    <div ${whyClass} style="margin-top:8px;font-size:12px">
      <strong style="color:${hasWhy ? 'inherit' : 'var(--danger)'}">WHY:</strong>
      ${hasWhy
        ? `<span>${list(whyItems)}</span>`
        : '<span style="color:var(--danger)"> Not documented — required for standardization decisions</span>'}
    </div>

    ${(v.pain_points||[]).length ? `<div style="margin-top:6px;font-size:11px"><strong>Pain Points:</strong> ${list(v.pain_points)}</div>` : ''}
    ${(v.evidence_or_examples||[]).length ? `<div style="margin-top:4px;font-size:11px"><strong>Evidence:</strong> ${list(v.evidence_or_examples)}</div>` : ''}

    ${warnings.length ? `<div style="margin-top:6px">${warnings.map(w => `<div style="font-size:11px;color:var(--warning)">&#9888; ${esc(w)}</div>`).join('')}</div>` : ''}
  </div>`;
}

// ─── Variant editor modal ────────────────────────────────────────────────────

async function openVariantEditor(streamId, step, entityId, variant) {
  const stepId = step.step_id;
  const v = variant || {};

  // Load guide questions
  let guideQs = [];
  try { guideQs = await API.getGlobal(`process-analysis-guide/${stepId}`); } catch { /* ok */ }

  const guideHtml = guideQs.length ? `
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;padding:10px 14px;margin-bottom:14px">
      <strong style="font-size:12px;color:#0369a1">Interview Guide — ${esc(step.step_name)}</strong>
      <ul style="margin:6px 0 0 16px;font-size:12px;color:#0369a1">
        ${guideQs.map(q => `<li>${esc(q.text)}</li>`).join('')}
      </ul>
    </div>` : '';

  const j = (arr) => (arr || []).join('\n');
  const jr = (roles) => (roles || []).map(r => typeof r === 'object' ? `${r.role}: ${r.responsibility || ''}` : String(r)).join('\n');

  openModal(`${esc(step.step_name)} — ${esc(entityId)}`, `
    ${guideHtml}

    ${textArea('f-pa-desc', 'Description *', v.description || '', { rows: 2 })}
    ${textField('f-pa-trigger', 'Trigger', v.trigger || '')}
    ${formRow(
      textArea('f-pa-channels', 'Input Channels (one per line)', j(v.input_channels), { rows: 2 }),
      textArea('f-pa-systems', 'Systems Used * (one per line)', j(v.systems_used), { rows: 2 })
    )}
    ${textArea('f-pa-roles', 'Roles & Responsibilities * (one per line, format: Role: Responsibility)', jr(v.roles_involved), { rows: 3 })}
    ${formRow(
      textField('f-pa-output', 'Output', v.output || ''),
      textField('f-pa-sla', 'SLA / Target', v.sla_or_target || '')
    )}
    ${textField('f-pa-volume', 'Approx. Volume', v.approx_volume || '')}
    ${textArea('f-pa-variants', 'Process Variants (one per line)', j(v.variants), { rows: 2 })}

    <div style="background:#fef2f2;border:1px solid var(--danger);border-radius:6px;padding:10px 14px;margin:12px 0">
      <label for="f-pa-why" style="font-weight:700;color:var(--danger)">WHY is it done this way? * (mandatory)</label>
      <textarea class="form-control" id="f-pa-why" rows="3" style="margin-top:4px;border-color:var(--danger)">${esc(j(v.why_is_it_done_this_way))}</textarea>
      <p style="font-size:11px;color:var(--danger);margin:4px 0 0">Without WHY, no standardization decision can be made.</p>
    </div>

    ${textArea('f-pa-painpoints', 'Pain Points (one per line)', j(v.pain_points), { rows: 2 })}
    ${textArea('f-pa-evidence', 'Evidence / Examples (one per line)', j(v.evidence_or_examples), { rows: 2 })}
    ${formRow(
      selectField('f-pa-performed', 'Performed In', [entityId, 'central', 'local', 'shared', 'unknown'], v.performed_in || entityId),
      textArea('f-pa-maturity', 'Maturity Notes', v.maturity_notes || '', { rows: 2 })
    )}
  `, async () => {
    const toList = (id) => document.getElementById(id)?.value.split('\n').map(l => l.trim()).filter(Boolean) || [];
    const parseRoles = (id) => {
      const lines = toList(id);
      return lines.map(line => {
        const parts = line.split(':');
        if (parts.length >= 2) return { role: parts[0].trim(), responsibility: parts.slice(1).join(':').trim() };
        return { role: line.trim(), responsibility: '' };
      });
    };

    const payload = {
      entity_id: entityId,
      entity_name: entityId,
      description: val('f-pa-desc'),
      trigger: val('f-pa-trigger'),
      input_channels: toList('f-pa-channels'),
      systems_used: toList('f-pa-systems'),
      roles_involved: parseRoles('f-pa-roles'),
      output: val('f-pa-output'),
      sla_or_target: val('f-pa-sla'),
      approx_volume: val('f-pa-volume'),
      variants: toList('f-pa-variants'),
      pain_points: toList('f-pa-painpoints'),
      why_is_it_done_this_way: toList('f-pa-why'),
      evidence_or_examples: toList('f-pa-evidence'),
      performed_in: val('f-pa-performed'),
      maturity_notes: val('f-pa-maturity'),
    };

    await API.put(`process-analysis/${encodeURIComponent(streamId)}/steps/${encodeURIComponent(stepId)}/variants/${encodeURIComponent(entityId)}`, payload);
    toast('Variant saved');
    closeModal();
    renderAnalysis(streamId);
  });
}
