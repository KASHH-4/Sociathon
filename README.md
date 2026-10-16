# TransitHear — Accessible Commute & Visual HUD

TransitHear is an accessible transit assistant designed for Deaf and Hard-of-Hearing commuters. It provides clear visual announcements, accessibility maps, communication cards, journey recovery alternatives, and haptic wearable alerts.

**Zero `node_modules` required**: The entire app runs natively via Python Flask. All web assets are pre-packaged into clean, self-contained static web assets and Jinja2 templates.

---

## 🌟 Key Features

- **100% Python Flask Application**: Runs independently without requiring Node.js, `npm`, or `node_modules`.
- **Visual Announcements HUD**: Live simulated journey feed, audio captions, verified transit updates, and ISL (Indian Sign Language) translation toggle.
- **Accessibility Map**: Station facility statuses (tactile pathways, ramps, elevators, hearing induction loops, visual displays).
- **Communication Card**: One-tap communication flashcards and interactive notepad for speaking to station staff.
- **Journey Recovery**: Real-time accessible alternate route suggestions when delays or platform changes occur.
- **Haptics & Wearable**: Simulated wrist vibration alerts for announcements, platform changes, and arrival alerts.
- **Progressive Web App (PWA)**:
  - Installable on desktop and mobile (`manifest.webmanifest`).
  - Offline support powered by Service Worker (`sw.js`).
  - Cache-first strategy for static assets and offline fallback (`offline.html`).
- **REST API Endpoints**:
  - Live journey telemetry, accessibility directory, phrase cards, and haptic pattern triggers.

---

## 🚀 Quick Start (Pure Python Local Environment)

A local Python virtual environment (`.venv`) is configured for the project. No Node.js or `node_modules` is needed.

### 1. Run Development Server

```bash
python run.py dev
```

Or using the direct shortcut:

```bash
python dev.py
```

This starts the application on **http://localhost:5000**.

### 2. Available Commands

```bash
python run.py dev       # Starts Flask in development mode (http://localhost:5000)
python run.py           # Starts Flask in production mode
python run.py install   # Installs Python virtual environment requirements
python dev.py           # Direct shortcut for development
```

---

## 🌐 Normal Static Frontend Hosting (Zero Node.js Required)

For static-only hosting (e.g. GitHub Pages, Netlify, Vercel, S3, or local static server), the frontend is 100% self-contained in `static/` and `index.html`. You do **not** need `node_modules` or `npm`:

```bash
# Preview locally with Python's built-in static server (optional)
python -m http.server 8080 --directory static
```

Configuration files included:
- `vercel.json` (Ready for 1-click Vercel deployments)
- `static/_redirects` (Ready for Netlify / Cloudflare Pages SPA routing)

---

## 🔌 Python Flask API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health status, version, and PWA status |
| `/api/transit/status` | GET | Current train, speed, stops, and delay info |
| `/api/transit/announcements` | GET | Visual audio transcripts & alerts |
| `/api/facilities` | GET | Station accessibility facilities directory |
| `/api/communication/phrases` | GET | Quick commuter communication cards |
| `/api/wearable/simulate-haptic` | POST | Test vibration alert patterns |

---

## 📱 PWA Verification

- **Manifest**: Located at `/manifest.webmanifest` and `/manifest.json`
- **Service Worker**: Served at `/sw.js` with `Service-Worker-Allowed: /`
- **Icons**: 192x192, 512x512, maskable icons, and Apple touch icon in `/icons/`
- **Offline page**: Served at `/offline.html` when network is unavailable
