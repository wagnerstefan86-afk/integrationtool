/**
 * Score display component — renders live scoring results.
 */

import { esc, badge } from '../utils.js';

/**
 * Render the live score panel HTML from a scoring API response.
 */
export function scorePanel(data) {
  if (!data) {
    return `<div class="score-panel score-panel-empty">
      <span style="color:var(--text-muted)">Enter scores to see live results</span>
    </div>`;
  }

  const cls = data.classification || '—';
  const baseCls = data.base_classification || cls;
  const capped = baseCls !== cls;
  const confCls = { high: 'confidence-high', medium: 'confidence-medium', low: 'confidence-low' };

  return `<div class="score-panel">
    <div class="score-panel-item">
      <div class="score-panel-value" style="font-size:28px;color:var(--primary)">${fmt(data.blended_score)}</div>
      <div class="score-panel-label">Blended Score</div>
    </div>
    <div class="score-panel-item">
      <div class="score-panel-value">${fmt(data.base_score)}</div>
      <div class="score-panel-label">Base Score</div>
    </div>
    <div class="score-panel-item">
      <div class="score-panel-value">${classificationBadge(cls)}</div>
      <div class="score-panel-label">Classification${capped ? ' (constrained)' : ''}</div>
    </div>
    <div class="score-panel-item">
      <div class="score-panel-value">${data.completeness_estimate ?? '—'}%</div>
      <div class="score-panel-label">Completeness</div>
    </div>
    <div class="score-panel-item">
      <div class="score-panel-value">
        <span class="badge ${confCls[data.confidence] || 'badge-muted'}">${esc(data.confidence || '—')}</span>
      </div>
      <div class="score-panel-label">Confidence</div>
    </div>
  </div>
  ${_constraintWarnings(data.constraint_reasons)}
  ${_missingWarnings(data.missing_dimensions)}`;
}

function fmt(v) {
  return v != null ? Number(v).toFixed(3) : '—';
}

function classificationBadge(cls) {
  const map = {
    fully_centralizable: 'badge-success',
    central_method_local_execution: 'badge-primary',
    partially_harmonizable: 'badge-warning',
    minimum_standard_only: 'badge-warning',
    currently_not_harmonizable: 'badge-danger',
  };
  return `<span class="badge ${map[cls] || 'badge-muted'}">${esc((cls || '—').replace(/_/g, ' '))}</span>`;
}

function _constraintWarnings(reasons) {
  if (!reasons || reasons.length === 0) return '';
  return `<div class="score-warnings" style="margin-top:10px">
    ${reasons.map(r => `<div class="score-warning">${esc(r)}</div>`).join('')}
  </div>`;
}

function _missingWarnings(dims) {
  if (!dims || dims.length === 0) return '';
  return `<div style="margin-top:8px;font-size:12px;color:var(--warning)">
    Missing: ${dims.map(d => esc(d.replace(/_/g, ' '))).join(', ')}
  </div>`;
}
