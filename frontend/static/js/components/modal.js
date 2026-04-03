/**
 * Modal component — open/close/save wiring for the global modal overlay.
 */

import { toast } from '../utils.js';

let _onSave = null;

/** Wire up modal buttons. Call once on init. */
export function initModal() {
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('modal-cancel').addEventListener('click', closeModal);
  document.getElementById('modal-save').addEventListener('click', async () => {
    if (!_onSave) return;
    const btn = document.getElementById('modal-save');
    btn.disabled = true;
    btn.textContent = 'Saving…';
    try {
      await _onSave();
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save';
    }
  });
  document.getElementById('modal-overlay').addEventListener('click', (e) => {
    if (e.target.id === 'modal-overlay') closeModal();
  });
}

/**
 * Open the modal with a title, body HTML, and async save callback.
 * The save callback should throw on error (error is shown as toast).
 */
export function openModal(title, bodyHtml, onSave) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;
  document.getElementById('modal-overlay').classList.remove('hidden');
  _onSave = onSave;
  // Focus first input
  const first = document.querySelector('#modal-body input, #modal-body select, #modal-body textarea');
  if (first) setTimeout(() => first.focus(), 50);
}

/** Close the modal and clear the save handler. */
export function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
  _onSave = null;
}
