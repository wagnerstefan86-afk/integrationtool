/**
 * Streams page — list view with filters, detail view with subprocess & interface CRUD.
 */

import { API } from '../api.js';
import { setContent, esc, badge, toast } from '../utils.js';
import { openModal, closeModal } from '../components/modal.js';
import { textField, textArea, selectField, formRow, val } from '../components/forms.js';

let _cachedEnums = null;
async function enums() {
  if (!_cachedEnums) _cachedEnums = await API.getGlobal('enums');
  return _cachedEnums;
}

// ─── Entry point ──────────────────────────────────────────────────────────────

export async function render(id) {
  if (id) return renderDetail(id);
  return renderList();
}

// ─── List view ────────────────────────────────────────────────────────────────

async function renderList() {
  const [streams, areas, assessments] = await Promise.all([
    API.get('streams'),
    API.get('areas'),
    API.get('assessments'),
  ]);

  const areaMap = Object.fromEntries(areas.map(a => [a.id, a.name]));
  const assessedIds = new Set(
    assessments.filter(a => a.assessed_object_type === 'stream').map(a => a.assessed_object_id)
  );

  const areaIds = [...new Set(streams.map(s => s.area_id).filter(Boolean))];
  const types = [...new Set(streams.map(s => s.stream_type).filter(Boolean))];

  const areaOpts = ['<option value="">Alle Bereiche</option>',
    ...areaIds.map(id => `<option value="${esc(id)}">${esc(areaMap[id] || id)}</option>`)].join('');
  const typeOpts = ['<option value="">Alle Typen</option>',
    ...types.map(t => `<option value="${esc(t)}">${esc(t)}</option>`)].join('');

  const hashQuery = location.hash.includes('?') ? location.hash.split('?')[1] : '';
  const preArea = new URLSearchParams(hashQuery).get('area') || '';

  const rows = streams.map(s => `
    <tr class="clickable stream-row"
        data-area="${esc(s.area_id || '')}" data-type="${esc(s.stream_type || '')}"
        data-name="${esc(s.name.toLowerCase())}"
        onclick="location.hash='#/streams/${encodeURIComponent(s.id)}'">
      <td><strong>${esc(s.name)}</strong>
        <br><code style="font-size:11px;color:var(--text-muted)">${esc(s.id)}</code></td>
      <td>${esc(areaMap[s.area_id] || s.area_id || '—')}</td>
      <td>${badge('badge-info', s.stream_type || '—')}</td>
      <td>${badge('badge-muted', s.country_scope || '—')} ${badge('badge-muted', s.tenant_scope || '—')}</td>
      <td>${_asIsStatusBadge(s.as_is || {})}</td>
      <td>${assessedIds.has(s.id) ? badge('badge-success', 'bewertet') : badge('badge-muted', 'ausstehend')}</td>
      <td onclick="event.stopPropagation()" style="white-space:nowrap">
        <button class="btn btn-sm" data-edit-stream="${esc(s.id)}">Bearbeiten</button>
        <button class="btn btn-sm btn-danger" data-delete-stream="${esc(s.id)}">Löschen</button>
      </td>
    </tr>`).join('');

  setContent(`
    <div class="page-header">
      <h1>Streams</h1>
      <div class="actions">
        <button class="btn btn-primary" id="btn-add-stream">+ Stream hinzufügen</button>
      </div>
    </div>
    <div class="filters">
      <select id="filter-area" onchange="window._filterStreams()">${areaOpts}</select>
      <select id="filter-type" onchange="window._filterStreams()">${typeOpts}</select>
      <input id="filter-q" type="search" placeholder="Nach Name suchen…" oninput="window._filterStreams()"
             style="padding:6px 10px;border:1px solid var(--border);border-radius:4px;font-size:12px;min-width:180px">
    </div>
    <div class="card"><div class="table-wrap">
      <table><thead><tr>
        <th>Name</th><th>Bereich</th><th>Typ</th><th>Scope</th><th>AS-IS</th><th>Bewertung</th><th></th>
      </tr></thead><tbody id="streams-body">${rows}</tbody></table>
    </div></div>
  `);

  if (preArea) {
    const sel = document.getElementById('filter-area');
    if (sel) { sel.value = preArea; window._filterStreams(); }
  }

  // Wire buttons
  document.getElementById('btn-add-stream').addEventListener('click', () => openStreamForm(null, areas));
  document.querySelectorAll('[data-edit-stream]').forEach(btn => {
    const s = streams.find(s => s.id === btn.dataset.editStream);
    btn.addEventListener('click', () => openStreamForm(s, areas));
  });
  document.querySelectorAll('[data-delete-stream]').forEach(btn => {
    btn.addEventListener('click', () => deleteStream(btn.dataset.deleteStream));
  });
}

window._filterStreams = function () {
  const area = document.getElementById('filter-area')?.value || '';
  const type = document.getElementById('filter-type')?.value || '';
  const q = (document.getElementById('filter-q')?.value || '').toLowerCase().trim();
  document.querySelectorAll('#streams-body .stream-row').forEach(row => {
    const ok = (!area || row.dataset.area === area)
            && (!type || row.dataset.type === type)
            && (!q || row.dataset.name.includes(q) || row.textContent.toLowerCase().includes(q));
    row.style.display = ok ? '' : 'none';
  });
};

// ─── Stream form ──────────────────────────────────────────────────────────────

async function openStreamForm(stream, areas) {
  const isNew = !stream;
  const s = stream || {};
  const e = await enums();

  const areaOpts = [{ value: '', label: '— auswählen —' }, ...areas.map(a => ({ value: a.id, label: a.name }))];
  const typeOpts = [{ value: '', label: '— auswählen —' }, ...e.stream_types.map(t => ({ value: t, label: t }))];
  const scopeOpts = e.country_scopes.map(v => ({ value: v, label: v }));
  const tenantOpts = e.tenant_scopes.map(v => ({ value: v, label: v }));

  openModal(isNew ? 'Stream erstellen' : 'Stream bearbeiten', `
    ${formRow(
      textField('f-s-id', 'ID', s.id || '', { required: true, readonly: !isNew, placeholder: 'z.B. my_stream' }),
      textField('f-s-name', 'Name', s.name || '', { required: true })
    )}
    ${formRow(
      selectField('f-s-area', 'Bereich', areaOpts, s.area_id || ''),
      selectField('f-s-type', 'Stream-Typ', typeOpts, s.stream_type || '')
    )}
    ${formRow(
      selectField('f-s-country', 'Country Scope', scopeOpts, s.country_scope || 'BOTH'),
      selectField('f-s-tenant', 'Tenant Scope', tenantOpts, s.tenant_scope || 'BOTH')
    )}
    ${textField('f-s-owner', 'Eigentümer-Rolle', s.owner_role || '')}
    ${textArea('f-s-desc', 'Beschreibung', s.description || '')}
    ${textArea('f-s-notes', 'Notizen', s.notes || '', { rows: 2 })}
  `, async () => {
    const id = val('f-s-id');
    const name = val('f-s-name');
    if (!id) throw new Error('ID ist erforderlich');
    if (!name) throw new Error('Name ist erforderlich');

    await API.put('streams', {
      ...(isNew ? {} : s),
      id, name,
      area_id: val('f-s-area'),
      stream_type: val('f-s-type'),
      country_scope: val('f-s-country'),
      tenant_scope: val('f-s-tenant'),
      owner_role: val('f-s-owner'),
      description: val('f-s-desc'),
      notes: val('f-s-notes'),
    });
    toast(isNew ? 'Stream erstellt' : 'Stream aktualisiert');
    closeModal();
    renderList();
  });
}

async function deleteStream(streamId) {
  if (!confirm(`Stream „${streamId}" löschen?\n\nSchlägt fehl, wenn Teilprozesse noch auf diesen Stream verweisen.`)) return;
  try {
    await API.del(`streams/${encodeURIComponent(streamId)}`);
    toast('Stream gelöscht');
    renderList();
  } catch (e) { toast(e.message, true); }
}

// ─── Detail view ──────────────────────────────────────────────────────────────

async function renderDetail(streamId) {
  const [stream, subprocesses, interfaces, allAssessments, areas, asIsData, deltaData] = await Promise.all([
    API.get(`streams/${encodeURIComponent(streamId)}`),
    API.get('subprocesses'),
    API.get('interfaces'),
    API.get('assessments'),
    API.get('areas'),
    API.get(`streams/${encodeURIComponent(streamId)}/as-is`).catch(() => ({ as_is: {}, delta: {} })),
    API.get(`streams/${encodeURIComponent(streamId)}/delta`).catch(() => null),
  ]);

  const streamSPs = subprocesses.filter(sp => sp.stream_id === streamId);
  const spIds = new Set(streamSPs.map(sp => sp.id));
  // Show interfaces where source or target is a subprocess of this stream
  const streamIfaces = interfaces.filter(i =>
    spIds.has(i.source_process_id) || spIds.has(i.target_process_id)
  );
  const assessment = allAssessments.find(a => a.assessed_object_id === streamId);

  const regulatoryBadges = (stream.regulatory_context || []).map(r => badge('badge-muted', r)).join(' ');

  // Build subprocess assessment status map
  const spAssMap = {};
  for (const a of allAssessments) {
    if (a.assessed_object_type === 'subprocess' && spIds.has(a.assessed_object_id)) {
      spAssMap[a.assessed_object_id] = a;
    }
  }

  const spRows = streamSPs.map(sp => {
    const spAss = spAssMap[sp.id];
    const spStatus = spAss?.status || 'not_started';
    const statusCls = { draft: 'badge-warning', completed: 'badge-success', reviewed: 'badge-info' };
    return `<tr>
      <td><strong>${esc(sp.name)}</strong>
        <br><code style="font-size:11px;color:var(--text-muted)">${esc(sp.id)}</code></td>
      <td style="color:var(--text-muted);font-size:12px;max-width:200px">${esc(sp.purpose || sp.description || '—')}</td>
      <td>${badge(statusCls[spStatus] || 'badge-muted', spStatus.replace(/_/g, ' '))}</td>
      <td style="white-space:nowrap">
        <a href="#/assessments/${encodeURIComponent(sp.id)}" class="btn btn-sm">${spAss ? 'Bew. bearbeiten' : 'Bewerten'}</a>
        <button class="btn btn-sm" data-edit-sp="${esc(sp.id)}">Bearbeiten</button>
        <button class="btn btn-sm btn-danger" data-delete-sp="${esc(sp.id)}">Löschen</button>
      </td>
    </tr>`;
  }).join('');

  const ifaceRows = streamIfaces.map(i => `
    <tr>
      <td><code style="font-size:11px">${esc(i.source_process_id)}</code></td>
      <td>${badge('badge-info', i.interface_type || '—')}</td>
      <td><code style="font-size:11px">${esc(i.target_process_id)}</code></td>
      <td style="color:var(--text-muted);font-size:12px;max-width:200px">${esc(i.description || '—')}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-sm" data-edit-iface="${esc(i.id)}">Bearbeiten</button>
        <button class="btn btn-sm btn-danger" data-delete-iface="${esc(i.id)}">Löschen</button>
      </td>
    </tr>`).join('');

  const assStatus = assessment?.status || 'not_started';
  const assStatusCls = { draft: 'badge-warning', completed: 'badge-success', reviewed: 'badge-info' };
  const assessSection = assessment
    ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
         ${badge(assStatusCls[assStatus] || 'badge-muted', assStatus.replace(/_/g, ' '))}
         ${assessment.assessor ? `<span style="font-size:12px;color:var(--text-muted)">by ${esc(assessment.assessor)}</span>` : ''}
       </div>` + _renderAssessmentSummary(assessment)
    : '<p style="color:var(--text-muted);font-size:12px">Keine Bewertung für diesen Stream erfasst.</p>';

  const streamAsIs = stream.as_is || asIsData?.as_is || {};

  setContent(`
    <div class="detail-header">
      <div>
        <h1>${esc(stream.name)}</h1>
        <div class="detail-meta">
          ${badge('badge-info', stream.stream_type || '—')}
          ${badge('badge-muted', stream.country_scope || '')}
          ${badge('badge-muted', stream.tenant_scope || '')}
          ${_asIsStatusBadge(streamAsIs)}
        </div>
      </div>
      <div class="actions">
        <a href="#/streams" class="btn">← Streams</a>
        <a href="#/process-analysis/${encodeURIComponent(streamId)}" class="btn btn-primary">Prozessanalyse</a>
        <button class="btn" id="btn-edit-stream">Stream bearbeiten</button>
      </div>
    </div>

    <div class="grid-2">
      <div>
        <div class="detail-section">
          <h3>Stream-Info</h3>
          <dl class="key-value">
            <dt>ID</dt>        <dd><code>${esc(stream.id)}</code></dd>
            <dt>Bereich</dt>   <dd>${esc(stream.area_id || '—')}</dd>
            <dt>Eigentümer</dt><dd>${esc(stream.owner_role || '—')}</dd>
            <dt>Beschreibung</dt><dd>${esc(stream.description || '—')}</dd>
            <dt>Notizen</dt>   <dd>${esc(stream.notes || '—')}</dd>
            <dt>Regulierung</dt><dd>${regulatoryBadges || '—'}</dd>
          </dl>
        </div>
        ${_renderAsIsSection(streamId, asIsData)}
        ${_renderDeltaSection(deltaData)}
        <div class="detail-section">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>Optionsbewertungen</h3>
          </div>
          ${_renderOptionAssessments(streamId, allAssessments)}
        </div>
        <div class="detail-section">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>Legacy-Bewertung</h3>
            <a href="#/assessments/${encodeURIComponent(streamId)}" class="btn btn-sm">
              ${assessment ? 'Bearbeiten' : 'Erstellen'}
            </a>
          </div>
          ${assessSection}
        </div>
      </div>
      <div>
        <div class="detail-section">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>Teilprozesse (${streamSPs.length})</h3>
            <button class="btn btn-sm btn-primary" id="btn-add-sp">+ Hinzufügen</button>
          </div>
          ${streamSPs.length === 0
            ? '<p style="color:var(--text-muted)">Keine Teilprozesse definiert.</p>'
            : `<div class="table-wrap"><table>
                <thead><tr><th>Name</th><th>Zweck</th><th>Bewertung</th><th></th></tr></thead>
                <tbody>${spRows}</tbody>
              </table></div>`}
        </div>
        <div class="detail-section">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h3>Schnittstellen (${streamIfaces.length})</h3>
            <button class="btn btn-sm btn-primary" id="btn-add-iface">+ Hinzufügen</button>
          </div>
          ${streamIfaces.length === 0
            ? '<p style="color:var(--text-muted)">Keine Schnittstellen definiert.</p>'
            : `<div class="table-wrap"><table>
                <thead><tr><th>Quelle</th><th>Typ</th><th>Ziel</th><th>Beschreibung</th><th></th></tr></thead>
                <tbody>${ifaceRows}</tbody>
              </table></div>`}
        </div>
      </div>
    </div>
  `);

  // Wire buttons
  document.getElementById('btn-edit-stream').addEventListener('click', () => {
    openStreamForm(stream, areas);
  });
  document.getElementById('btn-add-sp').addEventListener('click', () => {
    openSubprocessForm(null, streamId);
  });
  document.getElementById('btn-add-iface').addEventListener('click', () => {
    openInterfaceForm(null, subprocesses, [...new Set([...spIds])]);
  });
  document.querySelectorAll('[data-edit-sp]').forEach(btn => {
    const sp = streamSPs.find(sp => sp.id === btn.dataset.editSp);
    btn.addEventListener('click', () => openSubprocessForm(sp, streamId));
  });
  document.querySelectorAll('[data-delete-sp]').forEach(btn => {
    btn.addEventListener('click', () => deleteSubprocess(btn.dataset.deleteSp, streamId));
  });
  document.querySelectorAll('[data-edit-iface]').forEach(btn => {
    const iface = streamIfaces.find(i => i.id === btn.dataset.editIface);
    btn.addEventListener('click', () => openInterfaceForm(iface, subprocesses, [...spIds]));
  });
  document.querySelectorAll('[data-delete-iface]').forEach(btn => {
    btn.addEventListener('click', () => deleteInterface(btn.dataset.deleteIface, streamId));
  });

  // AS-IS edit button
  document.getElementById('btn-edit-as-is')?.addEventListener('click', () => {
    openAsIsForm(streamId, asIsData);
  });
}

// ─── AS-IS form (structured) ─────────────────────────────────────────────────

function _asIsCountryFields(prefix, data) {
  const j = (arr) => (arr || []).join('\n');
  return `
    <div class="form-group">
      <label for="f-${prefix}-desc">Beschreibung <span style="color:var(--danger)">*</span></label>
      <textarea class="form-control" id="f-${prefix}-desc" rows="2">${esc(data.description || '')}</textarea>
    </div>
    <h5 style="margin:12px 0 4px;font-size:12px;color:var(--text-muted)">Prozesskontext</h5>
    ${textArea('f-' + prefix + '-triggers', 'Auslöser (einer pro Zeile)', j(data.triggers), { rows: 2 })}
    ${formRow(
      textArea('f-' + prefix + '-inputs', 'Eingaben (eine pro Zeile)', j(data.inputs), { rows: 2 }),
      textArea('f-' + prefix + '-outputs', 'Ausgaben (eine pro Zeile)', j(data.outputs), { rows: 2 })
    )}
    <h5 style="margin:12px 0 4px;font-size:12px;color:var(--text-muted)">Prozessablauf</h5>
    <div class="form-group">
      <label for="f-${prefix}-steps">Schritte (einer pro Zeile, mind. 3) <span style="color:var(--danger)">*</span></label>
      <textarea class="form-control" id="f-${prefix}-steps" rows="4">${esc(j(data.steps))}</textarea>
    </div>
    <h5 style="margin:12px 0 4px;font-size:12px;color:var(--text-muted)">Organisation</h5>
    ${formRow(
      textArea('f-' + prefix + '-roles', 'Rollen (eine pro Zeile) *', j(data.roles), { rows: 2 }),
      textArea('f-' + prefix + '-responsibilities', 'Verantwortlichkeiten (eine pro Zeile)', j(data.responsibilities), { rows: 2 })
    )}
    <h5 style="margin:12px 0 4px;font-size:12px;color:var(--text-muted)">Werkzeuge</h5>
    <div class="form-group">
      <label for="f-${prefix}-tools">Werkzeuge / Systeme (eines pro Zeile) <span style="color:var(--danger)">*</span></label>
      <textarea class="form-control" id="f-${prefix}-tools" rows="2">${esc(j(data.tools))}</textarea>
    </div>
    <h5 style="margin:12px 0 4px;font-size:12px;color:var(--text-muted)">Kontrollen & Evidenz</h5>
    ${formRow(
      textArea('f-' + prefix + '-controls', 'Kontrollen / Referenzen (eine pro Zeile)', j(data.controls), { rows: 2 }),
      textArea('f-' + prefix + '-evidence', 'Evidenz (eine pro Zeile)', j(data.evidence), { rows: 2 })
    )}
    ${textArea('f-' + prefix + '-notes', 'Notizen', data.notes || '', { rows: 2 })}
  `;
}

function _readAsIsCountry(prefix) {
  const toList = (id) => document.getElementById(id)?.value.split('\n').map(l => l.trim()).filter(Boolean) || [];
  return {
    description: val('f-' + prefix + '-desc'),
    triggers: toList('f-' + prefix + '-triggers'),
    inputs: toList('f-' + prefix + '-inputs'),
    outputs: toList('f-' + prefix + '-outputs'),
    steps: toList('f-' + prefix + '-steps'),
    roles: toList('f-' + prefix + '-roles'),
    responsibilities: toList('f-' + prefix + '-responsibilities'),
    tools: toList('f-' + prefix + '-tools'),
    controls: toList('f-' + prefix + '-controls'),
    evidence: toList('f-' + prefix + '-evidence'),
    notes: val('f-' + prefix + '-notes') || null,
  };
}

function _validateAsIs(data, label) {
  const errors = [];
  if (!data.description.trim()) errors.push(`${label}: Beschreibung ist erforderlich`);
  if (data.steps.length < 3) errors.push(`${label}: Mindestens 3 Schritte erforderlich (hat ${data.steps.length})`);
  if (!data.roles.length) errors.push(`${label}: Rollen dürfen nicht leer sein`);
  if (!data.tools.length) errors.push(`${label}: Werkzeuge dürfen nicht leer sein`);
  return errors;
}

async function openAsIsForm(streamId, asIsData) {
  const asIs = asIsData?.as_is || {};
  const delta = asIsData?.delta || {};
  const de = asIs.de || {};
  const at = asIs.at || {};
  const e = await enums();
  const gapOpts = (e.gap_levels || ['low', 'medium', 'high']).map(g => ({ value: g, label: g }));

  openModal('AS-IS bearbeiten: DE / AT', `
    <div id="asis-errors" style="display:none;padding:8px 12px;margin-bottom:12px;background:#fef2f2;border:1px solid var(--danger);border-radius:4px;font-size:12px;color:var(--danger)"></div>

    <h4 style="margin:0 0 8px;color:var(--primary);border-bottom:2px solid var(--primary);padding-bottom:4px">DE (Germany)</h4>
    ${_asIsCountryFields('de', de)}

    <hr style="border:none;border-top:2px solid var(--border);margin:18px 0">

    <h4 style="margin:0 0 8px;color:var(--primary);border-bottom:2px solid var(--primary);padding-bottom:4px">AT (Austria)</h4>
    ${_asIsCountryFields('at', at)}

    <hr style="border:none;border-top:2px solid var(--border);margin:18px 0">
    <h4 style="margin:0 0 8px;color:var(--primary)">Delta-Bewertung</h4>
    ${formRow(
      selectField('f-delta-structural', 'Strukturelle Abweichung', gapOpts, delta.structural_diff || 'low'),
      selectField('f-delta-tooling', 'Werkzeug-Abweichung', gapOpts, delta.tooling_gap || 'low')
    )}
    ${formRow(
      selectField('f-delta-regulatory', 'Regulatorische Abweichung', gapOpts, delta.regulatory_gap || 'low'),
      selectField('f-delta-rolemodel', 'Rollenmodell-Abweichung', gapOpts, delta.role_model_diff || 'low')
    )}
  `, async () => {
    const deData = _readAsIsCountry('de');
    const atData = _readAsIsCountry('at');

    // Client-side validation
    const deHasContent = deData.description.trim();
    const atHasContent = atData.description.trim();
    let errors = [];

    if (deHasContent || atHasContent) {
      if (deHasContent) errors.push(..._validateAsIs(deData, 'DE'));
      if (atHasContent) errors.push(..._validateAsIs(atData, 'AT'));
      if (deHasContent && !atHasContent) errors.push('AT: Beschreibung ist erforderlich, wenn DE ausgefüllt ist');
      if (atHasContent && !deHasContent) errors.push('DE: Beschreibung ist erforderlich, wenn AT ausgefüllt ist');
    }

    const errEl = document.getElementById('asis-errors');
    if (errors.length) {
      if (errEl) {
        errEl.style.display = '';
        errEl.innerHTML = errors.map(e => esc(e)).join('<br>');
      }
      throw new Error(errors.join('; '));
    }

    const body = {
      as_is: { de: deData, at: atData },
      delta: {
        structural_diff: val('f-delta-structural'),
        tooling_gap: val('f-delta-tooling'),
        regulatory_gap: val('f-delta-regulatory'),
        role_model_diff: val('f-delta-rolemodel'),
      },
    };
    await API.put(`streams/${encodeURIComponent(streamId)}/as-is`, body);
    toast('AS-IS gespeichert');
    closeModal();
    renderDetail(streamId);
  });
}

// ─── Subprocess form ──────────────────────────────────────────────────────────

async function openSubprocessForm(sp, streamId) {
  const isNew = !sp;
  const s = sp || {};
  const e = await enums();
  const scopeOpts = e.country_scopes.map(v => ({ value: v, label: v }));
  const tenantOpts = e.tenant_scopes.map(v => ({ value: v, label: v }));

  openModal(isNew ? 'Teilprozess hinzufügen' : 'Teilprozess bearbeiten', `
    ${formRow(
      textField('f-sp-id', 'ID', s.id || '', { required: true, readonly: !isNew, placeholder: 'z.B. sp-my-process' }),
      textField('f-sp-name', 'Name', s.name || '', { required: true })
    )}
    ${textField('f-sp-purpose', 'Zweck', s.purpose || '')}
    ${textArea('f-sp-desc', 'Beschreibung', s.description || '')}
    ${formRow(
      selectField('f-sp-country', 'Länder-Scope', scopeOpts, s.country_scope || 'BOTH'),
      selectField('f-sp-tenant', 'Mandanten-Scope', tenantOpts, s.tenant_scope || 'BOTH')
    )}
    ${textArea('f-sp-roles', 'Rollen (eine pro Zeile)', (s.roles || []).join('\n'), { rows: 2 })}
    ${textArea('f-sp-tools', 'Werkzeuge (eines pro Zeile)', (s.tools || []).join('\n'), { rows: 2 })}
    ${textArea('f-sp-inputs', 'Eingaben (eine pro Zeile)', (s.inputs || []).join('\n'), { rows: 2 })}
    ${textArea('f-sp-outputs', 'Ausgaben (eine pro Zeile)', (s.outputs || []).join('\n'), { rows: 2 })}
    ${textArea('f-sp-evidence', 'Evidenz (eine pro Zeile)', (s.evidence || []).join('\n'), { rows: 2 })}
    ${textArea('f-sp-notes', 'Notizen', s.notes || '', { rows: 2 })}
  `, async () => {
    const id = val('f-sp-id');
    const name = val('f-sp-name');
    if (!id) throw new Error('ID ist erforderlich');
    if (!name) throw new Error('Name ist erforderlich');

    const toList = (v) => v.split('\n').map(l => l.trim()).filter(Boolean);

    await API.put('subprocesses', {
      ...(isNew ? {} : s),
      id, name,
      stream_id: streamId,
      purpose: val('f-sp-purpose'),
      description: val('f-sp-desc'),
      country_scope: val('f-sp-country'),
      tenant_scope: val('f-sp-tenant'),
      roles: toList(document.getElementById('f-sp-roles').value),
      tools: toList(document.getElementById('f-sp-tools').value),
      inputs: toList(document.getElementById('f-sp-inputs').value),
      outputs: toList(document.getElementById('f-sp-outputs').value),
      evidence: toList(document.getElementById('f-sp-evidence').value),
      notes: val('f-sp-notes'),
    });
    toast(isNew ? 'Teilprozess erstellt' : 'Teilprozess aktualisiert');
    closeModal();
    renderDetail(streamId);
  });
}

async function deleteSubprocess(spId, streamId) {
  if (!confirm(`Teilprozess „${spId}" löschen?\n\nSchlägt fehl, wenn Schnittstellen noch darauf verweisen.`)) return;
  try {
    await API.del(`subprocesses/${encodeURIComponent(spId)}`);
    toast('Teilprozess gelöscht');
    renderDetail(streamId);
  } catch (e) { toast(e.message, true); }
}

// ─── Interface form ───────────────────────────────────────────────────────────

async function openInterfaceForm(iface, allSubprocesses, contextSpIds) {
  const isNew = !iface;
  const i = iface || {};
  const e = await enums();

  // Build source/target options: all subprocess IDs + all stream IDs
  const streams = await API.get('streams');
  const processOpts = [
    { value: '', label: '— auswählen —' },
    ...allSubprocesses.map(sp => ({ value: sp.id, label: `[TP] ${sp.name} (${sp.id})` })),
    ...streams.map(s => ({ value: s.id, label: `[Stream] ${s.name} (${s.id})` })),
  ];
  const typeOpts = e.interface_types.map(t => ({ value: t, label: t }));

  openModal(isNew ? 'Schnittstelle hinzufügen' : 'Schnittstelle bearbeiten', `
    ${formRow(
      textField('f-if-id', 'ID', i.id || '', { required: true, readonly: !isNew, placeholder: 'z.B. iface-x-to-y' }),
      selectField('f-if-type', 'Typ', typeOpts, i.interface_type || 'data_flow')
    )}
    ${formRow(
      selectField('f-if-src', 'Quellprozess', processOpts, i.source_process_id || ''),
      selectField('f-if-tgt', 'Zielprozess', processOpts, i.target_process_id || '')
    )}
    ${textArea('f-if-desc', 'Beschreibung', i.description || '')}
    ${textField('f-if-trigger', 'Auslöser', i.trigger || '')}
    ${textArea('f-if-artifacts', 'Ausgetauschte Artefakte (eines pro Zeile)', (i.exchanged_artifacts || []).join('\n'), { rows: 2 })}
    ${textArea('f-if-notes', 'Notizen', i.notes || '', { rows: 2 })}
  `, async () => {
    const id = val('f-if-id');
    if (!id) throw new Error('ID ist erforderlich');

    const toList = (v) => v.split('\n').map(l => l.trim()).filter(Boolean);

    await API.put('interfaces', {
      ...(isNew ? {} : i),
      id,
      interface_type: val('f-if-type'),
      source_process_id: val('f-if-src'),
      target_process_id: val('f-if-tgt'),
      description: val('f-if-desc'),
      trigger: val('f-if-trigger'),
      exchanged_artifacts: toList(document.getElementById('f-if-artifacts').value),
      notes: val('f-if-notes'),
    });
    toast(isNew ? 'Schnittstelle erstellt' : 'Schnittstelle aktualisiert');
    closeModal();
    // Re-render the stream detail page we came from
    const hash = location.hash;
    const match = hash.match(/#\/streams\/([^?]+)/);
    if (match) renderDetail(decodeURIComponent(match[1]));
  });
}

async function deleteInterface(ifaceId, streamId) {
  if (!confirm(`Schnittstelle „${ifaceId}" löschen?`)) return;
  try {
    await API.del(`interfaces/${encodeURIComponent(ifaceId)}`);
    toast('Schnittstelle gelöscht');
    renderDetail(streamId);
  } catch (e) { toast(e.message, true); }
}

// ─── AS-IS completeness check (client-side mirror of backend logic) ──────────

function _isAsIsComplete(data) {
  if (!data?.description?.trim()) return false;
  const steps = (data.steps || []).filter(s => s.trim());
  if (steps.length < 3) return false;
  if (!(data.roles || []).some(r => r.trim())) return false;
  if (!(data.tools || []).some(t => t.trim())) return false;
  return true;
}

function _asIsStatusBadge(asIs) {
  const de = asIs?.de || {};
  const at = asIs?.at || {};
  const deOk = _isAsIsComplete(de);
  const atOk = _isAsIsComplete(at);
  if (deOk && atOk) return badge('badge-success', 'AS-IS vollständig');
  if (deOk || atOk) return badge('badge-warning', 'AS-IS teilweise');
  if (de.description?.trim() || at.description?.trim()) return badge('badge-warning', 'AS-IS unvollständig');
  return badge('badge-danger', 'AS-IS fehlt');
}

// ─── AS-IS DE/AT Section ─────────────────────────────────────────────────────

function _renderAsIsSection(streamId, asIsData) {
  const asIs = asIsData?.as_is || {};
  const delta = asIsData?.delta || {};
  const de = asIs.de || {};
  const at = asIs.at || {};
  const deOk = _isAsIsComplete(de);
  const atOk = _isAsIsComplete(at);

  const list = (items) => {
    const filtered = (items || []).filter(i => i.trim());
    return filtered.length
      ? `<ul style="margin:2px 0 4px 16px;font-size:12px">${filtered.map(i => `<li>${esc(i)}</li>`).join('')}</ul>`
      : '<span style="color:var(--text-muted);font-size:12px">---</span>';
  };

  const section = (label, items) => `
    <div style="margin-bottom:6px">
      <strong style="font-size:11px;color:var(--text-muted);text-transform:uppercase">${label}</strong>
      ${list(items)}
    </div>`;

  const countryCol = (label, data, complete) => `
    <div style="flex:1;min-width:220px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <h4 style="margin:0">${label}</h4>
        ${complete ? badge('badge-success', 'vollständig') : badge('badge-danger', 'unvollständig')}
      </div>
      ${data.description?.trim()
        ? `<p style="font-size:13px;margin:0 0 8px;padding:6px 8px;background:var(--bg-light);border-radius:4px">${esc(data.description)}</p>
           ${section('Schritte', data.steps)}
           ${section('Rollen', data.roles)}
           ${section('Werkzeuge', data.tools)}
           ${(data.triggers || []).length ? section('Auslöser', data.triggers) : ''}
           ${(data.inputs || []).length ? section('Eingaben', data.inputs) : ''}
           ${(data.outputs || []).length ? section('Ausgaben', data.outputs) : ''}
           ${(data.responsibilities || []).length ? section('Verantwortlichkeiten', data.responsibilities) : ''}
           ${section('Kontrollen', data.controls)}
           ${(data.evidence || []).length ? section('Evidenz', data.evidence) : ''}
           ${data.notes?.trim() ? `<div style="margin-top:6px;font-size:12px;color:var(--text-muted)"><em>${esc(data.notes)}</em></div>` : ''}`
        : '<p style="color:var(--text-muted);font-size:12px">Noch nicht dokumentiert.</p>'}
    </div>`;

  const gapBadge = (level) => {
    const cls = { low: 'badge-success', medium: 'badge-warning', high: 'badge-danger' };
    return level ? badge(cls[level] || 'badge-muted', level) : '';
  };

  const deltaHtml = (delta.structural_diff || delta.tooling_gap || delta.regulatory_gap || delta.role_model_diff) ? `
    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
      <strong style="font-size:12px">Delta-Analyse</strong>
      <div style="display:flex;gap:16px;margin-top:6px;font-size:12px;flex-wrap:wrap">
        <span>Struktur: ${gapBadge(delta.structural_diff)}</span>
        <span>Werkzeuge: ${gapBadge(delta.tooling_gap)}</span>
        <span>Regulatorik: ${gapBadge(delta.regulatory_gap)}</span>
        <span>Rollenmodell: ${gapBadge(delta.role_model_diff)}</span>
      </div>
    </div>` : '';

  return `<div class="detail-section">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <h3>AS-IS-Prozessvergleich ${_asIsStatusBadge(asIs)}</h3>
      <button class="btn btn-sm btn-primary" id="btn-edit-as-is">AS-IS bearbeiten</button>
    </div>
    <div style="display:flex;gap:20px;flex-wrap:wrap">
      ${countryCol('DE (Germany)', de, deOk)}
      ${countryCol('AT (Austria)', at, atOk)}
    </div>
    ${deltaHtml}
  </div>`;
}

function _renderDeltaSection(deltaData) {
  if (!deltaData || !deltaData.items || deltaData.items.length === 0) {
    return `<div class="detail-section">
      <h3>DE vs. AT Unterschiede</h3>
      <p style="color:var(--text-muted);font-size:12px">Kein Delta berechnet. Bitte zuerst AS-IS-Dokumentation für DE und AT vervollständigen.</p>
    </div>`;
  }

  const summary = deltaData.summary || {};
  const impactBadge = (level) => {
    const cls = { low: 'badge-success', medium: 'badge-warning', high: 'badge-danger' };
    return badge(cls[level] || 'badge-muted', level);
  };
  const diffBadge = (type) => {
    const cls = { identical: 'badge-success', partial: 'badge-warning', different: 'badge-danger', missing: 'badge-danger' };
    return badge(cls[type] || 'badge-muted', type);
  };
  const listCell = (items) => items?.length
    ? `<span style="font-size:11px">${items.map(i => esc(i)).join(', ')}</span>`
    : '<span style="color:var(--text-muted);font-size:11px">---</span>';

  const rows = deltaData.items.map(item => `
    <tr>
      <td><strong style="font-size:12px">${esc(item.category)}</strong></td>
      <td>${listCell(item.de_value)}</td>
      <td>${listCell(item.at_value)}</td>
      <td>${diffBadge(item.difference_type)}</td>
      <td>${impactBadge(item.impact)}</td>
    </tr>
    <tr><td colspan="5" style="padding:2px 8px 8px;font-size:11px;color:var(--text-muted);border-bottom:1px solid var(--border)">${esc(item.description)}</td></tr>
  `).join('');

  return `<div class="detail-section">
    <h3>DE vs. AT Unterschiede</h3>
    <div style="display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap">
      <div style="padding:8px 14px;background:var(--bg-light);border-radius:6px;font-size:13px">
        <strong>${summary.total_items || 0}</strong> <span style="color:var(--text-muted)">Kategorien verglichen</span>
      </div>
      ${summary.high_impact ? `<div style="padding:8px 14px;background:#fef2f2;border-radius:6px;font-size:13px;border:1px solid var(--danger)">
        <strong style="color:var(--danger)">${summary.high_impact}</strong> <span>hohe Auswirkung</span>
      </div>` : ''}
      ${summary.medium_impact ? `<div style="padding:8px 14px;background:#fffbeb;border-radius:6px;font-size:13px;border:1px solid var(--warning)">
        <strong style="color:var(--warning)">${summary.medium_impact}</strong> <span>mittlere Auswirkung</span>
      </div>` : ''}
      ${summary.low_impact ? `<div style="padding:8px 14px;background:#f0fdf4;border-radius:6px;font-size:13px">
        <strong style="color:var(--success)">${summary.low_impact}</strong> <span>geringe Auswirkung</span>
      </div>` : ''}
    </div>
    <div class="table-wrap"><table>
      <thead><tr>
        <th>Kategorie</th><th>DE</th><th>AT</th><th>Abweichung</th><th>Auswirkung</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
  </div>`;
}

function _renderOptionAssessments(streamId, allAssessments) {
  const optAssessments = allAssessments.filter(
    a => a.assessed_object_id === streamId && a.assessed_object_type === 'stream' && a.target_option
  );

  if (optAssessments.length === 0) {
    return `<p style="color:var(--text-muted);font-size:13px">
      Noch keine Optionsbewertungen. Bewerten Sie die Harmonisierungsstrategien:
    </p>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <a href="#/assessments/${encodeURIComponent(streamId)}?option=de_standard" class="btn btn-sm">DE-Standard bewerten</a>
      <a href="#/assessments/${encodeURIComponent(streamId)}?option=at_standard" class="btn btn-sm">AT-Standard bewerten</a>
      <a href="#/assessments/${encodeURIComponent(streamId)}?option=central" class="btn btn-sm">Zentral bewerten</a>
    </div>`;
  }

  const optMap = Object.fromEntries(optAssessments.map(a => [a.target_option, a]));
  const statusCls = { draft: 'badge-warning', completed: 'badge-success', reviewed: 'badge-info' };
  const options = ['de_standard', 'at_standard', 'central'];
  const labels = { de_standard: 'DE Standard', at_standard: 'AT Standard', central: 'Central' };

  const rows = options.map(opt => {
    const a = optMap[opt];
    if (!a) {
      return `<tr>
        <td>${esc(labels[opt])}</td>
        <td>${badge('badge-muted', 'fehlt')}</td><td>---</td><td>---</td>
        <td><a href="#/assessments/${encodeURIComponent(streamId)}?option=${opt}" class="btn btn-sm btn-primary">Erstellen</a></td>
      </tr>`;
    }
    const dims = (a.answers || []).length;
    return `<tr>
      <td><strong>${esc(labels[opt])}</strong></td>
      <td>${badge(statusCls[a.status] || 'badge-muted', a.status || 'draft')}</td>
      <td>${dims}/6 dims</td>
      <td>${(a.hard_constraints || []).length > 0 ? badge('badge-danger', a.hard_constraints.length + ' Einschränkungen') : badge('badge-success', 'keine')}</td>
      <td><a href="#/assessments/${encodeURIComponent(streamId)}?option=${opt}" class="btn btn-sm">Bearbeiten</a></td>
    </tr>`;
  }).join('');

  return `<div class="table-wrap"><table>
    <thead><tr><th>Option</th><th>Status</th><th>Antworten</th><th>Einschränkungen</th><th></th></tr></thead>
    <tbody>${rows}</tbody>
  </table></div>
  <div style="margin-top:8px">
    <a href="#/decisions/${encodeURIComponent(streamId)}" class="btn btn-sm btn-primary">Entscheidungsvergleich anzeigen</a>
  </div>`;
}

// ─── Assessment summary (read-only) ──────────────────────────────────────────

function _renderAssessmentSummary(a) {
  const dims = a.answers || [];
  const constraints = a.hard_constraints || [];

  const dimRows = dims.map(d => {
    const pct = Math.round((d.score / 5) * 100);
    const cls = pct >= 70 ? 'high' : pct >= 45 ? 'medium' : 'low';
    return `<tr>
      <td style="font-size:12px">${esc(d.dimension.replace(/_/g, ' '))}</td>
      <td><div class="score-bar" style="min-width:120px">
        <div class="score-bar-track"><div class="score-bar-fill ${cls}" style="width:${pct}%"></div></div>
        <span>${d.score}/5</span>
      </div></td>
      <td style="font-size:11px;color:var(--text-muted)">${esc(d.rationale || '')}</td>
    </tr>`;
  }).join('');

  const constraintBadges = constraints.length
    ? constraints.map(c => badge('badge-danger', c.replace(/_/g, ' '))).join(' ')
    : badge('badge-success', 'keine');

  return `
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr>
        <th style="padding:6px 8px;font-size:11px;color:var(--text-muted);text-align:left">Dimension</th>
        <th style="padding:6px 8px;font-size:11px;color:var(--text-muted)">Punktzahl</th>
        <th style="padding:6px 8px;font-size:11px;color:var(--text-muted)">Begründung</th>
      </tr></thead>
      <tbody>${dimRows}</tbody>
    </table>
    <div style="margin-top:10px">
      <span style="font-size:12px;color:var(--text-muted)">Harte Einschränkungen:</span>
      <span style="margin-left:6px">${constraintBadges}</span>
    </div>`;
}
