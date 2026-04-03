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
      <td>${dr ? decisionBadge(dr.decision) : badge('badge-muted', 'nicht berechnet')}</td>
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

  const statusOpts = '<option value="">Alle</option>' +
    ['pending', 'draft', 'completed', 'reviewed'].map(s =>
      `<option value="${s}">${s}</option>`
    ).join('');
  const decisionOpts = '<option value="">Alle</option>' +
    DECISIONS.map(d => `<option value="${d}">${d.replace(/_/g, ' ')}</option>`).join('');

  setContent(`
    <div class="page-header">
      <h1>Entscheidungen</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:12px">${assessed.length} bewertete Streams</span>
      </div>
    </div>
    <div class="filters">
      <select id="filter-rstatus" onchange="window._filterDecisions()">${statusOpts}</select>
      <select id="filter-decision" onchange="window._filterDecisions()">${decisionOpts}</select>
    </div>
    ${assessed.length === 0
      ? '<div class="card card-body" style="color:var(--text-muted)">Noch keine Streams bewertet. Zuerst <a href="#/assessments">Bewertungen erstellen</a>.</div>'
      : `<div class="card"><div class="table-wrap">
          <table><thead><tr>
            <th>Stream</th><th>Berechnet</th><th>Geprüft</th><th>Override</th>
            <th>Prüfstatus</th><th>Priorität</th><th>Konfidenz</th><th>Betriebsmodell</th><th></th>
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
      Entscheidungsdaten konnten nicht geladen werden: ${esc(e.message)}
    </div>`);
    return;
  }

  // Compute decision (legacy single-assessment)
  try {
    decision = await API.post(`decisions/compute/${encodeURIComponent(streamId)}`);
  } catch {
    decision = null;
  }

  // Option comparison (DE/AT)
  let optionComparison = null;
  try {
    optionComparison = await API.post(`decisions/compare/${encodeURIComponent(streamId)}`);
  } catch {
    // No option assessments available
  }

  const rv = review?.review || null;

  const reviewStatus = rv?.review_status || 'pending';
  const reviewStatusCls = {
    draft: 'badge-warning', completed: 'badge-info', reviewed: 'badge-success', pending: 'badge-muted',
  };

  setContent(`
    <div class="detail-header">
      <div>
        <h1>Entscheidung: ${esc(stream.name)}</h1>
        <div class="detail-meta">
          ${badge('badge-info', stream.stream_type || '---')}
          ${badge(reviewStatusCls[reviewStatus], 'Prüfung: ' + reviewStatus.replace(/_/g, ' '))}
          ${rv?.override_applied ? badge('badge-danger', 'Override angewendet') : ''}
        </div>
      </div>
      <div class="actions">
        <a href="#/decisions" class="btn">&larr; Entscheidungen</a>
        <a href="#/streams/${encodeURIComponent(streamId)}" class="btn">Stream anzeigen</a>
        <a href="#/assessments/${encodeURIComponent(streamId)}" class="btn">Bewertung anzeigen</a>
        <button class="btn btn-primary" id="btn-edit-review">Prüfung bearbeiten</button>
      </div>
    </div>

    ${_renderOptionComparison(optionComparison)}

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

// ─── Option comparison (DE/AT) ───────────────────────────────────────────────

function _renderOptionComparison(cmp) {
  if (!cmp) {
    return `<div class="detail-section">
      <h3>DE / AT Optionsvergleich</h3>
      <p style="color:var(--text-muted)">Keine Optionsbewertungen verfügbar. Bitte Bewertungen für de_standard, at_standard und central auf der Stream-Detailseite erstellen.</p>
    </div>`;
  }

  const labels = {
    de_standard: 'DE Standard',
    at_standard: 'AT Standard',
    central: 'Central',
  };
  const details = cmp.option_details || {};
  const options = Object.keys(details);

  const headerCells = options.map(opt =>
    `<th style="text-align:center">${esc(labels[opt] || opt)}
      ${opt === cmp.recommended_option ? '<br>' + badge('badge-success', 'empfohlen') : ''}
    </th>`
  ).join('');

  const scoreCells = options.map(opt => {
    const d = details[opt];
    return `<td style="text-align:center">${scoreBarHtml(d.score)}</td>`;
  }).join('');
  const adjScoreCells = options.map(opt => {
    const d = details[opt];
    return `<td style="text-align:center">${scoreBarHtml(d.adjusted_score)}</td>`;
  }).join('');
  const classCells = options.map(opt => {
    const d = details[opt];
    return `<td style="text-align:center">${classificationBadge(d.classification)}</td>`;
  }).join('');
  const statusCells = options.map(opt => {
    const d = details[opt];
    if (d.blocked) return `<td style="text-align:center">${badge('badge-danger', 'blockiert')}</td>`;
    return `<td style="text-align:center">${badge('badge-success', 'geeignet')}</td>`;
  }).join('');
  const constraintCells = options.map(opt => {
    const d = details[opt];
    return `<td style="text-align:center;font-size:12px">${
      d.hard_constraints.length ? d.hard_constraints.map(c => badge('badge-danger', c.replace(/_/g, ' '))).join(' ') : '---'
    }</td>`;
  }).join('');

  const blockersList = (cmp.blockers || []).length
    ? cmp.blockers.map(b => `<li style="font-size:13px">${esc(b)}</li>`).join('')
    : '';
  const prereqList = (cmp.prerequisites || []).length
    ? cmp.prerequisites.map(p => `<li style="font-size:13px">${esc(p)}</li>`).join('')
    : '';

  const discardedRows = (cmp.discarded_options || []).map(d => `
    <tr>
      <td>${esc(d.label || d.option)}</td>
      <td>${d.score != null ? scoreBarHtml(d.score) : '---'}</td>
      <td>${classificationBadge(d.classification)}</td>
      <td style="font-size:12px">${esc(d.reason)}</td>
    </tr>
  `).join('');

  return `<div class="detail-section">
    <h3>DE / AT Optionsvergleich</h3>
    ${cmp.recommended_option
      ? `<div style="margin-bottom:12px;padding:10px;background:var(--bg-light);border-radius:6px;border:1px solid var(--border)">
          <strong>Empfehlung:</strong> ${badge('badge-success', labels[cmp.recommended_option] || cmp.recommended_option)}
          <p style="margin:6px 0 0;font-size:13px">${esc(cmp.rationale)}</p>
        </div>`
      : `<div style="margin-bottom:12px;padding:10px;background:#fef2f2;border-radius:6px;border:1px solid var(--danger)">
          <strong>Keine Option kann empfohlen werden.</strong>
          <p style="margin:6px 0 0;font-size:13px">${esc(cmp.rationale)}</p>
        </div>`}

    <div class="table-wrap"><table>
      <thead><tr><th></th>${headerCells}</tr></thead>
      <tbody>
        <tr><td><strong>Punktzahl</strong></td>${scoreCells}</tr>
        <tr><td><strong>Bereinigt</strong></td>${adjScoreCells}</tr>
        <tr><td><strong>Klassifikation</strong></td>${classCells}</tr>
        <tr><td><strong>Status</strong></td>${statusCells}</tr>
        <tr><td><strong>Einschränkungen</strong></td>${constraintCells}</tr>
      </tbody>
    </table></div>

    ${blockersList ? `<div style="margin-top:10px"><strong style="font-size:12px">Blockierende Faktoren</strong><ul style="margin:4px 0 0 16px">${blockersList}</ul></div>` : ''}
    ${prereqList ? `<div style="margin-top:10px"><strong style="font-size:12px">Voraussetzungen</strong><ul style="margin:4px 0 0 16px">${prereqList}</ul></div>` : ''}

    ${discardedRows ? `
      <div style="margin-top:12px">
        <strong style="font-size:12px">Verworfene Optionen</strong>
        <div class="table-wrap"><table>
          <thead><tr><th>Option</th><th>Punktzahl</th><th>Klassifikation</th><th>Begründung</th></tr></thead>
          <tbody>${discardedRows}</tbody>
        </table></div>
      </div>` : ''}
  </div>`;
}

// ─── Computed decision section ───────────────────────────────────────────────

function _renderComputedDecision(d) {
  if (!d) {
    return `<div class="detail-section">
      <h3>Berechnete Entscheidung</h3>
      <p style="color:var(--text-muted)">Entscheidung konnte nicht berechnet werden. Stellen Sie sicher, dass der Stream eine abgeschlossene Bewertung hat.</p>
    </div>`;
  }

  const blockingList = (d.blocking_factors || []).length
    ? d.blocking_factors.map(b => `<li>${esc(b)}</li>`).join('')
    : '<li style="color:var(--text-muted)">Keine</li>';

  const prereqList = (d.prerequisites || []).length
    ? d.prerequisites.map(p => `<li>${esc(p)}</li>`).join('')
    : '<li style="color:var(--text-muted)">Keine</li>';

  return `<div class="detail-section">
    <h3>Berechnete Entscheidung</h3>
    <dl class="key-value">
      <dt>Empfehlung</dt><dd>${decisionBadge(d.decision)}</dd>
      <dt>Begründung</dt><dd>${esc(d.decision_rationale || '---')}</dd>
      <dt>Betriebsmodell</dt><dd>${badge('badge-info', (d.target_operating_model || '---').replace(/_/g, ' '))}</dd>
      <dt>Punktzahl</dt><dd>${scoreBarHtml(d.score)}</dd>
      <dt>Klassifikation</dt><dd>${classificationBadge(d.classification)}</dd>
      ${d.confidence ? `<dt>Konfidenz</dt><dd>${confidenceBadge(d.confidence)}</dd>` : ''}
      ${d.priority ? `<dt>Priorität</dt><dd>${badge('badge-info', d.priority)}</dd>` : ''}
      ${d.completeness_score != null ? `<dt>Vollständigkeit</dt><dd>${scoreBarHtml(d.completeness_score, 1)}</dd>` : ''}
      <dt>Erwarteter Nutzen</dt><dd>${esc(d.expected_benefit || '---')}</dd>
      <dt>Umsetzungsrisiko</dt><dd>${esc(d.implementation_risk || '---')}</dd>
      <dt>Schnittstellenkomplexität</dt><dd>${scoreBarHtml(d.interface_complexity, 1)}</dd>
    </dl>
    <div style="margin-top:10px">
      <strong style="font-size:12px">Blockierende Faktoren</strong>
      <ul style="margin:4px 0 0 16px;font-size:13px">${blockingList}</ul>
    </div>
    <div style="margin-top:10px">
      <strong style="font-size:12px">Voraussetzungen</strong>
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
    <h3>Harmonisierung / Standardisierung / Zentralisierung</h3>
    <div style="margin-bottom:8px">
      ${flag(hd.harmonizable, 'Harmonisierbar')}
      ${flag(hd.standardizable, 'Standardisierbar')}
      ${flag(hd.centralizable, 'Zentralisierbar')}
    </div>
    <dl class="key-value">
      <dt>Harmonisierungsgrad</dt><dd>${scoreBarHtml(hd.harmonization_degree, 1)}</dd>
      <dt>Standardisierungsgrad</dt><dd>${scoreBarHtml(hd.standardization_degree, 1)}</dd>
      <dt>Zentralisierungsgrad</dt><dd>${scoreBarHtml(hd.centralization_degree, 1)}</dd>
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
        ${ao.is_recommended ? badge('badge-success', 'empfohlen') : ''}
      </div>
      <p style="margin:4px 0;font-size:13px;color:var(--text-muted)">${esc(ao.description)}</p>
      ${ao.pros?.length ? `<div style="font-size:12px"><strong style="color:var(--success)">Vorteile:</strong> ${ao.pros.map(p => esc(p)).join(', ')}</div>` : ''}
      ${ao.cons?.length ? `<div style="font-size:12px"><strong style="color:var(--danger)">Nachteile:</strong> ${ao.cons.map(c => esc(c)).join(', ')}</div>` : ''}
      ${ao.risks?.length ? `<div style="font-size:12px"><strong>Risiken:</strong> ${ao.risks.map(r => esc(r)).join(', ')}</div>` : ''}
    </div>
  `).join('');

  return `<div class="detail-section">
    <h3>Alternative Optionen</h3>
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
    <h3>Auswirkung bei Nichthandeln</h3>
    <dl class="key-value">
      <dt>Regulatorisches Risiko</dt><dd>${levelBadge(nai.regulatory_risk)}</dd>
      <dt>Operatives Risiko</dt><dd>${levelBadge(nai.operational_risk)}</dd>
      <dt>Ineffizienzkosten</dt><dd>${levelBadge(nai.inefficiency_cost)}</dd>
      <dt>Audit-Risiko</dt><dd>${levelBadge(nai.audit_exposure)}</dd>
      <dt>Begründung</dt><dd style="font-size:13px">${esc(nai.rationale || '---')}</dd>
    </dl>
  </div>`;
}

// ─── Review state ────────────────────────────────────────────────────────────

function _renderReviewState(rv) {
  if (!rv) {
    return `<div class="detail-section">
      <h3>Prüfung</h3>
      <p style="color:var(--text-muted)">Keine Prüfung vorhanden. Klicken Sie auf „Prüfung bearbeiten".</p>
    </div>`;
  }

  const statusCls = { draft: 'badge-warning', completed: 'badge-info', reviewed: 'badge-success' };

  return `<div class="detail-section">
    <h3>Prüfung</h3>
    <dl class="key-value">
      <dt>Status</dt><dd>${badge(statusCls[rv.review_status] || 'badge-muted', rv.review_status || 'draft')}</dd>
      ${rv.reviewer_name ? `<dt>Prüfer</dt><dd>${esc(rv.reviewer_name)}</dd>` : ''}
      ${rv.review_notes ? `<dt>Notizen</dt><dd style="font-size:13px">${esc(rv.review_notes)}</dd>` : ''}
      ${rv.override_applied ? `
        <dt>Override</dt><dd>${badge('badge-danger', 'ja')}</dd>
        ${rv.reviewed_decision ? `<dt>Geprüfte Entscheidung</dt><dd>${decisionBadge(rv.reviewed_decision)}</dd>` : ''}
        ${rv.reviewed_operating_model ? `<dt>Geprüftes Betriebsmodell</dt><dd>${badge('badge-info', rv.reviewed_operating_model.replace(/_/g, ' '))}</dd>` : ''}
        <dt>Override-Begründung</dt><dd style="font-size:13px">${esc(rv.override_rationale || '')}</dd>
      ` : ''}
      ${rv.reviewed_at ? `<dt>Geprüft am</dt><dd>${esc(rv.reviewed_at)}</dd>` : ''}
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
      <dt>Entscheidungsverantwortlicher</dt><dd>${esc(g.decision_owner)}</dd>
      <dt>Entscheidungstyp</dt><dd>${badge('badge-info', (g.decision_type || '').replace(/_/g, ' '))}</dd>
      <dt>Beteiligte</dt><dd>${(g.involved_stakeholders || []).map(s => esc(s)).join(', ') || '---'}</dd>
      <dt>Erforderliche Freigaben</dt><dd>${(g.required_approvals || []).map(a => esc(a)).join(', ') || '---'}</dd>
    </dl>
  </div>`;
}

// ─── Effort estimate ─────────────────────────────────────────────────────────

function _renderEffort(d) {
  if (!d?.effort_estimate) return '';
  const e = d.effort_estimate;

  return `<div class="detail-section">
    <h3>Aufwandsschätzung</h3>
    <dl class="key-value">
      <dt>Personenmonate</dt><dd>${esc(e.person_months_bucket)}</dd>
      <dt>Dauer</dt><dd>${badge('badge-muted', (e.implementation_duration || '').replace(/_/g, ' '))}</dd>
      <dt>Kostenkategorie</dt><dd>${badge('badge-muted', (e.cost_category || '').replace(/_/g, ' '))}</dd>
      <dt>Begründung</dt><dd style="font-size:13px">${esc(e.rationale || '---')}</dd>
    </dl>
  </div>`;
}

// ─── Decision trace ──────────────────────────────────────────────────────────

function _renderDecisionTrace(d) {
  if (!d?.decision_trace) return '';
  const dt = d.decision_trace;

  const listOrNone = (arr) =>
    arr?.length ? arr.map(x => `<li>${esc(x)}</li>`).join('') : '<li style="color:var(--text-muted)">Keine</li>';

  return `<div class="detail-section">
    <h3>Entscheidungsprotokoll (Audit)</h3>
    <div style="font-size:13px">
      <strong>Eingabefaktoren</strong>
      <ul style="margin:2px 0 8px 16px">${listOrNone(dt.input_factors)}</ul>
      <strong>Ausgelöste Regeln</strong>
      <ul style="margin:2px 0 8px 16px">${listOrNone(dt.rules_triggered)}</ul>
      <strong>Angewendete Einschränkungen</strong>
      <ul style="margin:2px 0 8px 16px">${listOrNone(dt.constraints_applied)}</ul>
      <strong>Konfidenzbasis</strong>
      <ul style="margin:2px 0 8px 16px">${listOrNone(dt.confidence_basis)}</ul>
    </div>
  </div>`;
}

// ─── Review form ─────────────────────────────────────────────────────────────

function openReviewForm(streamId, existingReview, decision) {
  const rv = existingReview || {};
  const isOverride = rv.override_applied || false;

  const statusOpts = [
    { value: 'draft', label: 'Entwurf' },
    { value: 'completed', label: 'Abgeschlossen' },
    { value: 'reviewed', label: 'Geprüft' },
  ];
  const decisionOpts = [
    { value: '', label: '--- berechnet verwenden ---' },
    ...DECISIONS.map(d => ({ value: d, label: d.replace(/_/g, ' ') })),
  ];
  const tomOpts = [
    { value: '', label: '--- berechnet verwenden ---' },
    ...OPERATING_MODELS.map(m => ({ value: m, label: m.replace(/_/g, ' ') })),
  ];

  openModal('Prüfung bearbeiten', `
    ${selectField('f-rv-status', 'Prüfstatus', statusOpts, rv.review_status || 'draft')}
    ${textField('f-rv-reviewer', 'Prüfer', rv.reviewer_name || '')}
    ${textArea('f-rv-notes', 'Prüfnotizen', rv.review_notes || '')}
    <hr style="border:none;border-top:1px solid var(--border);margin:14px 0">
    <h4 style="margin:0 0 8px">Manueller Override</h4>
    <div class="form-group">
      <label>
        <input type="checkbox" id="f-rv-override" ${isOverride ? 'checked' : ''}
               onchange="document.getElementById('override-fields').style.display = this.checked ? '' : 'none'">
        Manuellen Override anwenden
      </label>
    </div>
    <div id="override-fields" style="display:${isOverride ? '' : 'none'}">
      ${selectField('f-rv-decision', 'Geprüfte Entscheidung', decisionOpts, rv.reviewed_decision || '')}
      ${selectField('f-rv-tom', 'Geprüftes Betriebsmodell', tomOpts, rv.reviewed_operating_model || '')}
      ${textArea('f-rv-rationale', 'Override-Begründung (Pflichtfeld)', rv.override_rationale || '', { rows: 3 })}
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
      if (!rationale) throw new Error('Override-Begründung ist bei aktiviertem Override erforderlich.');
      if (rd) payload.reviewed_decision = rd;
      if (rt) payload.reviewed_operating_model = rt;
      payload.override_rationale = rationale;
    }

    // Add timestamp
    payload.reviewed_at = new Date().toISOString();

    await API.put('reviews', payload);
    toast('Prüfung gespeichert');
    closeModal();
    renderDetail(streamId);
  });
}
