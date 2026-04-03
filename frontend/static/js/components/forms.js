/**
 * Shared form field helpers for modal forms.
 */

import { esc } from '../utils.js';

/** Text input field. */
export function textField(id, label, value = '', opts = {}) {
  const ro = opts.readonly ? 'readonly style="background:#f3f4f6;cursor:not-allowed"' : '';
  const req = opts.required ? '<span style="color:var(--danger)"> *</span>' : '';
  const ph = opts.placeholder ? `placeholder="${esc(opts.placeholder)}"` : '';
  return `<div class="form-group">
    <label for="${id}">${esc(label)}${req}</label>
    <input class="form-control" id="${id}" value="${esc(value)}" ${ro} ${ph}>
  </div>`;
}

/** Textarea field. */
export function textArea(id, label, value = '', opts = {}) {
  const rows = opts.rows || 3;
  return `<div class="form-group">
    <label for="${id}">${esc(label)}</label>
    <textarea class="form-control" id="${id}" rows="${rows}">${esc(value)}</textarea>
  </div>`;
}

/** Select dropdown field. */
export function selectField(id, label, options, currentValue = '') {
  const optHtml = options.map(o => {
    const val = typeof o === 'string' ? o : o.value;
    const text = typeof o === 'string' ? o : o.label;
    return `<option value="${esc(val)}" ${val === currentValue ? 'selected' : ''}>${esc(text)}</option>`;
  }).join('');
  return `<div class="form-group">
    <label for="${id}">${esc(label)}</label>
    <select class="form-control" id="${id}">${optHtml}</select>
  </div>`;
}

/** Two fields side by side. */
export function formRow(left, right) {
  return `<div class="form-row">${left}${right}</div>`;
}

/** Read value from a form field, trimmed. Returns '' for missing elements. */
export function val(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}
