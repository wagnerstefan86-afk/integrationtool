/**
 * Shared rendering utilities.
 */

/** HTML-escape a string to prevent XSS. */
export function esc(str) {
  return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Render a badge span. */
export function badge(cssClass, text) {
  return `<span class="badge ${cssClass}">${esc(text)}</span>`;
}

/** Badge for a decision value. */
export function decisionBadge(decision) {
  if (!decision) return '—';
  return `<span class="badge decision-${decision}">${esc(decision.replace(/_/g, ' '))}</span>`;
}

/** Badge for a harmonization classification. */
export function classificationBadge(cls) {
  const map = {
    fully_harmonizable: 'badge-success',
    harmonizable: 'badge-primary',
    conditionally_harmonizable: 'badge-warning',
    partially_harmonizable: 'badge-warning',
    not_harmonizable: 'badge-danger',
  };
  return badge(map[cls] || 'badge-muted', (cls || '—').replace(/_/g, ' '));
}

/** Badge for confidence level. */
export function confidenceBadge(level) {
  const cls = { high: 'confidence-high', medium: 'confidence-medium', low: 'confidence-low' };
  return `<span class="badge ${cls[level] || 'badge-muted'}">${esc(level || '—')}</span>`;
}

/** Score bar HTML (score 0–5). */
export function scoreBarHtml(score, max = 5) {
  if (score == null) return '<span style="color:var(--text-muted)">—</span>';
  const pct = Math.round((score / max) * 100);
  const cls = pct >= 70 ? 'high' : pct >= 45 ? 'medium' : 'low';
  const fmt = typeof score === 'number' ? score.toFixed(2) : score;
  return `<div class="score-bar">
    <div class="score-bar-track">
      <div class="score-bar-fill ${cls}" style="width:${pct}%"></div>
    </div>
    <span>${fmt}</span>
  </div>`;
}

/** Show a toast notification. */
export function toast(msg, isError = false) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.style.background = isError ? '#dc2626' : '#1e293b';
  el.classList.remove('hidden');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add('hidden'), 3500);
}

/** Replace #page-content with HTML and hide the loading indicator. */
export function setContent(html) {
  const loading = document.getElementById('page-loading');
  const content = document.getElementById('page-content');
  if (loading) loading.classList.add('hidden');
  if (content) content.innerHTML = html;
}

/** Show the loading indicator and clear page content. */
export function showLoading() {
  const loading = document.getElementById('page-loading');
  const content = document.getElementById('page-content');
  if (loading) loading.classList.remove('hidden');
  if (content) content.innerHTML = '';
}

/**
 * Convert Markdown text to safe HTML for in-browser report rendering.
 * Handles: headings, bold, lists, tables, code blocks, mermaid blocks, HR.
 */
export function mdToHtml(md) {
  const lines = md.split('\n');
  const out = [];
  let inCode = false;
  let isMermaid = false;
  let codeLines = [];
  let inTable = false;

  for (const line of lines) {
    // Code fence
    if (line.startsWith('```')) {
      if (inCode) {
        if (isMermaid) {
          out.push(`<div class="mermaid">${codeLines.join('\n')}</div>`);
        } else {
          out.push(`<pre style="background:#f6f8fa;padding:12px;border-radius:4px;overflow-x:auto">${codeLines.map(l => esc(l)).join('\n')}</pre>`);
        }
        inCode = false; isMermaid = false; codeLines = [];
      } else {
        isMermaid = line.slice(3).trim() === 'mermaid';
        inCode = true;
      }
      continue;
    }
    if (inCode) { codeLines.push(line); continue; }

    // Tables
    if (line.includes('|') && line.trim().startsWith('|')) {
      // Skip separator rows (---|---|...)
      if (/^[\|\s\-:]+$/.test(line)) { continue; }
      if (!inTable) { out.push('<table style="border-collapse:collapse;width:100%;margin:12px 0">'); inTable = true; }
      const cells = line.trim().replace(/^\||\|$/g, '').split('|');
      out.push('<tr>' + cells.map(c => `<td style="padding:6px 10px;border:1px solid var(--border)">${esc(c.trim())}</td>`).join('') + '</tr>');
      continue;
    }
    if (inTable) { out.push('</table>'); inTable = false; }

    // Headings
    if (line.startsWith('#### ')) { out.push(`<h4 style="margin:14px 0 4px">${esc(line.slice(5))}</h4>`); continue; }
    if (line.startsWith('### ')) { out.push(`<h3 style="margin:18px 0 6px;padding-bottom:4px;border-bottom:1px solid var(--border)">${esc(line.slice(4))}</h3>`); continue; }
    if (line.startsWith('## ')) { out.push(`<h2 style="margin:22px 0 8px;color:var(--primary)">${esc(line.slice(3))}</h2>`); continue; }
    if (line.startsWith('# ')) { out.push(`<h1 style="margin:0 0 16px;font-size:20px">${esc(line.slice(2))}</h1>`); continue; }

    // List items
    if (line.startsWith('- ')) { out.push(`<li style="margin:2px 0 2px 18px">${inlineFmt(line.slice(2))}</li>`); continue; }

    // HR
    if (/^-{3,}$/.test(line.trim())) { out.push('<hr style="border:none;border-top:1px solid var(--border);margin:14px 0">'); continue; }

    // Blank line
    if (line.trim() === '') { out.push('<br>'); continue; }

    // Paragraph
    out.push(`<p style="margin:4px 0">${inlineFmt(line)}</p>`);
  }

  if (inTable) out.push('</table>');
  if (inCode) out.push(isMermaid
    ? `<div class="mermaid">${codeLines.join('\n')}</div>`
    : `<pre>${codeLines.map(l => esc(l)).join('\n')}</pre>`);

  return out.join('\n');
}

function inlineFmt(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code style="background:#f3f4f6;padding:1px 4px;border-radius:3px;font-size:90%">$1</code>');
}
