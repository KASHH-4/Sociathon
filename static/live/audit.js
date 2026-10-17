/* audit.js — TransitHear Audit Log page */
'use strict';

const $ = id => document.getElementById(id);

async function loadSummary() {
  try {
    const res = await fetch('/api/audit/summary');
    const data = await res.json();
    const dl = $('summary-dl');
    dl.innerHTML = '';
    const items = [
      ['Total decisions', data.total],
      ['alert_critical', data.by_decision?.alert_critical || 0],
      ['verify_with_staff', data.by_decision?.verify_with_staff || 0],
      ['alert_info', data.by_decision?.alert_info || 0],
      ['ignore', data.by_decision?.ignore || 0],
      ['Mean confidence', data.mean_confidence != null ? data.mean_confidence.toFixed(3) : '—'],
      ['% fuzzy-matched', data.pct_fuzzy_matched != null ? data.pct_fuzzy_matched + '%' : '—'],
      ['% deduped', data.pct_deduped != null ? data.pct_deduped + '%' : '—'],
      ['% degraded to rules', data.pct_degraded != null ? data.pct_degraded + '%' : '—'],
    ];
    items.forEach(([k, v]) => {
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd'); dd.textContent = v;
      dl.appendChild(dt); dl.appendChild(dd);
    });
  } catch (err) {
    $('summary-dl').textContent = 'Error loading summary: ' + err;
  }
}

async function loadLog() {
  const limit = $('limit-select').value || 50;
  const tbody = $('audit-tbody');
  tbody.innerHTML = '<tr><td colspan="9" class="muted-text">Loading…</td></tr>';
  try {
    const res = await fetch(`/api/audit/log?limit=${limit}`);
    const data = await res.json();
    const rows = data.log || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="muted-text">No audit records yet. Run a simulation.</td></tr>';
      return;
    }
    tbody.innerHTML = '';
    rows.forEach(row => {
      const tr = document.createElement('tr');
      const sc = row.stage_scores || {};
      const dec = (row.decision || 'unknown').replace(/_/g, '_');
      const decCls = 'dec-' + (row.decision || 'ignore');
      tr.innerHTML = `
        <td>${formatTime(row.created_at)}</td>
        <td class="${escHtml(decCls)}">${escHtml(row.decision || '—')}</td>
        <td>${sc.stt != null ? sc.stt.toFixed(2) : '—'}</td>
        <td>${sc.extraction != null ? sc.extraction.toFixed(2) : '—'}</td>
        <td>${sc.resolution != null ? sc.resolution.toFixed(2) : '—'}</td>
        <td>${sc.verification != null ? sc.verification.toFixed(2) : '—'}</td>
        <td>${calcFinal(sc)}</td>
        <td>${escHtml((row.rules_fired || []).join(', ') || '—')}</td>
        <td>${row.model_versions?.gemini ? 'gemini' : 'rules'}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="9" class="notice notice-error">Error: ${escHtml(String(err))}</td></tr>`;
  }
}

function calcFinal(sc) {
  if (!sc || !Object.keys(sc).length) return '—';
  const w = { stt: 0.25, extraction: 0.25, resolution: 0.30, verification: 0.20 };
  let sum = 0, total = 0;
  for (const [k, wt] of Object.entries(w)) {
    if (sc[k] != null) { sum += sc[k] * wt; total += wt; }
  }
  return total ? (sum / total).toFixed(3) : '—';
}

function formatTime(iso) {
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  catch (_) { return iso || ''; }
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

$('refresh-btn').addEventListener('click', () => { loadSummary(); loadLog(); });
$('limit-select').addEventListener('change', loadLog);

loadSummary();
loadLog();
