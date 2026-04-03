/**
 * Areas page — list, create, edit, delete.
 */

import { API } from '../api.js';
import { setContent, esc, badge, toast } from '../utils.js';
import { openModal, closeModal } from '../components/modal.js';
import { textField, textArea, val } from '../components/forms.js';

export async function render() {
  const [areas, streams] = await Promise.all([
    API.get('areas'),
    API.get('streams'),
  ]);

  const streamCounts = {};
  for (const s of streams) {
    streamCounts[s.area_id] = (streamCounts[s.area_id] || 0) + 1;
  }

  const rows = areas.map(a => {
    const count = streamCounts[a.id] || 0;
    return `<tr class="clickable" onclick="location.hash='#/streams?area=${encodeURIComponent(a.id)}'">
      <td>
        <strong>${esc(a.name)}</strong>
        <br><code style="font-size:11px;color:var(--text-muted)">${esc(a.id)}</code>
      </td>
      <td style="color:var(--text-muted)">${esc(a.description || '—')}</td>
      <td style="text-align:center">${badge('badge-primary', String(count))}</td>
      <td onclick="event.stopPropagation()" style="white-space:nowrap">
        <button class="btn btn-sm" data-edit-area="${esc(a.id)}">Bearbeiten</button>
        <button class="btn btn-sm btn-danger" data-delete-area="${esc(a.id)}">Löschen</button>
      </td>
    </tr>`;
  }).join('');

  setContent(`
    <div class="page-header">
      <h1>Bereiche</h1>
      <div class="actions">
        <button class="btn btn-primary" id="btn-add-area">+ Bereich hinzufügen</button>
      </div>
    </div>
    <div class="card">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Bereich</th>
              <th>Beschreibung</th>
              <th style="text-align:center">Streams</th>
              <th></th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `);

  // Wire buttons
  document.getElementById('btn-add-area').addEventListener('click', () => openAreaForm(null));
  document.querySelectorAll('[data-edit-area]').forEach(btn => {
    const id = btn.dataset.editArea;
    const area = areas.find(a => a.id === id);
    btn.addEventListener('click', () => openAreaForm(area));
  });
  document.querySelectorAll('[data-delete-area]').forEach(btn => {
    btn.addEventListener('click', () => deleteArea(btn.dataset.deleteArea));
  });
}

function openAreaForm(area) {
  const isNew = !area;
  const a = area || {};

  openModal(isNew ? 'Bereich erstellen' : 'Bereich bearbeiten', `
    ${textField('f-area-id', 'ID', a.id || '', { required: true, readonly: !isNew, placeholder: 'z. B. my_area' })}
    ${textField('f-area-name', 'Name', a.name || '', { required: true })}
    ${textArea('f-area-desc', 'Beschreibung', a.description || '')}
    ${textArea('f-area-notes', 'Notizen', a.notes || '', { rows: 2 })}
  `, async () => {
    const id = val('f-area-id');
    const name = val('f-area-name');
    if (!id) throw new Error('ID ist erforderlich');
    if (!name) throw new Error('Name ist erforderlich');

    await API.put('areas', {
      id,
      name,
      description: val('f-area-desc'),
      notes: val('f-area-notes'),
    });
    toast(isNew ? 'Bereich erstellt' : 'Bereich aktualisiert');
    closeModal();
    render();
  });
}

async function deleteArea(areaId) {
  if (!confirm(`Bereich „${areaId}" löschen?\n\nDies schlägt fehl, wenn Streams noch auf diesen Bereich verweisen.`)) return;
  try {
    await API.del(`areas/${encodeURIComponent(areaId)}`);
    toast('Bereich gelöscht');
    render();
  } catch (e) {
    toast(e.message, true);
  }
}
