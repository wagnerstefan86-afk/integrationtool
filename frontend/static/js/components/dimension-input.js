/**
 * Dimension score input component — renders sliders with value display.
 */

import { esc } from '../utils.js';

/**
 * Render a set of dimension score inputs.
 *
 * @param {string} prefix - ID prefix (e.g. 'dim' or 'ts')
 * @param {Array} items - [{id, label, text?}]
 * @param {Object} existingAnswers - {id: {score, rationale}} from existing assessment
 * @param {Function} onChange - called when any value changes
 * @returns {string} HTML
 */
export function dimensionInputs(prefix, items, existingAnswers = {}, onChange = null) {
  if (items.length === 0) return '';

  const rows = items.map(item => {
    const existing = existingAnswers[item.id] || {};
    const score = existing.score ?? '';
    const rationale = existing.rationale || '';
    const inputId = `${prefix}-${item.id}`;

    return `<div class="dim-input-row" data-dim-id="${esc(item.id)}">
      <div class="dim-input-header">
        <label class="dim-input-label" for="${inputId}">${esc(item.label || item.text || item.id)}</label>
        <div class="dim-input-score">
          ${scoreButtons(inputId, score)}
        </div>
      </div>
      <input class="form-control dim-rationale" id="${inputId}-rat"
             placeholder="Begründung (optional)" value="${esc(rationale)}"
             style="font-size:12px;padding:4px 8px;margin-top:4px">
    </div>`;
  }).join('');

  return `<div class="dim-input-group" id="${prefix}-group">${rows}</div>`;
}

function scoreButtons(inputId, currentScore) {
  return `<div class="score-btn-group" id="${inputId}-btns">
    ${[1, 2, 3, 4, 5].map(v =>
      `<button type="button" class="score-btn ${v === currentScore ? 'active' : ''}"
              data-input="${inputId}" data-value="${v}">${v}</button>`
    ).join('')}
    <span class="score-btn-label" id="${inputId}-val">${currentScore || '—'}</span>
  </div>`;
}

/**
 * Wire up score button click handlers for a dimension group.
 * Call after inserting the HTML into the DOM.
 *
 * @param {string} prefix - same prefix passed to dimensionInputs
 * @param {Function} onChange - called when any score changes
 */
export function wireDimensionInputs(prefix, onChange) {
  const group = document.getElementById(`${prefix}-group`);
  if (!group) return;

  group.addEventListener('click', (e) => {
    const btn = e.target.closest('.score-btn[data-value]');
    if (!btn) return;
    const inputId = btn.dataset.input;
    const value = parseInt(btn.dataset.value);

    // Update active state
    const btnGroup = btn.closest('.score-btn-group');
    btnGroup.querySelectorAll('.score-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    // Update label
    const label = document.getElementById(`${inputId}-val`);
    if (label) label.textContent = value;

    if (onChange) onChange();
  });

  // Rationale changes also trigger onChange (debounced)
  let ratTimer;
  group.addEventListener('input', (e) => {
    if (e.target.classList.contains('dim-rationale')) {
      clearTimeout(ratTimer);
      ratTimer = setTimeout(() => { if (onChange) onChange(); }, 500);
    }
  });
}

/**
 * Read current values from a dimension group.
 *
 * @param {string} prefix
 * @param {Array} items - [{id, ...}]
 * @returns {Array} [{dimension|question_id, score, rationale}]
 */
export function readDimensionValues(prefix, items) {
  const results = [];
  for (const item of items) {
    const inputId = `${prefix}-${item.id}`;
    const btnGroup = document.getElementById(`${inputId}-btns`);
    const activeBtn = btnGroup?.querySelector('.score-btn.active');
    const score = activeBtn ? parseInt(activeBtn.dataset.value) : null;
    const rationale = document.getElementById(`${inputId}-rat`)?.value?.trim() || '';

    if (score != null) {
      results.push({
        dimension: item.id,  // works for both dimensions and question_ids
        question_id: item.id,
        score,
        rationale,
      });
    }
  }
  return results;
}
