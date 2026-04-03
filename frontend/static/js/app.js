/**
 * Harmonizer SPA — entry point.
 *
 * Registers all page routes, sets up the dataset selector,
 * and boots the router.
 */

import { state } from './api.js';
import { toast } from './utils.js';
import { register, initRouter, route } from './router.js';
import { render as renderDashboard } from './pages/dashboard.js';
import { render as renderAreas } from './pages/areas.js';
import { render as renderStreams } from './pages/streams.js';
import { render as renderReports } from './pages/reports.js';

// ─── Route registration ───────────────────────────────────────────────────────

register('dashboard', (_id) => renderDashboard());
register('areas',     (_id) => renderAreas());
register('streams',   (id)  => renderStreams(id));
register('reports',   (id)  => renderReports(id));

// Stub handlers for Phase B pages (keep nav links working)
register('subprocesses', () => Promise.resolve(_comingSoon('Subprocesses')));
register('interfaces',   () => Promise.resolve(_comingSoon('Interfaces')));
register('assessments',  () => Promise.resolve(_comingSoon('Assessments')));
register('decisions',    () => Promise.resolve(_comingSoon('Decisions')));
register('outcomes',     () => Promise.resolve(_comingSoon('Outcomes')));

function _comingSoon(name) {
  const { setContent } = window; // fallback — import at module scope is cleaner
  import('./utils.js').then(({ setContent }) => {
    setContent(`
      <div class="page-header"><h1>${name}</h1></div>
      <div class="card card-body" style="color:var(--text-muted)">
        This section is not yet available in the current phase.
      </div>
    `);
  });
}

// ─── Dataset selector ─────────────────────────────────────────────────────────

function initDatasetSelector() {
  const sel = document.getElementById('dataset-select');
  if (!sel) return;

  // Show current value until dashboard populates the full list
  if (!sel.querySelector(`option[value="${state.dataset}"]`)) {
    sel.innerHTML = `<option value="${state.dataset}">${state.dataset}</option>`;
  }

  sel.addEventListener('change', () => {
    state.dataset = sel.value;
    localStorage.setItem('harmonizer_dataset', sel.value);
    // Re-render current page with new dataset
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
  initDatasetSelector();
  initRouter();
  route(); // render initial page
});
