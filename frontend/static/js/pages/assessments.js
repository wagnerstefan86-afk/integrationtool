/**
 * Bewertungen page — list view + full-page assessment editor.
 */

import { API } from '../api.js';
import { setContent, esc, badge, toast } from '../utils.js';
import { scorePanel } from '../components/score-panel.js';
import { dimensionInputs, wireDimensionInputs, readDimensionValues } from '../components/dimension-input.js';

// ─── Constants ────────────────────────────────────────────────────────────────

const BASE_DIMENSIONS = [
  { id: 'regulatory_alignment', label: 'Regulatorische Ausrichtung' },
  { id: 'operational_alignment', label: 'Operative Ausrichtung' },
  { id: 'tooling_alignment', label: 'Tool-Ausrichtung' },
  { id: 'governance_alignment', label: 'Governance-Ausrichtung' },
  { id: 'maturity', label: 'Reifegrad' },
  { id: 'local_necessity', label: 'Lokale Notwendigkeit (hoch = geringe lokale Notwendigkeit)' },
];

const HARD_CONSTRAINTS = [
  { id: 'legal_local_difference', label: 'Rechtliche lokale Abweichung' },
  { id: 'tenant_separation_blocks_operation', label: 'Mandantentrennung blockiert Betrieb' },
  { id: 'separate_control_ownership', label: 'Getrennte Kontrollzuständigkeit' },
  { id: 'insufficient_documentation', label: 'Unzureichende Dokumentation' },
];

const PRIO_DIMENSIONS = [
  { id: 'harmonization_potential', label: 'Harmonisierungspotenzial' },
  { id: 'operational_relevance', label: 'Operative Relevanz' },
  { id: 'governance_compliance_benefit', label: 'Governance / Compliance-Nutzen' },
  { id: 'implementation_effort', label: 'Umsetzungsaufwand (hoch = einfach)' },
  { id: 'dependencies', label: 'Abhängigkeiten (hoch = wenige)' },
];

// ─── State for current edit ───────────────────────────────────────────────────

const TARGET_OPTIONS = [
  { value: '', label: '— keine (Legacy) —' },
  { value: 'de_standard', label: 'DE-Standard (AT übernimmt DE)' },
  { value: 'at_standard', label: 'AT-Standard (DE übernimmt AT)' },
  { value: 'central', label: 'Zentral (neuer einheitlicher Prozess)' },
];

let _editState = null;  // { objectId, objectType, streamType, typeQuestions, targetOption }

// ─── Entry point ──────────────────────────────────────────────────────────────

export async function render(id) {
  if (id) return renderEditor(id);
  return renderList();
}

// ─── List view ────────────────────────────────────────────────────────────────

async function renderList() {
  const [assessments, streams, sps] = await Promise.all([
    API.get('assessments'),
    API.get('streams'),
    API.get('subprocesses'),
  ]);
  const nameMap = Object.fromEntries([
    ...streams.map(s => [s.id, s.name]),
    ...sps.map(sp => [sp.id, sp.name]),
  ]);

  const rows = assessments.map(a => {
    const status = a.status || 'not_started';
    const statusCls = { draft: 'badge-warning', completed: 'badge-success', reviewed: 'badge-info' };
    const optParam = a.target_option ? `?option=${a.target_option}` : '';
    const optLabel = a.target_option ? a.target_option.replace(/_/g, ' ') : '';
    return `<tr>
      <td><strong>${esc(nameMap[a.assessed_object_id] || a.assessed_object_id)}</strong>
        <br><code style="font-size:11px;color:var(--text-muted)">${esc(a.assessed_object_id)}</code></td>
      <td>${badge(a.assessed_object_type === 'stream' ? 'badge-primary' : 'badge-info', a.assessed_object_type)}</td>
      <td>${optLabel ? badge('badge-info', optLabel) : ''}</td>
      <td>${badge(statusCls[status] || 'badge-muted', status)}</td>
      <td style="font-size:12px;color:var(--text-muted)">${esc(a.assessor || '—')}</td>
      <td>${(a.answers || []).length}/6 Dim.</td>
      <td style="white-space:nowrap">
        <a href="#/assessments/${encodeURIComponent(a.assessed_object_id)}${optParam}" class="btn btn-sm btn-primary">Bearbeiten</a>
        <button class="btn btn-sm btn-danger" data-del-ass="${esc(a.assessed_object_id)}" data-del-opt="${esc(a.target_option || '')}">Löschen</button>
      </td>
    </tr>`;
  }).join('');

  setContent(`
    <div class="page-header">
      <h1>Bewertungen</h1>
      <div class="actions">
        <span style="color:var(--text-muted);font-size:13px">${assessments.length} gesamt</span>
      </div>
    </div>
    <div class="card"><div class="table-wrap">
      <table><thead><tr>
        <th>Objekt</th><th>Typ</th><th>Option</th><th>Status</th><th>Bewerter</th><th>Antworten</th><th></th>
      </tr></thead><tbody>${rows}</tbody></table>
    </div></div>
  `);

  document.querySelectorAll('[data-del-ass]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.delAss;
      const opt = btn.dataset.delOpt;
      const label = opt ? `${id} (${opt})` : id;
      if (!confirm(`Bewertung für „${label}" löschen?`)) return;
      try {
        const extra = opt ? { target_option: opt } : {};
        await API.del(`assessments/${encodeURIComponent(id)}`, extra);
        toast('Gelöscht'); renderList();
      } catch (e) { toast(e.message, true); }
    });
  });
}

// ─── Editor ───────────────────────────────────────────────────────────────────

async function renderEditor(objectId) {
  // Parse target option from URL query: #/assessments/foo?option=de_standard
  const hashParts = location.hash.split('?');
  const queryParams = new URLSearchParams(hashParts[1] || '');
  const targetOption = queryParams.get('option') || '';

  // Resolve object type and metadata
  const [streams, sps] = await Promise.all([API.get('streams'), API.get('subprocesses')]);
  const stream = streams.find(s => s.id === objectId);
  const sp = sps.find(s => s.id === objectId);
  const objType = stream ? 'stream' : sp ? 'subprocess' : null;

  if (!objType) {
    setContent(`<div class="card card-body" style="color:var(--danger)">
      Objekt nicht gefunden: ${esc(objectId)}</div>`);
    return;
  }

  const objName = (stream || sp).name;
  const streamType = stream?.stream_type || null;
  // For subprocess, find parent stream type
  const parentStream = sp ? streams.find(s => s.id === sp.stream_id) : null;
  const effectiveStreamType = streamType || parentStream?.stream_type || null;

  // Load type-specific questions
  let typeQuestions = [];
  if (effectiveStreamType) {
    try {
      typeQuestions = await API.getGlobal(`questions/${effectiveStreamType}`);
    } catch { /* no questions for this type */ }
  }

  // Load existing assessment (with target_option if set)
  let existing = null;
  try {
    const extra = targetOption ? { target_option: targetOption } : {};
    existing = await API.get(`assessments/${encodeURIComponent(objectId)}`, extra);
  } catch { /* new */ }

  // Set edit state
  _editState = { objectId, objectType: objType, streamType: effectiveStreamType, typeQuestions, targetOption };

  // Prepare existing answer maps
  const dimAnswers = {};
  for (const a of (existing?.answers || [])) {
    dimAnswers[a.dimension] = a;
  }
  const tsAnswers = {};
  for (const a of (existing?.type_specific_answers || [])) {
    tsAnswers[a.question_id] = a;
  }
  const prioAnswers = {};
  for (const [k, v] of Object.entries(existing?.prioritization || {})) {
    prioAnswers[k] = { score: v };
  }
  const activeConstraints = new Set(existing?.hard_constraints || []);
  const status = existing?.status || 'not_started';

  // Build type-specific items for dimension inputs
  const tsItems = typeQuestions.map(q => ({ id: q.id, label: q.text || q.id }));

  // Build hard constraint checkboxes
  const hcHtml = HARD_CONSTRAINTS.map(hc => {
    const checked = activeConstraints.has(hc.id);
    return `<label class="hc-check ${checked ? 'checked' : ''}">
      <input type="checkbox" id="hc-${hc.id}" ${checked ? 'checked' : ''}>
      ${esc(hc.label)}
    </label>`;
  }).join('');

  // Status buttons
  const _assStatusDE = {not_started:'Nicht begonnen',draft:'Entwurf',completed:'Abgeschlossen'};
  const statusHtml = ['not_started', 'draft', 'completed'].map(s =>
    `<button type="button" class="status-option ${s === status ? 'active' : ''}"
            data-status="${s}">${_assStatusDE[s]}</button>`
  ).join('');

  const backUrl = objType === 'stream'
    ? `#/streams/${encodeURIComponent(objectId)}`
    : `#/streams/${encodeURIComponent(sp?.stream_id || '')}`;

  // Target option selector (streams only)
  const optionSelectorHtml = objType === 'stream' ? `
    <div class="card" style="margin-bottom:16px">
      <div class="card-header">Zieloption <span class="badge badge-info">DE / AT Harmonisierung</span></div>
      <div class="card-body">
        <div class="status-select" id="option-select">
          ${TARGET_OPTIONS.map(o => `
            <button type="button" class="status-option ${(targetOption || '') === o.value ? 'active' : ''}"
                    data-option="${o.value}">${esc(o.label)}</button>
          `).join('')}
        </div>
        <p style="margin-top:8px;font-size:12px;color:var(--text-muted)">
          Jede Zieloption wird unabhängig bewertet. Wählen Sie die Harmonisierungsstrategie, die Sie auswerten möchten.
        </p>
      </div>
    </div>` : '';

  setContent(`
    <div class="page-header">
      <div>
        <h1>Bewertung: ${esc(objName)}</h1>
        <div class="detail-meta" style="margin-top:6px">
          ${badge(objType === 'stream' ? 'badge-primary' : 'badge-info', objType)}
          ${effectiveStreamType ? badge('badge-muted', effectiveStreamType) : ''}
          ${targetOption ? badge('badge-info', targetOption.replace(/_/g, ' ')) : ''}
          <code style="font-size:11px;color:var(--text-muted)">${esc(objectId)}</code>
        </div>
      </div>
      <div class="actions">
        <a href="${backUrl}" class="btn">Abbrechen</a>
        <button class="btn btn-primary" id="btn-save-assessment">Speichern</button>
      </div>
    </div>

    ${optionSelectorHtml}

    <!-- Live Score Panel -->
    <div class="card" style="margin-bottom:16px">
      <div class="card-header">Live-Punktzahl Vorschau</div>
      <div class="card-body" id="live-score-container">
        ${scorePanel(null)}
      </div>
    </div>

    <div class="grid-2" style="gap:16px">
      <div>
        <!-- Base Dimensions -->
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">Ausrichtungsdimensionen <span class="badge badge-muted">1–5</span></div>
          <div class="card-body">
            ${dimensionInputs('dim', BASE_DIMENSIONS, dimAnswers)}
          </div>
        </div>

        <!-- Hard Constraints -->
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">Harte Einschränkungen</div>
          <div class="card-body" id="hc-container">${hcHtml}</div>
        </div>
      </div>

      <div>
        ${tsItems.length > 0 ? `
        <!-- Type-Specific Questions -->
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">Typspezifisch: ${esc(effectiveStreamType || '')} <span class="badge badge-muted">1–5</span></div>
          <div class="card-body">
            ${dimensionInputs('ts', tsItems, tsAnswers)}
          </div>
        </div>` : ''}

        <!-- Prioritization -->
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">Priorisierung <span class="badge badge-muted">1–5</span></div>
          <div class="card-body">
            ${dimensionInputs('prio', PRIO_DIMENSIONS, prioAnswers)}
          </div>
        </div>

        <!-- Metadata -->
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">Bewertungsmetadaten</div>
          <div class="card-body">
            <div class="form-group">
              <label>Status</label>

              <div class="status-select" id="status-select">${statusHtml}</div>
            </div>
            <div class="form-group">
              <label for="f-assessor">Bewerter</label>
              <input class="form-control" id="f-assessor" value="${esc(existing?.assessor || '')}"
                     placeholder="Name / Team">
            </div>
            <div class="form-group">
              <label for="f-notes">Notizen</label>
              <textarea class="form-control" id="f-notes" rows="3"
                        placeholder="Bewertungsnotizen…">${esc(existing?.notes || '')}</textarea>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end">
      <a href="${backUrl}" class="btn">Abbrechen</a>
      <button class="btn btn-primary" id="btn-save-assessment-bottom">Speichern</button>
    </div>
  `);

  // Wire up interactive elements
  wireDimensionInputs('dim', triggerLiveScore);
  wireDimensionInputs('ts', triggerLiveScore);
  wireDimensionInputs('prio', null);  // prio doesn't affect score

  // Hard constraint checkboxes
  document.getElementById('hc-container')?.addEventListener('change', (e) => {
    const label = e.target.closest('.hc-check');
    if (label) label.classList.toggle('checked', e.target.checked);
    triggerLiveScore();
  });

  // Option select — reload editor with new option
  document.getElementById('option-select')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.status-option');
    if (!btn) return;
    const newOpt = btn.dataset.option;
    const optQuery = newOpt ? `?option=${newOpt}` : '';
    location.hash = `#/assessments/${encodeURIComponent(objectId)}${optQuery}`;
  });

  // Status select
  document.getElementById('status-select')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.status-option');
    if (!btn || btn.dataset.status === 'reviewed') return; // reviewed can't be set manually
    document.querySelectorAll('#status-select .status-option').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });

  // Save buttons
  const saveFn = () => saveAssessment(existing);
  document.getElementById('btn-save-assessment')?.addEventListener('click', saveFn);
  document.getElementById('btn-save-assessment-bottom')?.addEventListener('click', saveFn);

  // Initial live score
  triggerLiveScore();
}

// ─── Live Scoring ─────────────────────────────────────────────────────────────

let _scoreTimer = null;

function triggerLiveScore() {
  clearTimeout(_scoreTimer);
  _scoreTimer = setTimeout(doLiveScore, 250);
}

async function doLiveScore() {
  if (!_editState) return;

  const dimValues = readDimensionValues('dim', BASE_DIMENSIONS);
  const tsItems = _editState.typeQuestions.map(q => ({ id: q.id, label: q.text }));
  const tsValues = readDimensionValues('ts', tsItems);

  const hardConstraints = HARD_CONSTRAINTS
    .filter(hc => document.getElementById(`hc-${hc.id}`)?.checked)
    .map(hc => hc.id);

  const payload = {
    answers: dimValues.map(v => ({ dimension: v.dimension, score: v.score })),
    type_specific_answers: tsValues.map(v => ({ question_id: v.question_id, score: v.score })),
    hard_constraints: hardConstraints,
    stream_type: _editState.streamType || undefined,
  };

  try {
    const resp = await fetch('/api/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) return;
    const data = await resp.json();
    const container = document.getElementById('live-score-container');
    if (container) container.innerHTML = scorePanel(data);
  } catch { /* swallow — don't disrupt editing */ }
}

// ─── Save ─────────────────────────────────────────────────────────────────────

async function saveAssessment(existing) {
  if (!_editState) return;

  const dimValues = readDimensionValues('dim', BASE_DIMENSIONS);
  const tsItems = _editState.typeQuestions.map(q => ({ id: q.id, label: q.text }));
  const tsValues = readDimensionValues('ts', tsItems);
  const prioValues = readDimensionValues('prio', PRIO_DIMENSIONS);

  const hardConstraints = HARD_CONSTRAINTS
    .filter(hc => document.getElementById(`hc-${hc.id}`)?.checked)
    .map(hc => hc.id);

  const statusBtn = document.querySelector('#status-select .status-option.active');
  const status = statusBtn?.dataset.status || 'draft';

  const answers = dimValues.map(v => ({
    dimension: v.dimension,
    score: v.score,
    rationale: v.rationale,
  }));
  const typeSpecificAnswers = tsValues.map(v => ({
    question_id: v.question_id,
    score: v.score,
    rationale: v.rationale,
  }));
  const prioritization = {};
  for (const v of prioValues) {
    prioritization[v.dimension] = v.score;
  }

  const assessment = {
    assessed_object_id: _editState.objectId,
    assessed_object_type: _editState.objectType,
    answers,
    type_specific_answers: typeSpecificAnswers,
    hard_constraints: hardConstraints,
    prioritization,
    status,
    assessor: document.getElementById('f-assessor')?.value?.trim() || '',
    notes: document.getElementById('f-notes')?.value?.trim() || '',
  };
  if (_editState.targetOption) {
    assessment.target_option = _editState.targetOption;
  }

  try {
    await API.put('assessments', assessment);
    toast(`Bewertung gespeichert (${status})`);
    // Navigate back
    const backUrl = _editState.objectType === 'stream'
      ? `#/streams/${encodeURIComponent(_editState.objectId)}`
      : `#/streams/${encodeURIComponent(
          (await API.get('subprocesses')).find(sp => sp.id === _editState.objectId)?.stream_id || ''
        )}`;
    location.hash = backUrl;
  } catch (e) {
    toast(e.message, true);
  }
}
