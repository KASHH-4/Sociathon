/* live.js — TransitHear Live Monitor
   Vanilla JS, no build step, no npm dependencies.
   ES2020+ (Chrome/Edge/Android only — same requirement as Web Speech API)
*/
'use strict';

// ============================================================
// Device ID (random UUID, persisted in localStorage)
// ============================================================
let DEVICE_ID = '';
try {
  DEVICE_ID = localStorage.getItem('th_device_id') || '';
  if (!DEVICE_ID) {
    DEVICE_ID = crypto.randomUUID();
    localStorage.setItem('th_device_id', DEVICE_ID);
  }
} catch (_) {
  DEVICE_ID = 'demo-' + Math.random().toString(36).slice(2);
}

document.getElementById('device-id-display').textContent = DEVICE_ID;

// ============================================================
// HTTPS hint (microphone needs HTTPS on phones)
// ============================================================
if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
  document.getElementById('https-warning').hidden = false;
}

// ============================================================
// Speech API support check
// ============================================================
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SpeechRecognition) {
  document.getElementById('stt-unsupported').hidden = false;
}

// ============================================================
// Helpers
// ============================================================
const $ = id => document.getElementById(id);
const API = url => fetch(url, { headers: { 'Accept': 'application/json' } });
const POST = (url, body) => fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function formatTime(isoStr) {
  try {
    return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (_) { return ''; }
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ============================================================
// Journey mode toggle
// ============================================================
const bookingRadio = $('mode-booking');
const routeRadio   = $('mode-route');
const bookingFields = $('booking-fields');
const routeFields   = $('route-fields');

bookingRadio.addEventListener('change', () => {
  bookingFields.hidden = false;
  routeFields.hidden = true;
});
routeRadio.addEventListener('change', () => {
  bookingFields.hidden = true;
  routeFields.hidden = false;
});

// ============================================================
// Typeahead helpers
// ============================================================
function setupTypeahead(inputId, suggestionsId, apiPath, displayKey) {
  const input = $(inputId);
  const list  = $(suggestionsId);
  let debounce = null;
  let selected = null;

  input.addEventListener('input', () => {
    clearTimeout(debounce);
    const q = input.value.trim();
    if (q.length < 1) { list.hidden = true; return; }
    debounce = setTimeout(async () => {
      try {
        const res = await API(`${apiPath}?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        const items = data.trains || data.stations || [];
        list.innerHTML = '';
        if (!items.length) { list.hidden = true; return; }
        items.slice(0, 8).forEach(item => {
          const li = document.createElement('li');
          li.setAttribute('role', 'option');
          li.textContent = `${item[displayKey] || ''} (${item.number || item.code || ''})`;
          li.dataset.value = item.number || item.code || item[displayKey];
          li.dataset.label = item[displayKey] || '';
          li.addEventListener('mousedown', e => {
            e.preventDefault();
            input.value = item[displayKey] || item.number || item.code;
            input.dataset.selected = li.dataset.value;
            list.hidden = true;
          });
          list.appendChild(li);
        });
        list.hidden = false;
      } catch (_) { list.hidden = true; }
    }, 200);
  });

  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; }, 150));
}

setupTypeahead('train-number-input', 'train-suggestions', '/api/trains', 'name');
setupTypeahead('origin-input',       'origin-suggestions', '/api/stations', 'name');
setupTypeahead('dest-input',         'dest-suggestions',   '/api/stations', 'name');

// ============================================================
// Journey form submit
// ============================================================
$('journey-form').addEventListener('submit', async e => {
  e.preventDefault();
  const mode = document.querySelector('input[name=mode]:checked').value;
  const payload = {
    device_id: DEVICE_ID,
    mode,
  };
  if (mode === 'booking') {
    const tnInput = $('train-number-input');
    payload.train_number = tnInput.dataset.selected || tnInput.value.trim();
    payload.origin = $('origin-input').dataset.selected || $('origin-input').value.trim() || 'PUNE';
    payload.destination = $('dest-input').dataset.selected  || $('dest-input').value.trim() || 'CSMT';
  } else {
    payload.origin      = $('origin-input').dataset.selected || $('origin-input').value.trim();
    payload.destination = $('dest-input').dataset.selected  || $('dest-input').value.trim();
  }
  if (!payload.origin || !payload.destination) {
    alert('Please enter origin and destination stations.');
    return;
  }

  const btn = $('start-journey-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const res = await POST('/api/journey', payload);
    const data = await res.json();
    if (!res.ok) { alert(data.error || 'Error saving journey'); return; }

    const j = data.journey;
    $('journey-info').textContent =
      `✓ Journey set: ${j.origin_code} → ${j.dest_code} (${j.mode} mode)`;
    const cl = $('candidate-list');
    cl.innerHTML = '';
    (data.candidates || []).forEach(t => {
      const li = document.createElement('li');
      li.textContent = `${t.number} — ${t.name}`;
      cl.appendChild(li);
    });
    $('journey-status').hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = 'Save journey';
  }
});

// ============================================================
// Speech recognition
// ============================================================
let recognition = null;
let monitoring  = false;
let wakeLock    = null;
let pendingSegment = '';
let segmentTimer   = null;

function acquireWakeLock() {
  if (!('wakeLock' in navigator)) return;
  navigator.wakeLock.request('screen').then(wl => {
    wakeLock = wl;
    $('wakelockNote').hidden = false;
  }).catch(() => {});
}

document.addEventListener('visibilitychange', () => {
  if (monitoring && document.visibilityState === 'visible') acquireWakeLock();
});

$('start-listen-btn').addEventListener('click', () => {
  if (!SpeechRecognition) {
    $('text-fallback-details').open = true;
    return;
  }
  startListening();
  acquireWakeLock();
  // This click is also the user gesture that unlocks navigator.vibrate
  try { navigator.vibrate(0); } catch (_) {}
});

$('stop-listen-btn').addEventListener('click', stopListening);

function startListening() {
  if (monitoring) return;
  monitoring = true;
  updateMicUI(true);
  createRecognition();
}

function stopListening() {
  monitoring = false;
  if (recognition) { try { recognition.stop(); } catch (_) {} }
  updateMicUI(false);
  if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
  $('wakelockNote').hidden = true;
}

function updateMicUI(active) {
  $('start-listen-btn').hidden = active;
  $('stop-listen-btn').hidden  = !active;
  $('mic-indicator').hidden    = !active;
  $('start-listen-btn').setAttribute('aria-pressed', String(active));
}

function createRecognition() {
  if (!SpeechRecognition) return;
  recognition = new SpeechRecognition();
  recognition.continuous      = true;
  recognition.interimResults  = true;
  recognition.maxAlternatives = 3;
  recognition.lang            = $('lang-select').value;

  recognition.onresult = e => {
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const result = e.results[i];
      if (result.isFinal) {
        const conf = result[0].confidence;
        pendingSegment += result[0].transcript + ' ';
        clearTimeout(segmentTimer);
        segmentTimer = setTimeout(() => submitSegment(conf), 3000);
      } else {
        interim += result[0].transcript;
      }
    }
    $('transcript-interim').textContent = interim;
  };

  recognition.onerror = e => {
    const ignorable = ['no-speech', 'aborted'];
    if (!ignorable.includes(e.error)) {
      $('mic-status').textContent = `Error: ${e.error}`;
    }
  };

  recognition.onend = () => {
    if (monitoring) {
      setTimeout(() => { if (monitoring) createRecognition(); }, 300);
    }
  };

  recognition.start();
}

async function submitSegment(confidence) {
  const text = pendingSegment.trim();
  pendingSegment = '';
  $('transcript-interim').textContent = '';

  const words = text.split(/\s+/).filter(Boolean).length;
  if (words < 3) return;

  try {
    const res = await POST('/api/announcements/ingest', {
      device_id: DEVICE_ID,
      transcript: text,
      stt_source: 'browser',
      stt_confidence: confidence || 0.7,
      language: $('lang-select').value,
    });
    const data = await res.json();
    if (res.ok && data.decision !== 'ignore') {
      renderAlert(data);
    }
  } catch (_) {}
}

// ============================================================
// Manual text fallback
// ============================================================
$('submit-manual-btn').addEventListener('click', async () => {
  const text = $('manual-transcript').value.trim();
  if (!text) return;
  const btn = $('submit-manual-btn');
  btn.disabled = true; btn.textContent = 'Sending…';
  try {
    const res = await POST('/api/announcements/ingest', {
      device_id: DEVICE_ID,
      transcript: text,
      stt_source: 'manual',
      stt_confidence: 0.5,
      language: $('lang-select').value,
    });
    const data = await res.json();
    if (res.ok) {
      renderAlert(data);
      $('manual-transcript').value = '';
    } else {
      alert(data.error || 'Error');
    }
  } finally {
    btn.disabled = false; btn.textContent = 'Submit to pipeline';
  }
});

// ============================================================
// SSE stream
// ============================================================
let evtSource = null;

function connectSSE() {
  if (evtSource) evtSource.close();
  evtSource = new EventSource(`/api/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);
  evtSource.addEventListener('announcement', e => {
    const data = JSON.parse(e.data);
    if (data.decision !== 'ignore') renderAlert(data);
  });
  evtSource.addEventListener('emergency', e => {
    const data = JSON.parse(e.data);
    renderAlert({ ...data, decision: 'alert_critical', type: 'safety' });
  });
  evtSource.onerror = () => {
    setTimeout(connectSSE, 5000);
  };
}
connectSSE();

// ============================================================
// Alert rendering
// ============================================================
const ALERT_ICONS = {
  platform_change: '🚉',
  delay:           '⏱',
  early_arrival:   '⏰',
  cancellation:    '🚫',
  safety:          '🚨',
  arrival:         '🚆',
  departure:       '🚄',
  other:           'ℹ️',
};

const SEEN_IDS = new Set();

function renderAlert(data) {
  if (data.id && SEEN_IDS.has(data.id)) return;
  if (data.id) SEEN_IDS.add(data.id);

  const tpl = document.getElementById('alert-tpl');
  const clone = tpl.content.cloneNode(true);
  const card = clone.querySelector('.alert-card');

  card.dataset.decision = data.decision;
  card.dataset.id = data.id || '';

  // Icon and type label
  const icon = ALERT_ICONS[data.type] || 'ℹ️';
  clone.querySelector('.alert-icon').textContent = icon;
  clone.querySelector('.alert-type-label').textContent =
    (data.type || 'announcement').replace(/_/g, ' ');

  // Trust badge
  const trust = clone.querySelector('.alert-trust-badge');
  trust.textContent = data.trust?.label || '';
  const ts = data.trust?.status || '';
  trust.classList.add(ts === 'confirmed' ? 'trust-confirmed' : ts === 'conflict' ? 'trust-conflict' : 'trust-unverified');

  // Time
  clone.querySelector('.alert-time').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  // Display text
  clone.querySelector('.alert-display-text').textContent = data.display_text || '';

  // Fuzzy correction note (R1)
  const train = data.train || {};
  if (train.correction_note) {
    const corr = clone.querySelector('.alert-correction');
    corr.textContent = '⚠ ' + train.correction_note;
    corr.hidden = false;
  }

  // Platform tile
  if (data.platform) {
    const pt = clone.querySelector('.alert-platform');
    pt.hidden = false;
    pt.querySelector('.platform-number').textContent = data.platform;
  }

  // Recommended action
  clone.querySelector('.alert-action').textContent = data.recommended_action || '';

  // Simulated badge in display
  if (data.simulated) {
    const sim = document.createElement('span');
    sim.className = 'sim-badge';
    sim.textContent = 'Simulated';
    clone.querySelector('.alert-header').appendChild(sim);
  }

  // Ack button
  clone.querySelector('.btn-ack').addEventListener('click', async function() {
    if (data.id) {
      await fetch(`/api/announcements/${data.id}/ack`, { method: 'POST' });
    }
    card.style.opacity = '0.5';
    this.disabled = true; this.textContent = 'Acknowledged ✓';
  });

  // Details toggle
  const detailsDiv = clone.querySelector('.alert-details');
  const detailsBtn = clone.querySelector('.btn-details');
  detailsBtn.addEventListener('click', function() {
    const shown = detailsDiv.hidden;
    detailsDiv.hidden = !shown;
    this.textContent = shown ? 'Details ↑' : 'Details ↓';
    this.setAttribute('aria-expanded', String(shown));
    if (shown) {
      const dl = detailsDiv.querySelector('.detail-list');
      dl.innerHTML = '';
      const items = [
        ['Extractor',    data.extractor],
        ['Degraded',     data.degraded ? 'Yes (rules fallback)' : 'No'],
        ['Resolver',     data.train?.method],
        ['STT',          data.stage_scores?.stt?.toFixed(3)],
        ['Extraction',   data.stage_scores?.extraction?.toFixed(3)],
        ['Resolution',   data.stage_scores?.resolution?.toFixed(3)],
        ['Verification', data.stage_scores?.verification?.toFixed(3)],
        ['Final conf',   data.confidence?.toFixed(3)],
        ['Rules fired',  (data.rules_fired || []).join(', ') || 'none'],
        ['Deduped',      data.deduped ? 'Yes' : 'No'],
      ];
      items.forEach(([k, v]) => {
        if (v == null) return;
        const dt = document.createElement('dt'); dt.textContent = k;
        const dd = document.createElement('dd'); dd.textContent = v;
        dl.appendChild(dt); dl.appendChild(dd);
      });
    }
  });

  // Vibrate
  if (data.haptic_pattern?.length) {
    try {
      navigator.vibrate(data.haptic_pattern);
    } catch (_) {
      const note = $('vibration-note');
      if (note.hidden) {
        note.hidden = false;
        note.textContent = 'ℹ Vibration is not supported on this device (iOS does not support it).';
        note.className = 'notice notice-info';
      }
    }
  }

  // Set aria-live role for critical alerts
  if (data.decision === 'alert_critical') {
    card.setAttribute('aria-live', 'assertive');
  } else {
    card.setAttribute('aria-live', 'polite');
  }

  const container = $('alerts-container');
  $('no-alerts-msg').hidden = true;
  container.prepend(clone);

  // Add to history
  const li = document.createElement('li');
  li.textContent = `${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})} — ${data.decision.replace(/_/g,' ')}: ${(data.display_text||'').slice(0,80)}`;
  $('history-list').prepend(li);
}

// ============================================================
// Simulation panel
// ============================================================
document.querySelectorAll('.btn-sim').forEach(btn => {
  btn.addEventListener('click', async () => {
    const scenario = btn.dataset.scenario;
    btn.disabled = true; btn.textContent = '…';
    try {
      const res = await POST('/api/simulate/announcement', {
        device_id: DEVICE_ID,
        scenario,
      });
      const data = await res.json();
      const sr = $('sim-result');
      sr.hidden = false;
      sr.textContent = JSON.stringify(data, null, 2);
      if (res.ok && data.decision !== 'ignore') renderAlert(data);
    } catch (err) {
      $('sim-result').hidden = false;
      $('sim-result').textContent = 'Error: ' + err;
    } finally {
      btn.disabled = false;
      btn.textContent = btn.dataset.scenario.replace(/_/g, ' ');
    }
  });
});

$('sim-official-btn').addEventListener('click', async () => {
  const res = await POST('/api/simulate/official-update', {
    train_number: '12123',
    station_code: 'PUNE',
    kind: 'platform_change',
    new_platform: 5,
  });
  const data = await res.json();
  $('sim-result').hidden = false;
  $('sim-result').textContent = JSON.stringify(data, null, 2);
});

$('sim-emergency-btn').addEventListener('click', async () => {
  const res = await POST('/api/simulate/emergency', {
    device_id: DEVICE_ID,
    message: 'Emergency situation reported on platform 3. Please evacuate.',
    kind: 'platform_emergency',
  });
  const data = await res.json();
  $('sim-result').hidden = false;
  $('sim-result').textContent = JSON.stringify(data, null, 2);
});

// ============================================================
// Preferences
// ============================================================
async function loadPrefs() {
  try {
    const res = await API(`/api/preferences?device_id=${encodeURIComponent(DEVICE_ID)}`);
    const data = await res.json();
    const p = data.preferences || {};
    $('pref-pa').checked       = p.pa_monitoring !== false;
    $('pref-haptic').checked   = p.haptic !== false;
    $('pref-sentinel').checked = !!p.sleep_sentinel;
    toggleSentinelNote();
  } catch (_) {}
}
loadPrefs();

function toggleSentinelNote() {
  $('sentinel-note').hidden = !$('pref-sentinel').checked;
}
$('pref-sentinel').addEventListener('change', toggleSentinelNote);

$('prefs-form').addEventListener('submit', async e => {
  e.preventDefault();
  const payload = {
    device_id:     DEVICE_ID,
    pa_monitoring: $('pref-pa').checked,
    haptic:        $('pref-haptic').checked,
    sleep_sentinel: $('pref-sentinel').checked,
  };
  await POST('/api/preferences', payload);
  $('prefs-saved').hidden = false;
  setTimeout(() => { $('prefs-saved').hidden = true; }, 2000);
});

// Load announcement history on page load
async function loadHistory() {
  try {
    const res = await API(`/api/announcements?device_id=${encodeURIComponent(DEVICE_ID)}&limit=10`);
    const data = await res.json();
    const list = $('history-list');
    (data.announcements || []).forEach(a => {
      const li = document.createElement('li');
      const time = formatTime(a.created_at);
      li.textContent = `${time} — ${(a.decision||'').replace(/_/g,' ')}: ${(a.normalized_transcript||'').slice(0,60)}`;
      list.appendChild(li);
    });
  } catch (_) {}
}
loadHistory();
