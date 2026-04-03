/**
 * Decisions page — overview list and detail/review view.
 */

import { API } from '../api.js';
import {
  setContent, esc, badge, decisionBadge, classificationBadge,
  confidenceBadge, scoreBarHtml, toast,
} from '../utils.js';
import { openModal, closeModal } from '../components/modal.js';
import { textField, textArea, selectField, formRow, val } from '../components/forms.js';

const DECISIONS = [
  'centralize_now', 'centralize_later', 'harmonize_only',
  'standardize_only', 'keep_local', 'reassess_after_data_completion',
];
const OPERATING_MODELS = [
  'centralized_execution', 'central_method_local_execution',
  'federated_standardized', 'local_independent',
];

// ─── Entry point ─────────────────────────────────────────────────────────────

export async function render(id) {
  if (id) return renderDetail(id);
  return renderList();
}

// ─── Overview list ───────────────────────────────────────────────────────────

async function renderList() {
  const [streams, assessments, reviews] = await Promise.all([
    API.get('streams'),
    API.get('assessments'),
    API.get('reviews'),
  ]);

  const streamAssessments = assessments.filter(a => a.assessed_object_type === 'stream');
  const assessMap = Object.fromEntries(streamAssessments.map(a => [a.assessed_object_id, a]));
  const reviewMap = Object.fromEntries(reviews.map(r => [r.stream_id, r]));

  // Only show streams that have a stream-level assessment
  const assessed = streams.filter(s => assessMap[s.id]);

  // Try to compute decisions for assessed streams (best effort)
  const decisionResults = {};
  await Promise.allSettled(
    assessed.map(async s => {
      try {
        decisionResults[s.id] = await API.post(`decisions/compute/${encodeURIComponent(s.id)}`);
      } catch { /* skip if computation fails */ }
    })
  );

  const rows = assessed.map(s => {
    const dr = decisionResults[s.id];
    const rv = reviewMap[s.id];
    const ass = assessMap[s.id];

    const reviewStatus = rv?.review_status || 'pending';
    const reviewStatusCls = {
      draft: 'badge-warning', completed: 'badge-info', reviewed: 'badge-success', pending: 'badge-muted',
    };
    const overrideFlag = rv?.override_applied
      ? badge('badge-danger', 'override')
      : '';

    return `<tr class="clickable decision-row"
                data-status="${esc(reviewStatus)}"
                data-decision="${esc(dr?.decision || '')}"
                onclick="location.hash='#/decisions/${encodeURIComponent(s.id)}'">
      <td><strong>${esc(s.name)}</strong>
        <br><code style="font-size:11px;color:var(--text-muted)">${esc(s.id)}</code></td>
      <td>${dr ? decisionBadge(dr.decision) : badge('badge-muted', 'not computed')}</td>
      <td>${rv?.reviewed_decision ? decisionBadge(rv.reviewed_decision) : '<span style="color:var(--text-muted)">--</span>'}</td>
      <td>${overrideFlag}</td>
      <td>${badge(reviewStatusCls[reviewStatus], reviewStatus.replace(/_/g, ' '))}</td>
      <td>${dr?.priority ? badge('badge-info', dr.priority) : '--'}</td>
      <td>${dr?.confidence ? confidenceBadge(dr.confidence) : '--'}</td>
      <td>${dr?.target_operating_model ? badge('badge-muted', dr.target_operating_model.replace(/_/g, ' ')) : '--'}</td>
      <td style="white-space:nowrap">
        <a href="#/streams/${encodeURIComponent(s.id)}" class="btn btn-sm" onclick="event.stopPropagation()">Stream</a>
        <a href="#/assessments/${encodeURIComponent(s.id)}" class="btn btn-sm" onclick="event.stopPropagation()">Assess.</a>
      </td>
    </tr>`;
  }).join('');

  const statusOpts = '<option value="">All</option>' +
    ['pending', 'draft', 'completed', 'reviewed'].map(s =>
      `<option value="${s}">${s}</option>`
    ).join('');
  const decisionOpts = '<option value="">All</option>' +
    DECISIONS.map(d => `<option value="${d}">${d.replace(/_/g, ' ')}</option>`).join('');

  setContent(`
    <div class="page-header">
      <h1>Decisions</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:12px">${assessed.length} assessed streams</span>
      </div>
    </div>
    <div class="filters">
      <select id="filter-rstatus" onchange="window._filterDecisions()">${statusOpts}</select>
      <select id="filter-decision" onchange="window._filterDecisions()">${decisionOpts}</select>
    </div>
    ${assessed.length === 0
      ? '<div class="card card-body" style="color:var(--text-muted)">No streams have been assessed yet. <a href="#/assessments">Create assessments</a> first.</div>'
      : `<div class="card"><div class="table-wrap">
          <table><thead><tr>
            <th>Stream</th><th>Computed</th><th>Reviewed</th><th>Override</th>
            <th>Review Status</th><th>Priority</th><th>Confidence</th><th>Operating Model</th><th></th>
          </tr></thead><tbody id="decisions-body">${rows}</tbody></table>
        </div></div>`}
  `);
}

window._filterDecisions = function () {
  const status = document.getElementById('filter-rstatus')?.value || '';
  const decision = document.getElementById('filter-decision')?.value || '';
  document.querySelectorAll('#decisions-body .decision-row').forEach(row => {
    const ok = (!status || row.dataset.status === status)
            && (!decision || row.dataset.decision === decision);
    row.style.display = ok ? '' : 'none';
  });
};

// ─── Detail view ─────────────────────────────────────────────────────────────

async function renderDetail(streamId) {
  let stream, review, decision;

  try {
    [stream, review] = await Promise.all([
      API.get(`streams/${encodeURIComponent(streamId)}`),
      API.get(`decisions/${encodeURIComponent(streamId)}`),
    ]);
  } catch (e) {
    setContent(`<div class="card card-body" style="color:var(--danger)">
      Failed to load decision data: ${esc(e.message)}
    </div>`);
    return;
  }

  // Compute decision
  try {
    decision = await API.post(`decisions/compute/${encodeURIComponent(streamId)}`);
  } catch {
    // Decision computation may fail if assessment is incomplete
    decision = null;
  }

  const rv = review?.review || null;

  const reviewStatus = rv?.review_status || 'pending';
  const reviewStatusCls = {
    draft: 'badge-warning', completed: 'badge-info', reviewed: 'badge-success', pending: 'badge-muted',
  };

  setContent(`
    <div class="detail-header">
      <div>
        <h1>Decision: ${esc(stream.name)}</h1>
        <div class="detail-meta">
          ${badge('badge-info', stream.stream_type || '---')}
          ${badge(reviewStatusCls[reviewStatus], 'review: ' + reviewStatus.replace(/_/g, ' '))}
          ${rv?.override_applied ? badge('badge-danger', 'override applied') : ''}
        </div>
      </div>
      <div class="actions">
        <a href="#/decisions" class="btn">&larr; Decisions</a>
        <a href="#/streams/${encodeURIComponent(streamId)}" class="btn">View Stream</a>
        <a href="#/assessments/${encodeURIComponent(streamId)}" class="btn">View Assessment</a>
        <button class="btn btn-primary" id="btn-edit-review">Edit Review</button>
      </div>
    </div>

    <div class="grid-2">
      <div>
        ${_renderComputedDecision(decision)}
        ${_renderHarmonizationDegree(decision)}
        ${_renderAlternatives(decision)}
        ${_renderNoActionImpact(decision)}
      </div>
      <div>
        ${_renderReviewState(rv)}
        ${_renderGovernance(decision)}
        ${_renderEffort(decision)}
        ${_renderDecisionTrace(decision)}
      </div>
    </div>
  `);

  document.getElementById('btn-edit-review').addEventListener('click', () => {
    openReviewForm(streamId, rv, decision);
  });
}

// ─── Computed decision section ───────────────────────────────────────────────

function _renderComputedDecision(d) {
  if (!d) {
    return `<div class="detail-section">
      <h3>Computed Decision</h3>
      <p style="color:var(--text-muted)">Decision could not be computed. Ensure the stream has a completed assessment.</p>
    </div>`;
  }

  const blockingList = (d.blocking_factors || []).length
    ? d.blocking_factors.map(b => `<li>${esc(b)}</li>`).join('')
    : '<li style="color:var(--text-muted)">None</li>';

  const prereqList = (d.prerequisites || []).length
    ? d.prerequisites.map(p => `<li>${esc(p)}</li>`).join('')
    : '<li style="color:var(--text-muted)">None</li>';

  return `<div class="detail-section">
    <h3>Computed Decision</h3>
    <dl class="key-value">
      <dt>Recommendation</dt><dd>${decisionBadge(d.decision)}</dd>
      <dt>Rationale</dt><dd>${esc(d.decision_rationale || '---')}</dd>
      <dt>Operating Model</dt><dd>${badge('badge-info', (d.target_operating_model || '---').replace(/_/g, ' '))}</dd>
      <dt>Score</dt><dd>${scoreBarHtml(d.score)}</dd>
      <dt>Classification</dt><dd>${classificationBadge(d.classification)}</dd>
      ${d.confidence ? `<dt>Confidence</dt><dd>${confidenceBadge(d.confidence)}</dd>` : ''}
      ${d.priority ? `<dt>Priority</dt><dd>${badge('badge-info', d.priority)}</dd>` : ''}
      ${d.completeness_score != null ? `<dt>Completeness</dt><dd>${scoreBarHtml(d.completeness_score, 1)}</dd>` : ''}
      <dt>Expected Benefit</dt><dd>${esc(d.expected_benefit || '---')}</dd>
      <dt>Implementation Risk</dt><dd>${esc(d.implementation_risk || '---')}</dd>
      <dt>Interface Complexity</dt><dd>${scoreBarHtml(d.interface_complexity, 1)}</dd>
    </dl>
    <div style="margin-top:10px">
      <strong style="font-size:12px">Blocking Factors</strong>
      <ul style="margin:4px 0 0 16px;font-size:13px">${blockingList}</ul>
    </div>
    <div style="margin-top:10px">
      <strong style="font-size:12px">Prerequisites</strong>
      <ul style="margin:4px 0 0 16px;font-size:13px">${prereqList}</ul>
    </div>
  </div>`;
}

// ─── Harmonization degree ────────────────────────────────────────────────────

function _renderHarmonizationDegree(d) {
  if (!d?.harmonization_degree) return '';
  const hd = d.harmonization_degree;

  const flag = (val, label) =>
    `<span style="margin-right:10px">${val ? '&#10003;' : '&#10007;'} ${label}</span>`;

  return `<div class="detail-section">
    <h3>Harmonization / Standardization / Centralization</h3>
    <div style="margin-bottom:8px">
      ${flag(hd.harmonizable, 'Harmonizable')}
      ${flag(hd.standardizable, 'Standardizable')}
      ${flag(hd.centralizable, 'Centralizable')}
    </div>
    <dl class="key-value">
      <dt>Harmonization Degree</dt><dd>${scoreBarHtml(hd.harmonization_degree, 1)}</dd>
      <dt>Standardization Degree</dt><dd>${scoreBarHtml(hd.standardization_degree, 1)}</dd>
      <dt>Centralization Degree</dt><dd>${scoreBarHtml(hd.centralization_degree, 1)}</dd>
    </dl>
  </div>`;
}

// ─── Alternatives ────────────────────────────────────────────────────────────

function _renderAlternatives(d) {
  if (!d?.alternative_options?.length) return '';

  const items = d.alternative_options.map(ao => `
    <div class="card" style="margin-bottom:8px;padding:10px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>${esc(ao.label)}</strong>
        ${ao.is_recommended ? badge('badge-success', 'recommended') : ''}
      </div>
      <p style="margin:4px 0;font-size:13px;color:var(--text-muted)">${esc(ao.description)}</p>
      ${ao.pros?.length ? `<div style="font-size:12px"><strong style="color:var(--success)">Pros:</strong> ${ao.pros.map(p => esc(p)).join(', ')}</div>` : ''}
      ${ao.cons?.length ? `<div style="font-size:12px"><strong style="color:var(--danger)">Cons:</strong> ${ao.cons.map(c => esc(c)).join(', ')}</div>` : ''}
      ${ao.risks?.length ? `<div style="font-size:12px"><strong>Risks:</strong> ${ao.risks.map(r => esc(r)).join(', ')}</div>` : ''}
    </div>
  `).join('');

  return `<div class="detail-section">
    <h3>Alternative Options</h3>
    ${items}
  </div>`;
}

// ─── No-action impact ────────────────────────────────────────────────────────

function _renderNoActionImpact(d) {
  if (!d?.no_action_impact) return '';
  const nai = d.no_action_impact;

  const levelBadge = (level) => {
    const cls = { low: 'badge-success', medium: 'badge-warning', high: 'badge-danger' };
    return badge(cls[level] || 'badge-muted', level || '---');
  };

  return `<div class="detail-section">
    <h3>Impact of No Action</h3>
    <dl class="key-value">
      <dt>Regulatory Risk</dt><dd>${levelBadge(nai.regulatory_risk)}</dd>
      <dt>Operational Risk</dt><dd>${levelBadge(nai.operational_risk)}</dd>
      <dt>Inefficiency Cost</dt><dd>${levelBadge(nai.inefficiency_cost)}</dd>
      <dt>Audit Exposure</dt><dd>${levelBadge(nai.audit_exposure)}</dd>
      <dt>Rationale</dt><dd style="font-size:13px">${esc(nai.rationale || '---')}</dd>
    </dl>
  </div>`;
}

// ─── Review state ────────────────────────────────────────────────────────────

function _renderReviewState(rv) {
  if (!rv) {
    return `<div class="detail-section">
      <h3>Review</h3>
      <p style="color:var(--text-muted)">No review recorded. Click "Edit Review" to begin.</p>
    </div>`;
  }

  const statusCls = { draft: 'badge-warning', completed: 'badge-info', reviewed: 'badge-success' };

  return `<div class="detail-section">
    <h3>Review</h3>
    <dl class="key-value">
      <dt>Status</dt><dd>${badge(statusCls[rv.review_status] || 'badge-muted', rv.review_status || 'draft')}</dd>
      ${rv.reviewer_name ? `<dt>Reviewer</dt><dd>${esc(rv.reviewer_name)}</dd>` : ''}
      ${rv.review_notes ? `<dt>Notes</dt><dd style="font-size:13px">${esc(rv.review_notes)}</dd>` : ''}
      ${rv.override_applied ? `
        <dt>Override</dt><dd>${badge('badge-danger', 'yes')}</dd>
        ${rv.reviewed_decision ? `<dt>Reviewed Decision</dt><dd>${decisionBadge(rv.reviewed_decision)}</dd>` : ''}
        ${rv.reviewed_operating_model ? `<dt>Reviewed TOM</dt><dd>${badge('badge-info', rv.reviewed_operating_model.replace(/_/g, ' '))}</dd>` : ''}
        <dt>Override Rationale</dt><dd style="font-size:13px">${esc(rv.override_rationale || '')}</dd>
      ` : ''}
      ${rv.reviewed_at ? `<dt>Reviewed At</dt><dd>${esc(rv.reviewed_at)}</dd>` : ''}
    </dl>
  </div>`;
}

// ─── Governance ──────────────────────────────────────────────────────────────

function _renderGovernance(d) {
  if (!d?.governance) return '';
  const g = d.governance;

  return `<div class="detail-section">
    <h3>Governance</h3>
    <dl class="key-value">
      <dt>Decision Owner</dt><dd>${esc(g.decision_owner)}</dd>
      <dt>Decision Type</dt><dd>${badge('badge-info', (g.decision_type || '').replace(/_/g, ' '))}</dd>
      <dt>Stakeholders</dt><dd>${(g.involved_stakeholders || []).map(s => esc(s)).join(', ') || '---'}</dd>
      <dt>Required Approvals</dt><dd>${(g.required_approvals || []).map(a => esc(a)).join(', ') || '---'}</dd>
    </dl>
  </div>`;
}

// ─── Effort estimate ─────────────────────────────────────────────────────────

function _renderEffort(d) {
  if (!d?.effort_estimate) return '';
  const e = d.effort_estimate;

  return `<div class="detail-section">
    <h3>Effort Estimate</h3>
    <dl class="key-value">
      <dt>Person-Months</dt><dd>${esc(e.person_months_bucket)}</dd>
      <dt>Duration</dt><dd>${badge('badge-muted', (e.implementation_duration || '').replace(/_/g, ' '))}</dd>
      <dt>Cost Category</dt><dd>${badge('badge-muted', (e.cost_category || '').replace(/_/g, ' '))}</dd>
      <dt>Rationale</dt><dd style="font-size:13px">${esc(e.rationale || '---')}</dd>
    </dl>
  </div>`;
}

// ─── Decision trace ──────────────────────────────────────────────────────────

function _renderDecisionTrace(d) {
  if (!d?.decision_trace) return '';
  const dt = d.decision_trace;

  const listOrNone = (arr) =>
    arr?.length ? arr.map(x => `<li>${esc(x)}</li>`).join('') : '<li style="color:var(--text-muted)">None</li>';

  return `<div class="detail-section">
    <h3>Decision Trace (Audit)</h3>
    <div style="font-size:13px">
      <strong>Input Factors</strong>
      <ul style="margin:2px 0 8px 16px">${listOrNone(dt.input_factors)}</ul>
      <strong>Rules Triggered</strong>
      <ul style="margin:2px 0 8px 16px">${listOrNone(dt.rules_triggered)}</ul>
      <strong>Constraints Applied</strong>
      <ul style="margin:2px 0 8px 16px">${listOrNone(dt.constraints_applied)}</ul>
      <strong>Confidence Basis</strong>
      <ul style="margin:2px 0 8px 16px">${listOrNone(dt.confidence_basis)}</ul>
    </div>
  </div>`;
}

// ─── Review form ─────────────────────────────────────────────────────────────

function openReviewForm(streamId, existingReview, decision) {
  const rv = existingReview || {};
  const isOverride = rv.override_applied || false;

  const statusOpts = [
    { value: 'draft', label: 'Draft' },
    { value: 'completed', label: 'Completed' },
    { value: 'reviewed', label: 'Reviewed' },
  ];
  const decisionOpts = [
    { value: '', label: '--- use computed ---' },
    ...DECISIONS.map(d => ({ value: d, label: d.replace(/_/g, ' ') })),
  ];
  const tomOpts = [
    { value: '', label: '--- use computed ---' },
    ...OPERATING_MODELS.map(m => ({ value: m, label: m.replace(/_/g, ' ') })),
  ];

  openModal('Edit Review', `
    ${selectField('f-rv-status', 'Review Status', statusOpts, rv.review_status || 'draft')}
    ${textField('f-rv-reviewer', 'Reviewer Name', rv.reviewer_name || '')}
    ${textArea('f-rv-notes', 'Review Notes', rv.review_notes || '')}
    <hr style="border:none;border-top:1px solid var(--border);margin:14px 0">
    <h4 style="margin:0 0 8px">Manual Override</h4>
    <div class="form-group">
      <label>
        <input type="checkbox" id="f-rv-override" ${isOverride ? 'checked' : ''}
               onchange="document.getElementById('override-fields').style.display = this.checked ? '' : 'none'">
        Apply manual override
      </label>
    </div>
    <div id="override-fields" style="display:${isOverride ? '' : 'none'}">
      ${selectField('f-rv-decision', 'Reviewed Decision', decisionOpts, rv.reviewed_decision || '')}
      ${selectField('f-rv-tom', 'Reviewed Operating Model', tomOpts, rv.reviewed_operating_model || '')}
      ${textArea('f-rv-rationale', 'Override Rationale (mandatory)', rv.override_rationale || '', { rows: 3 })}
    </div>
  `, async () => {
    const overrideApplied = document.getElementById('f-rv-override').checked;
    const payload = {
      stream_id: streamId,
      review_status: val('f-rv-status'),
      reviewer_name: val('f-rv-reviewer'),
      review_notes: val('f-rv-notes'),
      override_applied: overrideApplied,
    };

    if (overrideApplied) {
      const rd = val('f-rv-decision');
      const rt = val('f-rv-tom');
      const rationale = val('f-rv-rationale');
      if (!rationale) throw new Error('Override rationale is mandatory when override is applied.');
      if (rd) payload.reviewed_decision = rd;
      if (rt) payload.reviewed_operating_model = rt;
      payload.override_rationale = rationale;
    }

    // Add timestamp
    payload.reviewed_at = new Date().toISOString();

    await API.put('reviews', payload);
    toast('Review saved');
    closeModal();
    renderDetail(streamId);
  });
}
