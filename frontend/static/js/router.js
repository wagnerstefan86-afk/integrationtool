/**
 * Hash-based SPA router.
 *
 * Usage:
 *   register('dashboard', async (id) => { ... });
 *   initRouter();    // call once on DOMContentLoaded
 */

import { showLoading, setContent, esc } from './utils.js';

const _handlers = {};

/** Register a page handler for a route name. */
export function register(name, handler) {
  _handlers[name] = handler;
}

/** Navigate to a hash route. */
export function navigate(hash) {
  location.hash = hash;
}

/** Parse current location.hash and invoke the matching handler. */
export async function route() {
  const raw = location.hash.replace(/^#\/?/, '') || '';
  const parts = raw.split('/').filter(Boolean);
  const page = parts[0] || 'dashboard';
  const id = parts[1] ? decodeURIComponent(parts[1]) : null;

  // Update active nav link
  document.querySelectorAll('.nav-link').forEach(a => {
    a.classList.toggle('active', a.dataset.page === page);
  });

  showLoading();

  const handler = _handlers[page] || _handlers['dashboard'];
  if (!handler) {
    setContent(`<div class="card card-body" style="color:var(--danger)">Unbekannte Seite: ${esc(page)}</div>`);
    return;
  }

  try {
    await handler(id);
  } catch (err) {
    setContent(`<div class="card card-body" style="color:var(--danger)">
      <strong>Fehler beim Laden der Seite</strong><br>${esc(err.message)}
    </div>`);
  }
}

/** Wire up the hashchange listener. */
export function initRouter() {
  window.addEventListener('hashchange', route);
}
