/**
 * Process Analysis page — structured DE vs AT process capture per stream.
 *
 * Shows 6 default process phases, each with entity variants side-by-side.
 * Displays WHY quality, evidence strength, review status, enriched deltas,
 * recommendations, and management decision support.
 */

import { API } from '../api.js';
import { setContent, esc, badge, toast } from '../utils.js';
import { openModal, closeModal } from '../components/modal.js';
import { textField, textArea, selectField, formRow, val } from '../components/forms.js';

// ─── Constants ──────────────────────────────────────────────────────────────

const WHY_CATEGORIES = [
  'regulatory_requirement', 'legal_constraint', 'customer_specific_requirement',
  'technical_constraint', 'tooling_or_license_limitation', 'capacity_or_staffing',
  'temporary_transition_state', 'historical_growth', 'deliberate_local_optimization',
  'unknown_or_unclear',
];

const REVIEW_STATUSES = ['draft', 'captured', 'challenged', 'reviewed', 'approved'];

// ─── Badge helpers ──────────────────────────────────────────────────────────

function _whyQualityBadge(q) {
  const cls = { strong: 'badge-success', medium: 'badge-warning', weak: 'badge-danger' };
  return q ? badge(cls[q] || 'badge-muted', 'WHY: ' + q) : '';
}

function _evidenceBadge(strength, count) {
  if (!count && count !== 0) return '';
  if (count === 0) return badge('badge-danger', 'No evidence');
  const cls = { high: 'badge-success', medium: 'badge-warning', low: 'badge-danger' };
  return badge(cls[strength] || 'badge-muted', count + ' evidence (' + (strength || '?') + ')');
}

function _reviewBadge(status) {
  const cls = {
    draft: 'badge-muted', captured: 'badge-info', challenged: 'badge-warning',
    reviewed: 'badge-primary', approved: 'badge-success',
  };
  return status ? badge(cls[status] || 'badge-muted', status) : '';
}

function _recTypeBadge(type) {
  const cls = {
    harmonize: 'badge-primary', keep_local: 'badge-success', centralize: 'badge-info',
    investigate_further: 'badge-warning', remediate_control_gap: 'badge-danger',
  };
  return badge(cls[type] || 'badge-muted', (type || '').replace(/_/g, ' '));
}

function _priorityBadge(p) {
  const cls = { high: 'badge-danger', medium: 'badge-warning', low: 'badge-muted' };
  return badge(cls[p] || 'badge-muted', p);
}

function _complexityBadge(c) {
  const cls = { high: 'badge-danger', medium: 'badge-warning', low: 'badge-success' };
  return badge(cls[c] || 'badge-muted', c);
}

function _mgmtDecisionBadge(needs) {
  return needs ? `<span style="display:inline-block;font-size:10px;padding:1px 6px;border-radius:3px;background:#fbbf24;color:#78350f;font-weight:600">MGMT DECISION</span>` : '';
}

function _controlGapBadge() {
  return `<span style="display:inline-block;font-size:10px;padding:1px 6px;border-radius:3px;background:#dc2626;color:#fff;font-weight:600">CONTROL GAP</span>`;
}

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

  // Load completeness, deltas, summary (includes recommendations)
  let completeness = {}, deltas = [], summary = {};
  try {
    [completeness, deltas, summary] = await Promise.all([
      API.get(`process-analysis/${encodeURIComponent(streamId)}/completeness`),
      API.get(`process-analysis/${encodeURIComponent(streamId)}/deltas`),
      API.get(`process-analysis/${encodeURIComponent(streamId)}/summary`),
    ]);
  } catch { /* non-critical */ }

  const entities = analysis.entities || ['DE', 'AT'];
  const steps = analysis.process_steps || [];
  const stepScores = completeness.step_scores || {};
  const recs = summary.recommendations || [];

  // Build step sections
  const sections = steps.map(step => {
    const sid = step.step_id;
    const sc = stepScores[sid] || {};
    const stepDeltas = deltas.filter(d => d.step_id === sid);
    const stepRecs = recs.filter(r => (r.based_on_step_ids || []).includes(sid));
    return _renderStep(streamId, step, entities, sc, stepDeltas, stepRecs);
  }).join('');

  // Header badges
  const totalScore = completeness.score || 0;
  const missingWhys = completeness.missing_whys || 0;
  const highDeltas = deltas.filter(d => d.impact === 'high').length;
  const controlGaps = summary.control_gaps_count || 0;
  const weakWhys = summary.weak_why_count || 0;

  setContent(`
    <div class="page-header">
      <div>
        <h1>Process Analysis: ${esc(stream.name)}</h1>
        <div class="detail-meta">
          ${badge('badge-info', stream.stream_type || '---')}
          ${_completeBadge(totalScore)}
          ${missingWhys ? badge('badge-danger', missingWhys + ' missing WHY') : ''}
          ${weakWhys ? badge('badge-warning', weakWhys + ' weak WHY') : ''}
          ${highDeltas ? badge('badge-danger', highDeltas + ' high-impact deltas') : ''}
          ${controlGaps ? _controlGapBadge() : ''}
        </div>
      </div>
      <div class="actions">
        <a href="#/process-analysis" class="btn">&larr; All Analyses</a>
        <a href="#/streams/${encodeURIComponent(streamId)}" class="btn">Stream Detail</a>
      </div>
    </div>

    ${_renderSummaryCards(summary, deltas, entities, recs)}
    ${_renderRecommendationsPanel(recs)}
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

  // Wire review status selectors
  document.querySelectorAll('[data-review-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const [stepId, entityId] = btn.dataset.reviewAction.split('::');
      _openReviewStatusDialog(streamId, stepId, entityId);
    });
  });
}

function _completeBadge(score) {
  if (score >= 80) return badge('badge-success', score + '% complete');
  if (score >= 50) return badge('badge-warning', score + '% complete');
  return badge('badge-danger', score + '% complete');
}

// ─── Summary cards ───────────────────────────────────────────────────────────

function _renderSummaryCards(summary, deltas, entities, recs) {
  const s = summary;
  const high = deltas.filter(d => d.impact === 'high').length;
  const tendencyLabel = {
    harmonizable: 'Harmonizable', partially_harmonizable: 'Partially harmonizable',
    strongly_local: 'Strongly local', insufficiently_captured: 'Insufficiently captured',
  };
  const tendencyCls = {
    harmonizable: 'badge-success', partially_harmonizable: 'badge-warning',
    strongly_local: 'badge-info', insufficiently_captured: 'badge-danger',
  };

  const _stat = (value, label, danger, accent) => {
    const borderStyle = danger ? 'border-color:var(--danger)' : accent ? 'border-color:#facc15' : '';
    const colorStyle = danger ? 'color:var(--danger)' : accent ? 'color:#92400e' : '';
    return `<div class="stat-card" ${borderStyle ? `style="${borderStyle}"` : ''}>
      <div class="stat-value" ${colorStyle ? `style="${colorStyle}"` : ''}>${value}</div>
      <div class="stat-label">${label}</div>
    </div>`;
  };

  const controlGaps = s.control_gaps_count || 0;
  const mgmtDecisions = s.management_decisions_needed_count || 0;
  const evGaps = s.evidence_gaps_count || 0;
  const weakWhy = s.weak_why_count || 0;

  // Critical issues row (decision-relevant)
  const criticalRow = (controlGaps || mgmtDecisions || evGaps || weakWhy) ? `
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px">
      ${controlGaps ? _stat(controlGaps, 'Control Gaps', true) : ''}
      ${mgmtDecisions ? _stat(mgmtDecisions, 'Mgmt Decisions Needed', true) : ''}
      ${evGaps ? _stat(evGaps, 'Evidence Gaps', false, true) : ''}
      ${weakWhy ? _stat(weakWhy, 'Weak WHY', false, true) : ''}
    </div>` : '';

  return `
    <!-- Tendency + key metrics -->
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;align-items:stretch">
      <div class="stat-card" style="min-width:160px">
        <div class="stat-value" style="font-size:14px">${badge(tendencyCls[s.tendency] || 'badge-muted', tendencyLabel[s.tendency] || s.tendency || '---')}</div>
        <div class="stat-label">Overall Tendency</div>
      </div>
      ${_stat((s.completeness_score || 0) + '%', 'Completeness')}
      ${_stat(high, 'High-Impact Deltas', high > 0)}
      ${_stat(s.standardization_candidates_count || 0, 'Harmonize Candidates')}
      ${_stat(s.likely_keep_local_count || 0, 'Keep Local')}
    </div>

    <!-- Critical issues (only shown if any exist) -->
    ${criticalRow}

    <!-- Decision focus -->
    ${_renderDecisionFocus(s, deltas)}

    <!-- Open gaps -->
    ${_renderOpenGaps(s.open_gaps || [])}`;
}

function _renderDecisionFocus(summary, deltas) {
  const recs = summary.recommendations || [];
  const harmonize = recs.filter(r => r.recommendation_type === 'harmonize' && r.priority === 'high');
  const blockers = recs.filter(r => (r.blockers || []).length > 0);
  const investigate = recs.filter(r => r.recommendation_type === 'investigate_further');
  const remediate = recs.filter(r => r.recommendation_type === 'remediate_control_gap');

  if (!harmonize.length && !blockers.length && !investigate.length && !remediate.length) return '';

  return `<div class="card" style="margin-bottom:12px;border-color:#3b82f6">
    <div class="card-header" style="background:#eff6ff;font-size:12px;font-weight:600;color:#1d4ed8">
      Decision Focus
    </div>
    <div class="card-body" style="padding:8px 12px;font-size:12px">
      ${harmonize.length ? `<div style="margin-bottom:6px"><strong>Top harmonization opportunities:</strong>
        ${harmonize.slice(0, 3).map(r => `<div style="padding:2px 0">${_recTypeBadge(r.recommendation_type)} ${_priorityBadge(r.priority)} ${esc(r.title)}</div>`).join('')}</div>` : ''}
      ${remediate.length ? `<div style="margin-bottom:6px"><strong>Control gaps to remediate:</strong>
        ${remediate.slice(0, 3).map(r => `<div style="padding:2px 0">${_controlGapBadge()} ${esc(r.title)}</div>`).join('')}</div>` : ''}
      ${investigate.length ? `<div style="margin-bottom:6px"><strong>Needs investigation:</strong>
        ${investigate.slice(0, 3).map(r => `<div style="padding:2px 0">${_recTypeBadge(r.recommendation_type)} ${esc(r.title)}</div>`).join('')}</div>` : ''}
      ${blockers.length ? `<div><strong>Blocked recommendations:</strong>
        ${blockers.slice(0, 3).map(r => `<div style="padding:2px 0;color:var(--danger)">${esc(r.title)}: ${r.blockers.map(b => esc(b)).join(', ')}</div>`).join('')}</div>` : ''}
    </div>
  </div>`;
}

function _renderOpenGaps(gaps) {
  if (!gaps.length) return '';
  return `<div class="card" style="margin-bottom:16px;border-color:var(--warning)">
    <div class="card-header" style="background:#fffbeb;font-size:12px;font-weight:600;color:#92400e">
      Open Evidence &amp; Review Gaps (Top 5)
    </div>
    <div class="card-body" style="padding:8px 12px">
      ${gaps.map(g => `<div style="font-size:12px;padding:4px 0;border-bottom:1px solid var(--border);cursor:pointer" onclick="document.getElementById('step-${esc(g.step_id)}')?.scrollIntoView({behavior:'smooth',block:'start'})">
        <strong>${esc(g.step_name)}</strong> / ${esc(g.entity_id)}:
        ${g.issues.map(i => {
          const cls = i === 'no evidence' ? 'badge-danger' : i.includes('weak') ? 'badge-danger' : 'badge-warning';
          return badge(cls, i);
        }).join(' ')}
        <span style="font-size:10px;color:var(--text-muted);margin-left:4px">click to scroll</span>
      </div>`).join('')}
    </div>
  </div>`;
}

// ─── Single process step ─────────────────────────────────────────────────────

function _renderStep(streamId, step, entities, scores, stepDeltas, stepRecs) {
  const sid = step.step_id;
  const variants = step.entity_variants || [];
  const avgScore = scores.score || 0;
  const hasControlGap = stepDeltas.some(d => d.delta_type === 'control_gap');
  const hasMgmtDecision = stepDeltas.some(d => d.needs_management_decision);

  // Entity columns side by side
  const cols = entities.map(eid => {
    const v = variants.find(x => x.entity_id === eid) || {};
    const es = (scores.entity_scores || {})[eid] || {};
    return _renderVariantCol(streamId, sid, eid, v, es);
  }).join('');

  // Enriched deltas
  const deltaRows = stepDeltas.length ? `
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">
      <strong style="font-size:11px;color:var(--text-muted);text-transform:uppercase">Detected Differences</strong>
      <table style="width:100%;border-collapse:collapse;margin-top:6px;font-size:12px">
        <thead><tr style="text-align:left;border-bottom:1px solid var(--border)">
          <th style="padding:3px 6px;font-size:10px;color:var(--text-muted)">Impact</th>
          <th style="padding:3px 6px;font-size:10px;color:var(--text-muted)">Type</th>
          <th style="padding:3px 6px;font-size:10px;color:var(--text-muted)">Dimension</th>
          <th style="padding:3px 6px;font-size:10px;color:var(--text-muted)">Nature</th>
          <th style="padding:3px 6px;font-size:10px;color:var(--text-muted)">Description</th>
          <th style="padding:3px 6px;font-size:10px;color:var(--text-muted)">Flags</th>
        </tr></thead>
        <tbody>${stepDeltas.map(d => `<tr style="border-bottom:1px solid #f3f4f6${d.delta_type === 'control_gap' ? ';background:#fef2f2' : ''}">
          <td style="padding:3px 6px">${_impactBadge(d.impact)}</td>
          <td style="padding:3px 6px">${_deltaTypeBadge(d.delta_type)}</td>
          <td style="padding:3px 6px">${_dimBadge(d.delta_dimension)}</td>
          <td style="padding:3px 6px">${_natureBadge(d.delta_nature)}</td>
          <td style="padding:3px 6px">${esc(d.description)}</td>
          <td style="padding:3px 6px;white-space:nowrap">
            ${d.delta_type === 'control_gap' ? _controlGapBadge() : ''}
            ${d.needs_management_decision ? _mgmtDecisionBadge(true) : ''}
            ${d.constraint_type && d.constraint_type !== 'none' ? badge('badge-info', d.constraint_type) : ''}
          </td>
        </tr>`).join('')}</tbody>
      </table>
    </div>` : '';

  // Per-step recommendations (compact)
  const recRows = (stepRecs || []).length ? `
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">
      <strong style="font-size:11px;color:var(--text-muted);text-transform:uppercase">Recommendations for this step</strong>
      ${stepRecs.map(r => `<div style="display:flex;gap:6px;align-items:center;margin-top:4px;font-size:12px">
        ${_recTypeBadge(r.recommendation_type)} ${_priorityBadge(r.priority)}
        <span>${esc(r.title)}</span>
      </div>`).join('')}
    </div>` : '';

  return `<div class="card" id="step-${esc(sid)}" style="margin-bottom:16px${hasControlGap ? ';border-left:3px solid var(--danger)' : ''}">
    <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
      <span>
        <strong>${esc(step.sort_order)}. ${esc(step.step_name)}</strong>
        ${hasControlGap ? _controlGapBadge() : ''}
        ${hasMgmtDecision ? _mgmtDecisionBadge(true) : ''}
      </span>
      <span>${_completeBadge(avgScore)}</span>
    </div>
    <div class="card-body">
      <div style="display:flex;gap:16px;flex-wrap:wrap">
        ${cols}
      </div>
      ${deltaRows}
      ${recRows}
    </div>
  </div>`;
}

function _impactBadge(impact) {
  const cls = { high: 'badge-danger', medium: 'badge-warning', low: 'badge-success' };
  return badge(cls[impact] || 'badge-muted', impact);
}

function _deltaTypeBadge(dtype) {
  const labels = {
    system_difference: 'System', channel_difference: 'Channel',
    role_difference: 'Role', variant_difference: 'Variant',
    missing_rationale: 'Missing WHY', control_gap: 'Control Gap',
  };
  const bg = dtype === 'control_gap' ? '#dc2626' : '#f3f4f6';
  const fg = dtype === 'control_gap' ? '#fff' : 'var(--text-muted)';
  return `<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:${bg};color:${fg}">${labels[dtype] || dtype}</span>`;
}

function _dimBadge(dim) {
  if (!dim) return '';
  return `<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:#e0e7ff;color:#3730a3">${esc(dim)}</span>`;
}

function _natureBadge(nature) {
  if (!nature) return '';
  const colors = {
    cosmetic: '#d1fae5', procedural: '#dbeafe',
    operationally_significant: '#fef3c7', control_relevant: '#fee2e2',
    potentially_blocking: '#fce7f3',
  };
  const fg = {
    cosmetic: '#065f46', procedural: '#1e40af',
    operationally_significant: '#92400e', control_relevant: '#991b1b',
    potentially_blocking: '#9d174d',
  };
  return `<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:${colors[nature] || '#f3f4f6'};color:${fg[nature] || 'var(--text-muted)'}">${esc((nature || '').replace(/_/g, ' '))}</span>`;
}

// ─── Entity variant column ───────────────────────────────────────────────────

function _renderVariantCol(streamId, stepId, entityId, v, scores) {
  const score = scores.score || 0;
  const warnings = scores.warnings || [];
  const missingFields = scores.missing_fields || [];
  const whyQuality = scores.why_quality || v.why_quality || '';
  const evStrength = scores.evidence_strength || v.evidence_strength || 'none';
  const evCount = scores.evidence_count != null ? scores.evidence_count : (v.evidence_references || []).length;
  const reviewStatus = scores.review_status || v.review_status || 'draft';

  const list = (items, fallback) => {
    if (!items || !items.length) return `<span style="color:var(--text-muted)">${fallback || '---'}</span>`;
    return items.map(i => {
      if (typeof i === 'object' && i.role) return `${esc(i.role)} (${esc(i.responsibility || '')})`;
      return esc(String(i));
    }).join(', ');
  };

  const whyItems = v.why_is_it_done_this_way || [];
  const hasWhy = Array.isArray(whyItems) ? whyItems.some(w => String(w).trim()) : Boolean(whyItems);
  const whyCats = (v.why_categories || []);

  // WHY section background based on quality
  const whyBg = !hasWhy ? '#fef2f2' : whyQuality === 'weak' ? '#fefce8' : '';
  const whyBorder = !hasWhy ? 'var(--danger)' : whyQuality === 'weak' ? '#facc15' : 'transparent';

  // Evidence references (structured)
  const evRefs = v.evidence_references || [];
  const legacyEv = v.evidence_or_examples || [];

  // Review metadata
  const reviewComment = v.review_comment || '';
  const reviewedBy = v.reviewed_by || '';
  const reviewedAt = v.reviewed_at || '';

  return `<div style="flex:1;min-width:280px;border:1px solid var(--border);border-radius:6px;padding:10px">
    <!-- Header: entity + score + actions -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <strong>${esc(entityId)}</strong>
      <div style="display:flex;gap:4px;align-items:center">
        ${_completeBadge(score)}
        <button class="btn btn-sm" data-edit-variant="${esc(stepId)}::${esc(entityId)}">Edit</button>
      </div>
    </div>

    <!-- Status badges row -->
    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px">
      ${_reviewBadge(reviewStatus)}
      ${hasWhy ? _whyQualityBadge(whyQuality) : badge('badge-danger', 'WHY missing')}
      ${_evidenceBadge(evStrength, evCount)}
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

    <!-- WHY section -->
    <div style="margin-top:8px;font-size:12px;padding:4px 8px;border-radius:4px;${whyBg ? 'background:' + whyBg + ';' : ''}${whyBorder !== 'transparent' ? 'border:1px solid ' + whyBorder : ''}">
      <strong style="color:${hasWhy ? 'inherit' : 'var(--danger)'}">WHY:</strong>
      ${hasWhy
        ? `<span>${list(whyItems)}</span>`
        : '<span style="color:var(--danger)"> Not documented</span>'}
      ${whyCats.length ? `<div style="margin-top:3px">${whyCats.map(c => `<span style="font-size:10px;padding:1px 5px;border-radius:3px;background:#e8e8e8;margin-right:3px">${esc(c.replace(/_/g, ' '))}</span>`).join('')}</div>` : ''}
      ${v.why_review_note ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;font-style:italic">${esc(v.why_review_note)}</div>` : ''}
    </div>

    <!-- Evidence section -->
    <div style="margin-top:6px;font-size:11px">
      <strong>Evidence:</strong>
      ${evRefs.length ? evRefs.map(e =>
        `<div style="padding:2px 0"><span style="font-size:10px;padding:1px 4px;border-radius:3px;background:#dbeafe;color:#1e40af;margin-right:4px">${esc(e.type || 'other')}</span>${esc(e.title || '')}${e.confidence ? ' <span style="color:var(--text-muted)">(' + esc(e.confidence) + ')</span>' : ''}</div>`
      ).join('') : legacyEv.length ? list(legacyEv) : '<span style="color:var(--danger)">none</span>'}
    </div>

    ${(v.pain_points||[]).length ? `<div style="margin-top:4px;font-size:11px"><strong>Pain Points:</strong> ${list(v.pain_points)}</div>` : ''}

    <!-- Review metadata -->
    ${reviewComment || reviewedBy ? `<div style="margin-top:6px;font-size:11px;padding:4px 8px;background:#f8fafc;border-radius:4px;border:1px solid var(--border)">
      ${reviewComment ? `<div><strong>Review:</strong> ${esc(reviewComment)}</div>` : ''}
      ${reviewedBy ? `<div style="color:var(--text-muted)">by ${esc(reviewedBy)}${reviewedAt ? ' on ' + esc(reviewedAt) : ''}</div>` : ''}
    </div>` : ''}

    <!-- Review action -->
    <div style="margin-top:6px;text-align:right">
      <button class="btn btn-sm" data-review-action="${esc(stepId)}::${esc(entityId)}" style="font-size:11px">Review Status</button>
    </div>

    ${warnings.length ? `<div style="margin-top:4px">${warnings.map(w => `<div style="font-size:11px;color:var(--warning)">&#9888; ${esc(w)}</div>`).join('')}</div>` : ''}
  </div>`;
}

// ─── Recommendations panel ──────────────────────────────────────────────────

function _renderRecommendationsPanel(recs) {
  if (!recs || !recs.length) return '';

  // Group by type for visual clarity
  const byPriority = { high: [], medium: [], low: [] };
  recs.forEach(r => (byPriority[r.priority] || byPriority.medium).push(r));
  const ordered = [...byPriority.high, ...byPriority.medium, ...byPriority.low];

  return `<div class="card" style="margin-bottom:20px">
    <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
      <strong>Recommendations (${recs.length})</strong>
      <div style="display:flex;gap:6px">
        ${badge('badge-danger', byPriority.high.length + ' high')}
        ${badge('badge-warning', byPriority.medium.length + ' medium')}
        ${badge('badge-muted', byPriority.low.length + ' low')}
      </div>
    </div>
    <div class="card-body" style="padding:0">
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="background:#f8fafc;border-bottom:1px solid var(--border)">
          <th style="padding:6px 10px;text-align:left;font-size:10px;color:var(--text-muted)">Priority</th>
          <th style="padding:6px 10px;text-align:left;font-size:10px;color:var(--text-muted)">Type</th>
          <th style="padding:6px 10px;text-align:left;font-size:10px;color:var(--text-muted)">Title</th>
          <th style="padding:6px 10px;text-align:left;font-size:10px;color:var(--text-muted)">Steps</th>
          <th style="padding:6px 10px;text-align:left;font-size:10px;color:var(--text-muted)">Complexity</th>
        </tr></thead>
        <tbody>
          ${ordered.map(r => `<tr style="border-bottom:1px solid #f3f4f6;cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'':'none'">
            <td style="padding:6px 10px">${_priorityBadge(r.priority)}</td>
            <td style="padding:6px 10px">${_recTypeBadge(r.recommendation_type)}</td>
            <td style="padding:6px 10px"><strong>${esc(r.title)}</strong></td>
            <td style="padding:6px 10px">${(r.based_on_step_ids||[]).map(s => badge('badge-muted', s)).join(' ')}</td>
            <td style="padding:6px 10px">${_complexityBadge(r.implementation_complexity)}</td>
          </tr>
          <tr style="display:none;background:#f8fafc">
            <td colspan="5" style="padding:8px 10px 8px 24px;font-size:11px">
              <div><strong>Rationale:</strong> ${esc(r.rationale)}</div>
              <div><strong>Expected benefit:</strong> ${esc(r.expected_benefit)}</div>
              ${(r.assumptions||[]).length ? `<div><strong>Assumptions:</strong> ${r.assumptions.map(a => esc(a)).join('; ')}</div>` : ''}
              ${(r.blockers||[]).length ? `<div style="color:var(--danger)"><strong>Blockers:</strong> ${r.blockers.map(b => esc(b)).join('; ')}</div>` : ''}
            </td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
  </div>`;
}

// ─── Review status dialog (validate + apply) ───────────────────────────────

async function _openReviewStatusDialog(streamId, stepId, entityId) {
  const statusOptions = REVIEW_STATUSES.map(s =>
    `<option value="${s}">${s}</option>`
  ).join('');

  openModal(`Review Status: ${esc(stepId)} / ${esc(entityId)}`, `
    <div style="margin-bottom:10px">
      <label style="font-weight:600;font-size:13px">Target Review Status</label>
      <select class="form-control" id="f-review-status" style="margin-top:4px">
        ${statusOptions}
      </select>
    </div>
    ${textField('f-review-comment', 'Review Comment (optional)', '')}
    ${textField('f-review-by', 'Reviewed By (optional)', '')}
    <div style="display:flex;gap:8px;margin:12px 0">
      <button class="btn" id="btn-validate-review">Check First</button>
      <button class="btn btn-primary" id="btn-apply-review">Apply Transition</button>
    </div>
    <div id="review-validation-result"></div>
  `, null);

  // Validate only
  document.getElementById('btn-validate-review')?.addEventListener('click', async () => {
    const newStatus = document.getElementById('f-review-status')?.value;
    const resultDiv = document.getElementById('review-validation-result');
    if (!resultDiv) return;
    resultDiv.innerHTML = '<span style="color:var(--text-muted)">Validating...</span>';
    try {
      const result = await API.post(
        `process-analysis/${encodeURIComponent(streamId)}/validate-review-status`,
        { step_id: stepId, entity_id: entityId, new_status: newStatus }
      );
      if (result.allowed) {
        resultDiv.innerHTML = `<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:6px;padding:10px;font-size:13px">
          <strong style="color:#166534">Allowed.</strong> Transition to <strong>${esc(newStatus)}</strong> is valid. Click <em>Apply Transition</em> to persist.
        </div>`;
      } else {
        resultDiv.innerHTML = `<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:6px;padding:10px;font-size:13px">
          <strong style="color:#991b1b">Blocked.</strong>
          ${(result.reasons||[]).map(r => `<div style="margin-top:4px">${esc(r)}</div>`).join('')}
          ${(result.missing_prerequisites||[]).length ? `<div style="margin-top:6px"><strong>Missing:</strong><ul style="margin:4px 0 0 16px">${result.missing_prerequisites.map(m => `<li>${esc(m)}</li>`).join('')}</ul></div>` : ''}
        </div>`;
      }
    } catch (e) {
      resultDiv.innerHTML = `<div style="color:var(--danger)">Error: ${esc(e.message)}</div>`;
    }
  });

  // Apply transition (validate + persist)
  document.getElementById('btn-apply-review')?.addEventListener('click', async () => {
    const newStatus = document.getElementById('f-review-status')?.value;
    const comment = val('f-review-comment');
    const reviewedBy = val('f-review-by');
    const resultDiv = document.getElementById('review-validation-result');
    if (!resultDiv) return;
    resultDiv.innerHTML = '<span style="color:var(--text-muted)">Applying...</span>';
    try {
      const result = await API.post(
        `process-analysis/${encodeURIComponent(streamId)}/apply-review-status`,
        { step_id: stepId, entity_id: entityId, new_status: newStatus,
          review_comment: comment, reviewed_by: reviewedBy }
      );
      toast(`Review status updated to: ${result.new_status}`);
      closeModal();
      renderAnalysis(streamId);
    } catch (e) {
      // HTTP 400 = blocked transition
      let detail = e.message || 'Unknown error';
      resultDiv.innerHTML = `<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:6px;padding:10px;font-size:13px">
        <strong style="color:#991b1b">Blocked.</strong>
        <div style="margin-top:4px">${esc(detail)}</div>
      </div>`;
    }
  });
}

// ─── Evidence sub-form helpers ───────────────────────────────────────────────

const _EV_TYPES = ['interview', 'document', 'ticket_example', 'sop', 'policy', 'system_screenshot', 'other'];
const _EV_CONF = ['high', 'medium', 'low'];

function _evidenceRowHtml(idx, e, types, conf) {
  e = e || {};
  const typeOpts = (types || _EV_TYPES).map(t => `<option value="${t}" ${t === (e.type || '') ? 'selected' : ''}>${t}</option>`).join('');
  const confOpts = (conf || _EV_CONF).map(c => `<option value="${c}" ${c === (e.confidence || 'medium') ? 'selected' : ''}>${c}</option>`).join('');
  return `<div class="ev-row" style="border:1px solid #bae6fd;border-radius:4px;padding:8px;margin-bottom:6px;background:#fff">
    <div style="display:flex;gap:6px;margin-bottom:4px">
      <div style="flex:1"><label style="font-size:10px;color:var(--text-muted)">Type</label><select class="form-control ev-type" style="font-size:12px">${typeOpts}</select></div>
      <div style="flex:2"><label style="font-size:10px;color:var(--text-muted)">Title</label><input class="form-control ev-title" style="font-size:12px" value="${esc(e.title || '')}"></div>
      <div style="flex:1"><label style="font-size:10px;color:var(--text-muted)">Confidence</label><select class="form-control ev-conf" style="font-size:12px">${confOpts}</select></div>
      <div style="display:flex;align-items:end"><button type="button" class="btn btn-sm ev-remove" style="font-size:11px;color:var(--danger)">Remove</button></div>
    </div>
    <div style="display:flex;gap:6px;margin-bottom:4px">
      <div style="flex:1"><label style="font-size:10px;color:var(--text-muted)">Source</label><input class="form-control ev-source" style="font-size:12px" value="${esc(e.source || '')}"></div>
      <div style="flex:1"><label style="font-size:10px;color:var(--text-muted)">Collected By</label><input class="form-control ev-collected-by" style="font-size:12px" value="${esc(e.collected_by || '')}"></div>
      <div style="flex:1"><label style="font-size:10px;color:var(--text-muted)">Date Collected</label><input class="form-control ev-date" style="font-size:12px" type="date" value="${esc(e.date_collected || '')}"></div>
    </div>
    <div><label style="font-size:10px;color:var(--text-muted)">Reference Detail</label><input class="form-control ev-detail" style="font-size:12px" value="${esc(e.reference_detail || '')}"></div>
  </div>`;
}

function _wireEvidenceControls(stepId, entityId) {
  // Add evidence button
  document.getElementById('btn-add-evidence')?.addEventListener('click', () => {
    const container = document.getElementById('evidence-container');
    if (!container) return;
    const emptyMsg = document.getElementById('ev-empty-msg');
    if (emptyMsg) emptyMsg.remove();
    const count = container.querySelectorAll('.ev-row').length;
    container.insertAdjacentHTML('beforeend', _evidenceRowHtml(count, {}, _EV_TYPES, _EV_CONF));
    _wireEvidenceRemoveButtons();
  });
  _wireEvidenceRemoveButtons();
}

function _wireEvidenceRemoveButtons() {
  document.querySelectorAll('.ev-remove').forEach(btn => {
    btn.onclick = () => btn.closest('.ev-row')?.remove();
  });
}

function _collectEvidenceRefs(stepId, entityId) {
  const rows = document.querySelectorAll('#evidence-container .ev-row');
  return [...rows].map((row, i) => ({
    id: `ev_${stepId}_${entityId}_${i + 1}`,
    type: row.querySelector('.ev-type')?.value || 'other',
    title: row.querySelector('.ev-title')?.value?.trim() || '',
    source: row.querySelector('.ev-source')?.value?.trim() || '',
    reference_detail: row.querySelector('.ev-detail')?.value?.trim() || '',
    date_collected: row.querySelector('.ev-date')?.value || '',
    collected_by: row.querySelector('.ev-collected-by')?.value?.trim() || '',
    confidence: row.querySelector('.ev-conf')?.value || 'medium',
  })).filter(e => e.title);  // Drop rows with no title
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

  // WHY categories checkboxes
  const whyCatChecks = WHY_CATEGORIES.map(c => {
    const checked = (v.why_categories || []).includes(c) ? 'checked' : '';
    return `<label style="display:inline-flex;align-items:center;gap:4px;margin:2px 8px 2px 0;font-size:12px">
      <input type="checkbox" class="f-pa-whycat" value="${c}" ${checked}> ${c.replace(/_/g, ' ')}
    </label>`;
  }).join('');

  // Evidence references — structured sub-form
  const evTypes = ['interview', 'document', 'ticket_example', 'sop', 'policy', 'system_screenshot', 'other'];
  const evConf = ['high', 'medium', 'low'];
  const existingEvRefs = v.evidence_references || [];

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

      <div style="margin-top:8px">
        <label style="font-weight:600;font-size:12px;color:#991b1b">WHY Categories (select all that apply)</label>
        <div style="margin-top:4px">${whyCatChecks}</div>
      </div>

      ${formRow(
        selectField('f-pa-whyquality', 'WHY Quality', ['', 'strong', 'medium', 'weak'], v.why_quality || ''),
        textField('f-pa-whynote', 'WHY Review Note', v.why_review_note || '')
      )}
    </div>

    ${textArea('f-pa-painpoints', 'Pain Points (one per line)', j(v.pain_points), { rows: 2 })}

    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;padding:10px 14px;margin:12px 0">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <label style="font-weight:600;font-size:13px;color:#0369a1">Evidence References</label>
        <button type="button" class="btn btn-sm" id="btn-add-evidence" style="font-size:11px">+ Add Evidence</button>
      </div>
      <div id="evidence-container">
        ${existingEvRefs.map((e, i) => _evidenceRowHtml(i, e, evTypes, evConf)).join('')}
      </div>
      ${existingEvRefs.length === 0 ? '<p id="ev-empty-msg" style="font-size:11px;color:var(--text-muted);margin:4px 0">No evidence references yet. Click "+ Add Evidence" to add one.</p>' : ''}
      ${textArea('f-pa-evidence', 'Legacy Evidence / Examples (one per line)', j(v.evidence_or_examples), { rows: 2 })}
    </div>

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

    // Parse WHY categories from checkboxes
    const whyCats = [...document.querySelectorAll('.f-pa-whycat:checked')].map(cb => cb.value);

    // Collect structured evidence references
    const evRefs = _collectEvidenceRefs(stepId, entityId);

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
      why_categories: whyCats,
      why_quality: val('f-pa-whyquality'),
      why_review_note: val('f-pa-whynote'),
      evidence_or_examples: toList('f-pa-evidence'),
      evidence_references: evRefs,
      performed_in: val('f-pa-performed'),
      maturity_notes: val('f-pa-maturity'),
    };

    await API.put(`process-analysis/${encodeURIComponent(streamId)}/steps/${encodeURIComponent(stepId)}/variants/${encodeURIComponent(entityId)}`, payload);
    toast('Variant saved');
    closeModal();
    renderAnalysis(streamId);
  });

  // Wire evidence sub-form controls after modal is rendered
  _wireEvidenceControls(stepId, entityId);
}
