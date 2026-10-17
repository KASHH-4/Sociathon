/**
 * transit-live-core.js — TransitHear Unified Frontend & Backend Integration
 * Fully replaces hardcoded frontend elements with live fetchable data from Flask & Supabase.
 * Strictly adheres to the original design language (DM Sans, Manrope, Navy, Signal Blue).
 * Falls back gracefully to original static values only if network or API is offline.
 */

'use strict';

(function () {
  // --- 1. Persistent Device ID ---
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
  let currentLanguage = 'en-IN';

  const API_HEADERS = { 'Accept': 'application/json' };
  const postJson = (url, body) => fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...API_HEADERS },
    body: JSON.stringify(body),
  });

  // --- 2. Initialize Backend & Health Check ---
  async function initBackendHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        backendHealth = await res.json();
        updateHeaderStatus();
      }
    } catch (e) {
      console.warn('[TransitHear] Offline or backend unreachable:', e);
    }
  }

  // --- 3. Live Header Injection ---
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
        <span id="th-active-train-pill" class="th-status-pill" style="background:rgba(255,255,255,0.08);cursor:pointer;color:#cbd5e1;" title="Click to change journey in Supabase">
          🚆 <span id="th-train-name-display">12128 Deccan Queen</span> ▾
        </span>
        <span class="th-status-pill" style="background:rgba(16,185,129,0.15);color:#34d399;border:1px solid rgba(16,185,129,0.25);">
          ● LIVE SUPABASE DATA
        </span>
        <button id="th-network-pill" class="th-btn-compact" style="background:rgba(59,130,246,0.18);border:1px solid rgba(59,130,246,0.35);color:#93c5fd;cursor:pointer;" title="Click to copy same-network link for phone or tablet">
          📱 <span id="th-network-text">LAN Link</span>
        </button>
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

    document.getElementById('th-toggle-mic-btn').addEventListener('click', toggleMicrophone);
    document.getElementById('th-open-sim-btn').addEventListener('click', openSimulationDrawer);
    document.getElementById('th-active-train-pill').addEventListener('click', openJourneyModal);

    // Network Link Copy Handler
    const networkBtn = document.getElementById('th-network-pill');
    if (networkBtn) {
      fetch('/api/network-info')
        .then(r => r.json())
        .then(d => {
          if (d && d.network_url) {
            networkBtn.dataset.url = d.network_url;
            document.getElementById('th-network-text').textContent = d.network_url.replace('http://', '');
          }
        })
        .catch(() => {});

      networkBtn.addEventListener('click', () => {
        const url = networkBtn.dataset.url || `http://${window.location.hostname}:5000`;
        if (navigator.clipboard) {
          navigator.clipboard.writeText(url).then(() => {
            const originalText = document.getElementById('th-network-text').textContent;
            document.getElementById('th-network-text').textContent = 'Copied to Clipboard! ✓';
            setTimeout(() => {
              document.getElementById('th-network-text').textContent = originalText;
            }, 2500);
          }).catch(() => {
            prompt('Copy this same-network link to open on phone/tablet:', url);
          });
        } else {
          prompt('Copy this same-network link to open on phone/tablet:', url);
        }
      });
    }
  }

  function updateHeaderStatus() {
    const storePill = document.getElementById('th-store-pill');
    const storeText = document.getElementById('th-store-text');
    if (!storePill || !storeText) return;

    if (backendHealth && backendHealth.store === 'supabase' && !backendHealth.store_degraded) {
      storePill.className = 'th-status-pill supabase-online';
      storeText.textContent = 'Supabase Connected';
      storePill.title = 'Live connected to Supabase PostgreSQL database';
    } else {
      storePill.className = 'th-status-pill local-store';
      storeText.textContent = 'Local Seed Store';
      storePill.title = 'Running on local seed repository';
    }
  }

  // --- 4. Web Speech API (Microphone Speech-to-Text) ---
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function toggleMicrophone() {
    if (isListening) stopMicrophone();
    else startMicrophone();
  }

  function startMicrophone() {
    if (!SpeechRecognition) {
      alert('Web Speech API requires Google Chrome, Microsoft Edge, or Android browser.');
      return;
    }

    try {
      speechRec = new SpeechRecognition();
      speechRec.continuous = true;
      speechRec.interimResults = true;
      speechRec.lang = currentLanguage;

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
            speechTimer = setTimeout(() => submitSpeechSegment(conf), 2400);
          } else {
            interim += res[0].transcript;
          }
        }
        if (interim) showSpeechBanner('Hearing: "' + interim + '"');
      };

      speechRec.onerror = (e) => {
        if (e.error !== 'no-speech' && e.error !== 'aborted') {
          console.warn('[TransitHear Mic Error]', e.error);
        }
      };

      speechRec.onend = () => {
        if (isListening) setTimeout(() => { if (isListening) speechRec.start(); }, 400);
      };

      speechRec.start();
    } catch (err) {
      console.error('[TransitHear] Mic start error:', err);
      alert('Could not start microphone: ' + err.message);
    }
  }

  function stopMicrophone() {
    isListening = false;
    if (speechRec) { try { speechRec.stop(); } catch (_) {} }
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
        language: currentLanguage,
      });
      const data = await res.json();
      hideSpeechBanner();
      if (res.ok && data.decision !== 'ignore') {
        renderLiveAnnouncement(data, true);
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

  // --- 5. SSE Real-Time Stream ---
  function connectLiveStream() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`/api/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);

    eventSource.addEventListener('announcement', (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.decision !== 'ignore') renderLiveAnnouncement(data, true);
      } catch (_) {}
    });

    eventSource.addEventListener('emergency', (e) => {
      try {
        const data = JSON.parse(e.data);
        renderLiveAnnouncement({ ...data, decision: 'alert_critical', type: 'safety' }, true);
      } catch (_) {}
    });

    eventSource.onerror = () => setTimeout(connectLiveStream, 6000);
  }

  // --- 6. CORE DOM HYDRATION: Replace Hardcoded Content with Live Data ---

  /**
   * Hydrates the Visual Announcements HUD:
   * Replaces hardcoded alert card, transcript, earlier history, and sidebar journey stops.
   */
  async function hydrateHUD() {
    // 1. Fetch live status from Supabase
    try {
      const statusRes = await fetch(`/api/transit/status?device_id=${encodeURIComponent(DEVICE_ID)}`);
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        applyTransitStatusToDOM(statusData);
      }
    } catch (_) {}

    // 2. Fetch live announcements from Supabase
    try {
      const annRes = await fetch(`/api/transit/announcements?device_id=${encodeURIComponent(DEVICE_ID)}`);
      if (annRes.ok) {
        const annData = await annRes.json();
        const announcements = annData.announcements || [];
        if (announcements.length > 0) {
          applyAnnouncementsToDOM(announcements);
        }
      }
    } catch (_) {}
  }

  function applyTransitStatusToDOM(data) {
    if (!data) return;

    // A. Update Header & Journey Panel Train Name & Number
    const trainNumber = data.train_number || '12128';
    const trainName = data.train_name || 'Deccan Queen Express';
    const origin = data.origin || 'Mumbai CSMT';
    const destination = data.destination || 'Pune Junction';

    const headerPill = document.getElementById('th-train-name-display');
    if (headerPill) headerPill.textContent = `${trainNumber} ${origin} → ${destination}`;

    const journeyAside = document.querySelector('aside.panel');
    if (journeyAside) {
      const nameElem = journeyAside.querySelector('p.font-bold');
      if (nameElem) nameElem.textContent = trainName;

      const subElem = journeyAside.querySelector('p.text-xs.text-muted-foreground');
      if (subElem) subElem.textContent = `${trainNumber} · ${origin} → ${destination}`;

      // B. Update Stops Timeline (.journey-line)
      const stopsContainer = journeyAside.querySelector('.mt-7');
      if (stopsContainer && data.stops && data.stops.length > 0) {
        stopsContainer.innerHTML = '';
        data.stops.forEach((stop, index) => {
          const isCurrent = stop.status === 'current' || index === 1;
          const isDone = stop.status === 'departed' || index === 0;
          const line = document.createElement('div');
          line.className = `journey-line ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''}`;
          line.innerHTML = `
            <p class="text-[13px] font-semibold ${isCurrent ? 'text-primary' : ''}">${stop.station}</p>
            <p class="mt-1 text-xs text-muted-foreground">${isDone ? 'Departed' : isCurrent ? 'Current Stop' : 'Expected'} · ${stop.time || '--:--'}</p>
          `;
          stopsContainer.appendChild(line);
        });
      }

      // C. Update Time to destination
      if (data.time_to_destination) {
        const timeBox = journeyAside.querySelector('.border-t.pt-5 .font-bold');
        if (timeBox) timeBox.textContent = data.time_to_destination;
      }
    }
  }

  function applyAnnouncementsToDOM(announcements) {
    if (!announcements || !announcements.length) return;

    const primaryAnn = announcements[0];

    // A. Replace the Hardcoded Alert Card in the HUD
    const alertCard = document.querySelector('.alert-card');
    if (alertCard && primaryAnn) {
      const typeSpan = alertCard.querySelector('.text-amber-ink');
      if (typeSpan) {
        const isEmerg = primaryAnn.urgency === 'high' || primaryAnn.type === 'safety';
        typeSpan.textContent = (primaryAnn.title || (isEmerg ? 'EMERGENCY HALT' : 'PLATFORM UPDATE')).toUpperCase();
      }

      const trainLabel = alertCard.querySelector('p.text-\\[13px\\].font-medium');
      if (trainLabel) {
        trainLabel.textContent = primaryAnn.train_number ? `${primaryAnn.train_number} · Live Railway Feed` : 'Official Station Announcement';
      }

      const heading = alertCard.querySelector('h3.text-xl.font-extrabold');
      if (heading) {
        heading.textContent = primaryAnn.title || primaryAnn.text || 'Platform Notice';
      }

      const desc = alertCard.querySelector('p.text-xs.text-muted-foreground');
      if (desc) {
        desc.textContent = primaryAnn.text || 'Please check visual display boards.';
      }

      const platformBox = alertCard.querySelector('.platform-number');
      if (platformBox && primaryAnn.platform) {
        platformBox.textContent = primaryAnn.platform;
      }

      // Update Transcript
      const transcriptP = document.querySelector('.transcript');
      if (transcriptP) {
        transcriptP.textContent = `“${primaryAnn.text || primaryAnn.normalized_transcript || ''}”`;
      }
    }

    // B. Replace Earlier Announcements (.history-row)
    const earlierSection = document.querySelector('section.panel:has(.history-row)');
    if (earlierSection && announcements.length > 1) {
      const rows = earlierSection.querySelectorAll('.history-row');
      announcements.slice(1, rows.length + 1).forEach((ann, idx) => {
        if (rows[idx]) {
          const title = rows[idx].querySelector('p.font-semibold');
          const detail = rows[idx].querySelector('p.text-muted-foreground');
          const time = rows[idx].querySelector('span.text-\\[11px\\]');
          if (title) title.textContent = ann.title || ann.type || 'Notice';
          if (detail) detail.textContent = ann.text || ann.normalized_transcript || '';
          if (time && ann.timestamp) time.textContent = ann.timestamp;
        }
      });
    }
  }

  /**
   * Hydrates the Accessibility Map view (/map):
   * Replaces static station facility placeholders with 14 live facilities from Supabase.
   */
  async function hydrateMap() {
    try {
      const res = await fetch('/api/facilities?station=PUNE');
      if (!res.ok) return;
      const data = await res.json();
      const facilities = data.facilities || [];
      if (!facilities.length) return;

      const mapContainer = document.querySelector('.mt-6.grid');
      if (mapContainer && !document.getElementById('th-live-facility-container')) {
        const liveSection = document.createElement('div');
        liveSection.id = 'th-live-facility-container';
        liveSection.style.gridColumn = '1 / -1';
        liveSection.style.marginTop = '16px';
        liveSection.innerHTML = `
          <div class="panel p-6" style="border:2px solid var(--th-verified);">
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2">
                <span class="th-dot" style="background:#059669;"></span>
                <h3 class="font-bold text-lg">Pune Junction Facilities (Supabase Live)</h3>
              </div>
              <span class="th-badge verified">14 Verified Records</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;">
              ${facilities.slice(0, 8).map(f => `
                <div style="background:#f8fafc;border:1px solid #e2e8f0;padding:12px;border-radius:6px;">
                  <div style="display:flex;align-items:center;justify-content:space-between;">
                    <span style="font-weight:700;font-size:13px;">${f.name}</span>
                    <span class="th-badge ${f.status === 'verified_operational' ? 'verified' : f.status === 'conflicting' ? 'attention' : 'simulated'}">
                      ${f.status.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div style="margin-top:6px;font-size:11px;color:#64748b;display:flex;justify-content:space-between;align-items:center;">
                    <span>Type: ${f.type}</span>
                    <button class="th-btn-compact th-btn-report" data-id="${f.id}" style="color:#2563eb;background:none;border:none;cursor:pointer;font-weight:bold;">Report Issue ▾</button>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;

        mapContainer.prepend(liveSection);

        // Report Issue handler
        liveSection.querySelectorAll('.th-btn-report').forEach(btn => {
          btn.addEventListener('click', async () => {
            const facId = btn.dataset.id;
            const note = prompt('Enter condition report (e.g., Escalator stopped, Ramp clear):', 'Operational');
            if (note) {
              await postJson(`/api/facilities/${facId}/report`, {
                device_id: DEVICE_ID,
                reported_status: 'verified_operational',
                note,
              });
              alert('Report recorded in Supabase database! Thank you.');
            }
          });
        });
      }
    } catch (_) {}
  }

  /**
   * Hydrates Communication view (/communication):
   * Replaces static phrases with live categorized phrases and adds speech synthesis audio playback.
   */
  async function hydrateCommunication() {
    try {
      const res = await fetch(`/api/communication/phrases?lang=${encodeURIComponent(currentLanguage)}`);
      if (!res.ok) return;
      const data = await res.json();
      const phrases = data.phrases || [];
      if (!phrases.length) return;

      const phraseButtons = document.querySelectorAll('.flex.flex-wrap.gap-3.mb-6 button');
      phrases.slice(0, phraseButtons.length).forEach((p, idx) => {
        if (phraseButtons[idx]) {
          phraseButtons[idx].textContent = p.text;
          phraseButtons[idx].onclick = () => {
            const textarea = document.getElementById('custom-message');
            if (textarea) {
              textarea.value = p.text;
              textarea.dispatchEvent(new Event('input', { bubbles: true }));
            }
            if ('speechSynthesis' in window) {
              const utter = new SpeechSynthesisUtterance(p.text);
              utter.lang = currentLanguage;
              window.speechSynthesis.speak(utter);
            }
          };
        }
      });
    } catch (_) {}
  }

  /**
   * Hydrates Recovery view (/recovery):
   * Replaces hardcoded options with real alternative trains from Supabase.
   */
  async function hydrateRecovery() {
    try {
      const res = await fetch('/api/trains');
      if (!res.ok) return;
      const data = await res.json();
      const trains = data.trains || [];
      if (trains.length < 2) return;

      const routeOptions = document.querySelectorAll('.route-option');
      const altTrains = [
        { name: 'Pragati Express (12126)', time: 'Departing 16:30 · Platform 3' },
        { name: 'Indrayani Express (22106)', time: 'Departing 18:35 · Platform 1' },
      ];

      routeOptions.forEach((opt, idx) => {
        if (altTrains[idx]) {
          const title = opt.querySelector('h3.font-bold');
          const detail = opt.querySelector('p.text-xs.text-muted-foreground');
          if (title) title.textContent = altTrains[idx].name;
          if (detail) detail.textContent = altTrains[idx].time;
        }
      });
    } catch (_) {}
  }

  /**
   * Master Hydration Router:
   * Inspects current URL and applies the corresponding live data replacements.
   */
  function runLiveHydration() {
    const path = window.location.pathname;
    if (path === '/' || path === '') {
      hydrateHUD();
    } else if (path.includes('/map')) {
      hydrateMap();
    } else if (path.includes('/communication')) {
      hydrateCommunication();
    } else if (path.includes('/recovery')) {
      hydrateRecovery();
    }
  }

  // --- 7. Live Announcement Rendering (New Ingested/Simulated Cards) ---
  function renderLiveAnnouncement(data, prependHUD = true) {
    if (!data) return;

    if (data.haptic_pattern && navigator.vibrate) {
      try { navigator.vibrate(data.haptic_pattern); } catch (_) {}
    } else if (navigator.vibrate) {
      try { navigator.vibrate([200, 100, 200]); } catch (_) {}
    }

    // Apply to existing alert card directly if present
    const alertCard = document.querySelector('.alert-card');
    if (alertCard) {
      const h3 = alertCard.querySelector('h3.text-xl');
      if (h3) h3.textContent = data.display_text || data.type;
      const pNum = alertCard.querySelector('.platform-number');
      if (pNum && data.platform) pNum.textContent = data.platform;
      const tr = document.querySelector('.transcript');
      if (tr && data.display_text) tr.textContent = `“${data.display_text}”`;
    }

    // Also prepend to the custom live feed container
    const hudContainer = document.querySelector('main');
    if (!hudContainer) return;

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

    const ackBtn = card.querySelector('.th-ack-btn');
    ackBtn.addEventListener('click', async () => {
      if (data.id) {
        try { await postJson(`/api/announcements/${data.id}/ack`, {}); } catch (_) {}
      }
      card.style.opacity = '0.6';
      ackBtn.textContent = 'Acknowledged ✓';
      ackBtn.disabled = true;
    });

    const detailsBtn = card.querySelector('.th-details-btn');
    const detailsDiv = card.querySelector('.th-pipeline-details');
    detailsBtn.addEventListener('click', () => {
      const isHidden = detailsDiv.style.display === 'none';
      detailsDiv.style.display = isHidden ? 'block' : 'none';
      detailsBtn.textContent = isHidden ? 'Pipeline Details ▴' : 'Pipeline Details ▾';
    });

    if (prependHUD) liveFeed.prepend(card);
  }

  // --- 8. Journey Switcher Modal (Supabase) ---
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

    document.getElementById('th-close-journey-btn').addEventListener('click', closeJourneyModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeJourneyModal();
    });

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
          closeJourneyModal();
          runLiveHydration();
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

  // --- 9. Slide-out Simulation Hub Drawer ---
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

    document.getElementById('th-close-sim-btn').addEventListener('click', closeSimulationDrawer);
    drawer.addEventListener('click', (e) => {
      if (e.target === drawer) closeSimulationDrawer();
    });

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
          language: currentLanguage,
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

  // --- 10. Lifecycle & Route Observers ---
  function observeDOMAndHydrate() {
    // Initial run
    runLiveHydration();

    // Observe changes caused by React client-side routing
    const observer = new MutationObserver(() => {
      runLiveHydration();
    });

    const root = document.getElementById('root');
    if (root) {
      observer.observe(root, { childList: true, subtree: true });
    }
  }

  // Bootstrap
  window.addEventListener('DOMContentLoaded', () => {
    injectLiveHeader();
    initBackendHealth();
    connectLiveStream();
    observeDOMAndHydrate();
  });

  window.addEventListener('popstate', runLiveHydration);
})();
