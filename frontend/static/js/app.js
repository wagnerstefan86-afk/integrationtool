/**
 * Harmonizer SPA — entry point.
 *
 * Registers all page routes, sets up the dataset selector,
 * and boots the router.
 */

import { state } from './api.js';
import { setContent } from './utils.js';
import { register, initRouter, route } from './router.js';
import { initModal } from './components/modal.js';
import { render as renderDashboard } from './pages/dashboard.js';
import { render as renderAreas } from './pages/areas.js';
import { render as renderStreams } from './pages/streams.js';
import { render as renderSubprocesses } from './pages/subprocesses.js';
import { render as renderInterfaces } from './pages/interfaces.js';
import { render as renderReports } from './pages/reports.js';

// ─── Route registration ───────────────────────────────────────────────────────

register('dashboard',    (_id) => renderDashboard());
register('areas',        (_id) => renderAreas());
register('streams',      (id)  => renderStreams(id));
register('subprocesses', (_id) => renderSubprocesses());
register('interfaces',   (_id) => renderInterfaces());
register('reports',      (id)  => renderReports(id));

// Stub handlers for Phase C pages
register('assessments', () => Promise.resolve(_comingSoon('Assessments')));
register('decisions',   () => Promise.resolve(_comingSoon('Decisions')));
register('outcomes',    () => Promise.resolve(_comingSoon('Outcomes')));

function _comingSoon(name) {
  setContent(`
    <div class="page-header"><h1>${name}</h1></div>
    <div class="card card-body" style="color:var(--text-muted)">
      This section is not yet available in the current phase.
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

// ─── Boot ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initMermaid();
  initModal();
  initDatasetSelector();
  initRouter();
  route();
});
