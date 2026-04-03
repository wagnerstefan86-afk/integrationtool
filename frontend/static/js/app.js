/**
 * Harmonizer SPA — entry point.
 *
 * Registers all page routes, sets up the dataset selector,
 * and boots the router.
 */

import { API, state } from './api.js';
import { setContent, esc } from './utils.js';
import { register, initRouter, route } from './router.js';
import { initModal } from './components/modal.js';
import { render as renderDashboard } from './pages/dashboard.js';
import { render as renderAreas } from './pages/areas.js';
import { render as renderStreams } from './pages/streams.js';
import { render as renderSubprocesses } from './pages/subprocesses.js';
import { render as renderInterfaces } from './pages/interfaces.js';
import { render as renderReports } from './pages/reports.js';
import { render as renderAssessments } from './pages/assessments.js';
import { render as renderDecisions } from './pages/decisions.js';
import { render as renderDirector } from './pages/director.js';
import { render as renderProcessAnalysis } from './pages/process-analysis.js';

// ─── Route registration ───────────────────────────────────────────────────────

register('dashboard',        (_id) => renderDashboard());
register('areas',            (_id) => renderAreas());
register('streams',          (id)  => renderStreams(id));
register('subprocesses',     (_id) => renderSubprocesses());
register('interfaces',       (_id) => renderInterfaces());
register('assessments',      (id)  => renderAssessments(id));
register('process-analysis', (id)  => renderProcessAnalysis(id));
register('decisions',        (id)  => renderDecisions(id));
register('director',         (_id) => renderDirector());
register('reports',          (id)  => renderReports(id));

// Stub handlers for future phases
register('outcomes',    () => Promise.resolve(_comingSoon('Ergebnisse')));

function _comingSoon(name) {
  setContent(`
    <div class="page-header"><h1>${name}</h1></div>
    <div class="card card-body" style="color:var(--text-muted)">
      Dieser Bereich ist in der aktuellen Phase noch nicht verfügbar.
    </div>
  `);
}

// ─── Dataset selector ─────────────────────────────────────────────────────────

function initDatasetSelector() {
  const sel = document.getElementById('dataset-select');
  if (!sel) return;

  if (!sel.querySelector(`option[value="${state.dataset}"]`)) {
    sel.innerHTML = `<option value="${state.dataset}">${state.dataset}</option>`;
  }

  sel.addEventListener('change', () => {
    state.dataset = sel.value;
    localStorage.setItem('harmonizer_dataset', sel.value);
    route();
  });
}

// ─── Mermaid initialisation ───────────────────────────────────────────────────

function initMermaid() {
  if (window.mermaid) {
    mermaid.initialize({ startOnLoad: false, theme: 'default' });
  }
}

// ─── Version info ────────────────────────────────────────────────────────────

async function initVersionInfo() {
  try {
    const h = await API.getGlobal('health');
    const versionEl = document.getElementById('app-version');
    if (versionEl && h.version) versionEl.textContent = 'v' + h.version;

    const buildEl = document.getElementById('build-info');
    if (buildEl) {
      const parts = [];
      if (h.git_commit && h.git_commit !== 'unknown') parts.push(h.git_commit);
      if (h.build_date && h.build_date !== 'unknown') parts.push(h.build_date.slice(0, 10));
      if (h.app_env) parts.push(h.app_env);
      buildEl.textContent = parts.join(' \u00b7 ');
    }

    // Store globally for dashboard use
    window._harmonizer_health = h;
  } catch { /* ignore — version display is non-critical */ }
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initMermaid();
  initModal();
  initDatasetSelector();
  initVersionInfo();
  initRouter();
  route();
});
