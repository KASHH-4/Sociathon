/**
 * transit-live-core.js — TransitHear Unified Frontend & Backend Integration
 * Seamlessly connects the visual React SPA with the Python Flask backend and Supabase.
 * Uses exact theme tokens from the old folder frontend (DM Sans, Manrope, Navy, Signal Blue).
 * Hardcoded data acts strictly as an offline fallback.
 */

'use strict';

(function () {
  // --- 1. Device ID Management ---
  let DEVICE_ID = '';
  try {
    DEVICE_ID = localStorage.getItem('th_device_id') || '';
    if (!DEVICE_ID) {
      DEVICE_ID = crypto.randomUUID();
      localStorage.setItem('th_device_id', DEVICE_ID);
    }
  } catch (_) {
    DEVICE_ID = 'device-' + Math.random().toString(36).slice(2, 10);
  }

  // State
  let backendHealth = null;
  let activeJourney = null;
  let speechRec = null;
  let isListening = false;
  let pendingTranscript = '';
  let speechTimer = null;
  let eventSource = null;
  const acknowledgedIds = new Set();

  const API_HEADERS = { 'Accept': 'application/json' };
  const postJson = (url, body) => fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify(body),
  });

  // --- 2. Initialize Backend & Supabase Status ---
  async function initBackendHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        backendHealth = await res.json();
        updateHeaderStatus();
      }
    } catch (e) {
      console.warn('[TransitHear] Offline or backend unreachable, using fallback mode:', e);
    }
  }

  // --- 3. DOM Injection: Live Header Bar & Controls ---
  function injectLiveHeader() {
    if (document.getElementById('th-live-header-bar')) return;

    const bar = document.createElement('div');
    bar.id = 'th-live-header-bar';
    bar.className = 'th-live-header-bar';
    bar.innerHTML = `
      <div class="th-live-status-group">
        <span id="th-store-pill" class="th-status-pill local-store">
          <span class="th-dot"></span> <span id="th-store-text">Checking Store…</span>
        </span>
        <span id="th-mic-pill" class="th-status-pill" style="display:none;">
          <span class="th-dot"></span> <span id="th-mic-status-text">Mic Active</span>
        </span>
        <span id="th-active-train-pill" class="th-status-pill" style="background:rgba(255,255,255,0.08);cursor:pointer;color:#cbd5e1;" title="Click to change journey">
          🚆 <span id="th-train-name-display">12128 Deccan Queen</span> ▾
        </span>
      </div>
      <div class="th-live-actions">
        <button id="th-toggle-mic-btn" class="th-btn-compact" title="Start microphone for speech-to-text PA detection">
          🎙️ <span>Start Mic</span>
        </button>
        <button id="th-open-sim-btn" class="th-btn-compact th-btn-primary" title="Open simulation scenarios and live pipeline tester">
          ⚡ <span>Simulation Lab</span>
        </button>
        <a href="/live/audit" target="_blank" class="th-btn-compact" style="text-decoration:none;" title="View pipeline confidence scores and audit trail">
          📋 <span>Audit Log</span>
        </a>
      </div>
    `;

    document.body.prepend(bar);

    // Event Listeners
    document.getElementById('th-toggle-mic-btn').addEventListener('click', toggleMicrophone);
    document.getElementById('th-open-sim-btn').addEventListener('click', openSimulationDrawer);
    document.getElementById('th-active-train-pill').addEventListener('click', openJourneyModal);
  }

  function updateHeaderStatus() {
    const storePill = document.getElementById('th-store-pill');
    const storeText = document.getElementById('th-store-text');
    if (!storePill || !storeText) return;

    if (backendHealth && backendHealth.store === 'Supabase' && !backendHealth.store_degraded) {
      storePill.className = 'th-status-pill supabase-online';
      storeText.textContent = 'Supabase Connected';
      storePill.title = 'Live connected to Supabase PostgreSQL database';
    } else {
      storePill.className = 'th-status-pill local-store';
      storeText.textContent = 'Local Seed Store';
      storePill.title = 'Running on in-memory local seed data';
    }
  }

  // --- 4. Web Speech API (Microphone Speech-to-Text) ---
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function toggleMicrophone() {
    if (isListening) {
      stopMicrophone();
    } else {
      startMicrophone();
    }
  }

  function startMicrophone() {
    if (!SpeechRecognition) {
      alert('Web Speech API is not supported in this browser. Please use Google Chrome, Microsoft Edge, or Android.');
      return;
    }

    try {
      speechRec = new SpeechRecognition();
      speechRec.continuous = true;
      speechRec.interimResults = true;
      speechRec.lang = 'en-IN';

      speechRec.onstart = () => {
        isListening = true;
        const btn = document.getElementById('th-toggle-mic-btn');
        if (btn) {
          btn.className = 'th-btn-compact th-btn-mic-active';
          btn.innerHTML = '🔴 <span>Stop Mic</span>';
        }
        const micPill = document.getElementById('th-mic-pill');
        if (micPill) {
          micPill.style.display = 'inline-flex';
          micPill.className = 'th-status-pill listening';
        }
        showSpeechBanner('Listening for public announcements…');
        try { navigator.vibrate(50); } catch (_) {}
      };

      speechRec.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i];
          if (res.isFinal) {
            const conf = res[0].confidence || 0.8;
            pendingTranscript += res[0].transcript + ' ';
            clearTimeout(speechTimer);
            speechTimer = setTimeout(() => submitSpeechSegment(conf), 2500);
          } else {
            interim += res[0].transcript;
          }
        }
        if (interim) {
          showSpeechBanner('Hearing: "' + interim + '"');
        }
      };

      speechRec.onerror = (e) => {
        if (e.error !== 'no-speech' && e.error !== 'aborted') {
          console.warn('[TransitHear Mic Error]', e.error);
        }
      };

      speechRec.onend = () => {
        if (isListening) {
          setTimeout(() => { if (isListening) speechRec.start(); }, 400);
        }
      };

      speechRec.start();
    } catch (err) {
      console.error('[TransitHear] Failed to start speech recognition:', err);
      alert('Could not start microphone: ' + err.message);
    }
  }

  function stopMicrophone() {
    isListening = false;
    if (speechRec) {
      try { speechRec.stop(); } catch (_) {}
    }
    const btn = document.getElementById('th-toggle-mic-btn');
    if (btn) {
      btn.className = 'th-btn-compact';
      btn.innerHTML = '🎙️ <span>Start Mic</span>';
    }
    const micPill = document.getElementById('th-mic-pill');
    if (micPill) micPill.style.display = 'none';
    hideSpeechBanner();
  }

  async function submitSpeechSegment(confidence) {
    const text = pendingTranscript.trim();
    pendingTranscript = '';
    hideSpeechBanner();

    if (!text || text.split(/\s+/).length < 3) return;

    showSpeechBanner('Processing announcement through pipeline…');
    try {
      const res = await postJson('/api/announcements/ingest', {
        device_id: DEVICE_ID,
        transcript: text,
        stt_source: 'browser',
        stt_confidence: confidence || 0.75,
        language: 'en-IN',
      });
      const data = await res.json();
      hideSpeechBanner();
      if (res.ok && data.decision !== 'ignore') {
        renderLiveAnnouncement(data);
      }
    } catch (e) {
      console.error('[TransitHear] Ingest error:', e);
      hideSpeechBanner();
    }
  }

  function showSpeechBanner(text) {
    let banner = document.getElementById('th-speech-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'th-speech-banner';
      banner.className = 'th-speech-banner';
      const headerBar = document.getElementById('th-live-header-bar');
      if (headerBar) headerBar.after(banner);
      else document.body.prepend(banner);
    }
    banner.innerHTML = `<span>🎙️ <span class="th-live-text">${text}</span></span><button style="background:none;border:none;cursor:pointer;color:inherit;font-weight:bold;" onclick="this.parentElement.remove()">✕</button>`;
  }

  function hideSpeechBanner() {
    const banner = document.getElementById('th-speech-banner');
    if (banner) banner.remove();
  }

  // --- 5. Real-Time SSE Stream ---
  function connectLiveStream() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`/api/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);

    eventSource.addEventListener('announcement', (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.decision !== 'ignore') renderLiveAnnouncement(data);
      } catch (_) {}
    });

    eventSource.addEventListener('emergency', (e) => {
      try {
        const data = JSON.parse(e.data);
        renderLiveAnnouncement({ ...data, decision: 'alert_critical', type: 'safety' });
      } catch (_) {}
    });

    eventSource.onerror = () => {
      setTimeout(connectLiveStream, 6000);
    };
  }

  // --- 6. Live Announcement Card Rendering in UI ---
  function renderLiveAnnouncement(data) {
    if (!data) return;

    // Trigger haptic
    if (data.haptic_pattern && navigator.vibrate) {
      try { navigator.vibrate(data.haptic_pattern); } catch (_) {}
    } else if (navigator.vibrate) {
      try { navigator.vibrate([200, 100, 200]); } catch (_) {}
    }

    // Locate the React Announcement section
    const hudContainer = document.querySelector('main');
    if (!hudContainer) return;

    // Check if live container already exists, else insert before React content
    let liveFeed = document.getElementById('th-live-announcements-feed');
    if (!liveFeed) {
      liveFeed = document.createElement('div');
      liveFeed.id = 'th-live-announcements-feed';
      liveFeed.className = 'th-live-feed-section';
      hudContainer.prepend(liveFeed);
    }

    const cardId = data.id || 'ann-' + Date.now();
    const isEmergency = data.decision === 'alert_critical' || data.type === 'safety';
    const typeLabel = (data.type || 'announcement').replace(/_/g, ' ').toUpperCase();
    const trustLabel = data.trust?.label || 'Verified Announcement';
    const trainInfo = data.train ? `${data.train.matched || data.train.heard || ''}` : '';

    const card = document.createElement('div');
    card.id = cardId;
    card.className = `th-live-card ${isEmergency ? 'emergency' : ''}`;
    card.innerHTML = `
      <div class="th-card-header">
        <div style="display:flex;align-items:center;gap:8px;">
          <span class="th-badge ${isEmergency ? 'emergency' : 'attention'}">${typeLabel}</span>
          <span class="th-badge verified">✓ ${trustLabel}</span>
          ${data.simulated ? '<span class="th-badge simulated">Simulated</span>' : ''}
        </div>
        <span style="font-size:11px;color:var(--th-muted);">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
      <div class="th-card-body">
        <div style="flex:1;">
          <p style="font-size:12px;font-weight:600;color:var(--th-muted);margin:0 0 4px 0;">${trainInfo ? trainInfo + ' · Live Pipeline' : 'Live Update'}</p>
          <h3 class="th-card-title">${data.display_text || 'Train Update Received'}</h3>
          <p class="th-card-desc">${data.recommended_action || 'Please proceed as directed.'}</p>
          ${data.train?.correction_note ? `<div class="th-correction-note">⚠ ${data.train.correction_note}</div>` : ''}
        </div>
        ${data.platform ? `
          <div class="th-platform-box">
            <div class="th-lbl">PLATFORM</div>
            <div class="th-num">${data.platform}</div>
          </div>
        ` : ''}
      </div>
      <div class="th-card-footer">
        <button class="th-btn-compact th-ack-btn" style="background:#2563eb;color:#ffffff;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;">
          Got it ✓
        </button>
        <button class="th-btn-compact th-details-btn" style="background:none;border:none;color:var(--th-signal);cursor:pointer;font-weight:700;">
          Pipeline Details ▾
        </button>
      </div>
      <div class="th-pipeline-details" style="display:none;">
        <div style="font-size:11px;font-weight:800;color:#64748b;margin-bottom:6px;">PIPELINE TRANSPARENCY SCORECARD</div>
        <div class="th-pipeline-grid">
          <div class="th-pipeline-item"><div class="th-p-lbl">EXTRACTOR</div><div class="th-p-val">${data.extractor || 'rules'}</div></div>
          <div class="th-pipeline-item"><div class="th-p-lbl">STT CONF</div><div class="th-p-val">${(data.stage_scores?.stt || 0).toFixed(2)}</div></div>
          <div class="th-pipeline-item"><div class="th-p-lbl">RESOLUTION</div><div class="th-p-val">${(data.stage_scores?.resolution || 0).toFixed(2)}</div></div>
          <div class="th-pipeline-item"><div class="th-p-lbl">VERIFY CONF</div><div class="th-p-val">${(data.stage_scores?.verification || 0).toFixed(2)}</div></div>
          <div class="th-pipeline-item"><div class="th-p-lbl">FUSED CONF</div><div class="th-p-val" style="color:#059669;">${(data.confidence || 0).toFixed(3)}</div></div>
          <div class="th-pipeline-item"><div class="th-p-lbl">DECISION</div><div class="th-p-val">${data.decision || 'alert_info'}</div></div>
        </div>
      </div>
    `;

    // Acknowledge Button
    const ackBtn = card.querySelector('.th-ack-btn');
    ackBtn.addEventListener('click', async () => {
      if (data.id) {
        try { await postJson(`/api/announcements/${data.id}/ack`, {}); } catch (_) {}
      }
      card.style.opacity = '0.6';
      ackBtn.textContent = 'Acknowledged ✓';
      ackBtn.disabled = true;
    });

    // Pipeline Details Toggle
    const detailsBtn = card.querySelector('.th-details-btn');
    const detailsDiv = card.querySelector('.th-pipeline-details');
    detailsBtn.addEventListener('click', () => {
      const isHidden = detailsDiv.style.display === 'none';
      detailsDiv.style.display = isHidden ? 'block' : 'none';
      detailsBtn.textContent = isHidden ? 'Pipeline Details ▴' : 'Pipeline Details ▾';
    });

    liveFeed.prepend(card);
  }

  // --- 7. Live Journey Manager (Supabase backed) ---
  async function loadActiveJourney() {
    try {
      const res = await fetch(`/api/journey/current?device_id=${encodeURIComponent(DEVICE_ID)}`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.journey) {
          activeJourney = data.journey;
          syncJourneyToUI(data.journey, data.stops);
        }
      }
    } catch (_) {
      // Fallback: Deccan Queen hardcoded
    }
  }

  function syncJourneyToUI(journey, stops) {
    const trainNumber = journey.train_number || '12128';
    const trainPillText = document.getElementById('th-train-name-display');
    if (trainPillText) {
      trainPillText.textContent = `${trainNumber} ${journey.origin_code} → ${journey.dest_code}`;
    }

    // Update React Journey Sidebar Card if present
    const journeyPanel = document.querySelector('aside.panel');
    if (journeyPanel) {
      const heading = journeyPanel.querySelector('p.font-bold');
      if (heading) heading.textContent = `Train ${trainNumber}`;
      const sub = journeyPanel.querySelector('p.text-xs.text-muted-foreground');
      if (sub) sub.textContent = `${trainNumber} · ${journey.origin_code} → ${journey.dest_code}`;
    }
  }

  // Journey Switcher Modal
  function injectJourneyModal() {
    if (document.getElementById('th-journey-modal-backdrop')) return;

    const modal = document.createElement('div');
    modal.id = 'th-journey-modal-backdrop';
    modal.className = 'th-modal-backdrop';
    modal.innerHTML = `
      <div class="th-modal">
        <div class="th-modal-header">
          <h3 style="margin:0;font-size:16px;font-weight:800;">Set Up Journey (Supabase)</h3>
          <button id="th-close-journey-btn" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button>
        </div>
        <div class="th-modal-body">
          <p style="font-size:12px;color:var(--th-muted);margin-top:0;">Search real train schedules from Supabase database:</p>
          <div class="th-form-group">
            <label class="th-form-label">Train Number / Name</label>
            <input type="text" id="th-modal-train-input" class="th-input" placeholder="e.g. 12128, Deccan Queen, Pragati…" autocomplete="off" />
            <ul id="th-train-suggestions" class="th-typeahead-list" style="display:none;"></ul>
          </div>
          <div class="th-form-group" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div>
              <label class="th-form-label">Origin</label>
              <input type="text" id="th-modal-origin-input" class="th-input" value="PUNE" />
            </div>
            <div>
              <label class="th-form-label">Destination</label>
              <input type="text" id="th-modal-dest-input" class="th-input" value="CSMT" />
            </div>
          </div>
          <button id="th-save-journey-btn" class="th-btn-compact th-btn-primary" style="width:100%;padding:10px;justify-content:center;font-size:13px;margin-top:10px;">
            Save Journey to Supabase
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    // Close logic
    document.getElementById('th-close-journey-btn').addEventListener('click', closeJourneyModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeJourneyModal();
    });

    // Train Typeahead from Supabase
    const trainInput = document.getElementById('th-modal-train-input');
    const trainList = document.getElementById('th-train-suggestions');
    let debounceTimer;

    trainInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      const q = trainInput.value.trim();
      if (!q) { trainList.style.display = 'none'; return; }
      debounceTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/api/trains?q=${encodeURIComponent(q)}`);
          const data = await res.json();
          const trains = data.trains || [];
          trainList.innerHTML = '';
          if (!trains.length) { trainList.style.display = 'none'; return; }
          trains.forEach((t) => {
            const li = document.createElement('li');
            li.className = 'th-typeahead-item';
            li.textContent = `${t.number} — ${t.name}`;
            li.addEventListener('mousedown', (e) => {
              e.preventDefault();
              trainInput.value = t.number;
              trainInput.dataset.selected = t.number;
              trainList.style.display = 'none';
            });
            trainList.appendChild(li);
          });
          trainList.style.display = 'block';
        } catch (_) { trainList.style.display = 'none'; }
      }, 200);
    });

    // Save Journey
    document.getElementById('th-save-journey-btn').addEventListener('click', async () => {
      const train = trainInput.dataset.selected || trainInput.value.trim() || '12128';
      const origin = document.getElementById('th-modal-origin-input').value.trim() || 'PUNE';
      const dest = document.getElementById('th-modal-dest-input').value.trim() || 'CSMT';

      const saveBtn = document.getElementById('th-save-journey-btn');
      saveBtn.textContent = 'Saving…';
      saveBtn.disabled = true;

      try {
        const res = await postJson('/api/journey', {
          device_id: DEVICE_ID,
          mode: 'booking',
          train_number: train,
          origin,
          destination: dest,
        });
        const data = await res.json();
        if (res.ok) {
          activeJourney = data.journey;
          syncJourneyToUI(data.journey, []);
          closeJourneyModal();
          alert(`Journey set: Train ${train} (${origin} → ${dest}) saved in Supabase!`);
        } else {
          alert('Error: ' + (data.error || 'Failed to save journey'));
        }
      } catch (err) {
        alert('Save failed: ' + err.message);
      } finally {
        saveBtn.textContent = 'Save Journey to Supabase';
        saveBtn.disabled = false;
      }
    });
  }

  function openJourneyModal() {
    injectJourneyModal();
    const modal = document.getElementById('th-journey-modal-backdrop');
    if (modal) modal.classList.add('active');
  }

  function closeJourneyModal() {
    const modal = document.getElementById('th-journey-modal-backdrop');
    if (modal) modal.classList.remove('active');
  }

  // --- 8. Slide-out Simulation Hub Drawer ---
  function injectSimulationDrawer() {
    if (document.getElementById('th-sim-drawer-backdrop')) return;

    const drawer = document.createElement('div');
    drawer.id = 'th-sim-drawer-backdrop';
    drawer.className = 'th-drawer-backdrop';
    drawer.innerHTML = `
      <div class="th-drawer">
        <div class="th-drawer-header">
          <div>
            <h3 class="th-drawer-title">Simulation & Testing Lab</h3>
            <span style="font-size:11px;opacity:0.8;">Test real PA scenarios against Python pipeline</span>
          </div>
          <button id="th-close-sim-btn" class="th-drawer-close">✕</button>
        </div>
        <div class="th-drawer-content">
          <div class="th-drawer-section">
            <h4>Live Pipeline Scenarios</h4>
            <div class="th-scenario-grid">
              <button class="th-btn-scenario" data-scenario="platform_change">🚉 Platform Change</button>
              <button class="th-btn-scenario" data-scenario="delay">⏱ 25m Delay</button>
              <button class="th-btn-scenario" data-scenario="cancellation">🚫 Cancellation</button>
              <button class="th-btn-scenario" data-scenario="early_arrival">⏰ Early Arrival</button>
              <button class="th-btn-scenario" data-scenario="facility_disruption">♿ Lift Out of Service</button>
              <button class="th-btn-scenario" data-scenario="conflicting_official">⚠️ Conflict Feed</button>
              <button class="th-btn-scenario" data-scenario="noise_chatter">🔊 Background Noise</button>
              <button class="th-btn-scenario emergency" data-scenario="emergency">🚨 Emergency Evac</button>
            </div>
          </div>

          <div class="th-drawer-section">
            <h4>Manual Announcement Ingestion</h4>
            <textarea id="th-manual-transcript" class="th-input" rows="3" placeholder="Type custom PA text to run through rules + Gemini pipeline…"></textarea>
            <button id="th-submit-manual-btn" class="th-btn-compact th-btn-primary" style="margin-top:8px;width:100%;justify-content:center;padding:8px;">
              Submit to Pipeline
            </button>
          </div>

          <div class="th-drawer-section">
            <h4>Pipeline Response (JSON)</h4>
            <pre id="th-sim-output" style="background:#0f172a;color:#38bdf8;padding:12px;border-radius:6px;font-size:11px;max-height:180px;overflow:auto;margin:0;">Waiting for scenario execution…</pre>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(drawer);

    // Close logic
    document.getElementById('th-close-sim-btn').addEventListener('click', closeSimulationDrawer);
    drawer.addEventListener('click', (e) => {
      if (e.target === drawer) closeSimulationDrawer();
    });

    // Scenario buttons
    drawer.querySelectorAll('.th-btn-scenario').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const scenario = btn.dataset.scenario;
        const out = document.getElementById('th-sim-output');
        out.textContent = `Running ${scenario} scenario…`;

        try {
          let res, data;
          if (scenario === 'emergency') {
            res = await postJson('/api/simulate/emergency', {
              device_id: DEVICE_ID,
              message: 'Emergency situation reported on platform 3. Please evacuate.',
              kind: 'platform_emergency',
            });
            data = await res.json();
            renderLiveAnnouncement({ ...data, decision: 'alert_critical', type: 'safety', display_text: data.message });
          } else {
            res = await postJson('/api/simulate/announcement', {
              device_id: DEVICE_ID,
              scenario,
            });
            data = await res.json();
            if (data.decision !== 'ignore') renderLiveAnnouncement(data);
          }
          out.textContent = JSON.stringify(data, null, 2);
        } catch (err) {
          out.textContent = 'Error: ' + err.message;
        }
      });
    });

    // Manual Ingest
    document.getElementById('th-submit-manual-btn').addEventListener('click', async () => {
      const text = document.getElementById('th-manual-transcript').value.trim();
      if (!text) return;
      const out = document.getElementById('th-sim-output');
      out.textContent = 'Ingesting transcript…';

      try {
        const res = await postJson('/api/announcements/ingest', {
          device_id: DEVICE_ID,
          transcript: text,
          stt_source: 'manual',
          stt_confidence: 0.85,
          language: 'en-IN',
        });
        const data = await res.json();
        out.textContent = JSON.stringify(data, null, 2);
        if (data.decision !== 'ignore') renderLiveAnnouncement(data);
      } catch (err) {
        out.textContent = 'Error: ' + err.message;
      }
    });
  }

  function openSimulationDrawer() {
    injectSimulationDrawer();
    const drawer = document.getElementById('th-sim-drawer-backdrop');
    if (drawer) drawer.classList.add('active');
  }

  function closeSimulationDrawer() {
    const drawer = document.getElementById('th-sim-drawer-backdrop');
    if (drawer) drawer.classList.remove('active');
  }

  // --- 9. Route-Specific Functionality (Map, Communication, Wearable) ---
  function initRouteIntegrations() {
    const path = window.location.pathname;

    // Accessibility Map View: Load Supabase facilities
    if (path.includes('/map')) {
      fetch('/api/facilities?station=PUNE')
        .then((r) => r.json())
        .then((d) => {
          if (d && d.facilities && d.facilities.length > 0) {
            console.log(`[TransitHear] Loaded ${d.facilities.length} live facilities from Supabase`);
          }
        })
        .catch(() => {});
    }

    // Wearable View: Hook vibration buttons to real backend API
    if (path.includes('/wearable')) {
      document.querySelectorAll('button').forEach((b) => {
        if (b.textContent.includes('Simulate') || b.textContent.includes('Test')) {
          b.addEventListener('click', async () => {
            try {
              const res = await postJson('/api/wearable/simulate-haptic', { pattern: 'alert' });
              const d = await res.json();
              if (d && d.haptic_profile?.vibrations && navigator.vibrate) {
                navigator.vibrate(d.haptic_profile.vibrations);
              }
            } catch (_) {}
          });
        }
      });
    }
  }

  // --- 10. Bootstrap Everything ---
  window.addEventListener('DOMContentLoaded', () => {
    injectLiveHeader();
    initBackendHealth();
    loadActiveJourney();
    connectLiveStream();
    initRouteIntegrations();
  });

  // Re-check on pushState / navigation
  window.addEventListener('popstate', initRouteIntegrations);
})();
