import os
import sys

# -------------------------------------------------------------
# Enforce Local Virtual Environment (.venv) First
# -------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, ".venv")

if sys.platform == "win32":
    VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
else:
    VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")

def enforce_local_venv():
    """Ensure execution occurs strictly within the local .venv."""
    if not os.path.exists(VENV_PYTHON):
        import subprocess
        print(f"[TransitHear] Creating local virtual environment in {VENV_DIR}...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR], cwd=BASE_DIR)
        print("[TransitHear] Virtual environment created.")
        subprocess.check_call([VENV_PYTHON, "-m", "pip", "install", "-r", "requirements.txt"], cwd=BASE_DIR)

    current_py = os.path.normpath(sys.executable).lower()
    target_py = os.path.normpath(VENV_PYTHON).lower()
    if current_py != target_py:
        import subprocess
        print(f"[TransitHear] Enforcing local virtual environment: {VENV_PYTHON}")
        ret = subprocess.call([VENV_PYTHON] + sys.argv, cwd=BASE_DIR)
        sys.exit(ret)

enforce_local_venv()

# -------------------------------------------------------------
# Imports (Loaded exclusively from .venv)
# -------------------------------------------------------------
import mimetypes
from flask import Flask, send_from_directory, jsonify, request, send_file, make_response, render_template
from flask_cors import CORS

# Configure UTF-8 console output for Windows shells
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Register critical MIME types
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("application/javascript", ".js")

STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
CORS(app)

def get_asset_file(relative_path):
    """Find a static file in the static directory."""
    full_path = os.path.join(STATIC_DIR, relative_path)
    return full_path if os.path.exists(full_path) else None

# -------------------------------------------------------------
# TransitHear REST API Endpoints (Pure Python)
# -------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint confirming Python Flask backend in local venv."""
    return jsonify({
        "status": "online",
        "app": "TransitHear",
        "version": "1.0.0",
        "backend": "Python Flask (Local .venv Only)",
        "python_executable": sys.executable,
        "is_local_venv": os.path.normpath(sys.executable).lower() == os.path.normpath(VENV_PYTHON).lower(),
        "pwa": True,
        "static_ready": os.path.exists(STATIC_DIR)
    })

@app.route("/api/transit/status", methods=["GET"])
def transit_status():
    """Simulated Deccan Queen 12128 live journey status."""
    return jsonify({
        "train_number": "12128",
        "train_name": "Deccan Queen Express",
        "origin": "Mumbai CSMT",
        "destination": "Pune Junction",
        "current_station": "Lonavala",
        "current_platform": 2,
        "status": "In Progress",
        "delay_minutes": 2,
        "speed_kmh": 68,
        "time_to_destination": "1 hr 17 min",
        "stops": [
            {"station": "Mumbai CSMT", "time": "17:10", "status": "departed"},
            {"station": "Lonavala", "time": "19:08", "status": "current"},
            {"station": "Shivajinagar", "time": "20:10", "status": "expected"},
            {"station": "Pune Junction", "time": "20:25", "status": "expected"}
        ],
        "step_free_destination_verified": True
    })

@app.route("/api/transit/announcements", methods=["GET"])
def transit_announcements():
    """Audio announcements converted into visual cards."""
    return jsonify({
        "announcements": [
            {
                "id": "ann-101",
                "timestamp": "19:06",
                "type": "audio_transcript",
                "urgency": "normal",
                "title": "Approaching Lonavala",
                "text": "Approaching Lonavala station. Doors will open on the left side. Commuters are requested to mind the gap.",
                "sign_language_available": True,
                "verified": True
            },
            {
                "id": "ann-102",
                "timestamp": "18:45",
                "type": "alert",
                "urgency": "high",
                "title": "Platform 3 Caution",
                "text": "Due to track maintenance, boarding at Shivajinagar will be shifted to Platform 1. Tactile pathways active.",
                "sign_language_available": True,
                "verified": True
            }
        ]
    })

@app.route("/api/facilities", methods=["GET"])
def accessible_facilities():
    """Accessibility facilities directory for commuter navigation."""
    station = request.args.get("station", "Pune Junction")
    return jsonify({
        "station": station,
        "facilities": [
            {"name": "Step-free Ramp (Main Entrance)", "status": "Operational", "accessible": True},
            {"name": "Braille & Tactile Guidance Path", "status": "Operational", "accessible": True},
            {"name": "Visual LED Multi-lingual Display", "status": "Active", "accessible": True},
            {"name": "Deaf Commuter Assistance Desk", "status": "Staffed until 22:00", "accessible": True},
            {"name": "Platform 1 Elevator", "status": "Operational", "accessible": True},
            {"name": "Platform 2 Escalator", "status": "Operational", "accessible": True}
        ]
    })

@app.route("/api/communication/phrases", methods=["GET"])
def communication_phrases():
    """Quick flashcards for communicating with station staff."""
    return jsonify({
        "phrases": [
            {"category": "assistance", "text": "I am Deaf / Hard of Hearing. Please communicate by writing or pointing."},
            {"category": "transit", "text": "Which platform does train 12128 Deccan Queen arrive at?"},
            {"category": "emergency", "text": "I need step-free access assistance to the exit."},
            {"category": "tickets", "text": "Can you check my digital ticket QR code?"}
        ]
    })

@app.route("/api/wearable/simulate-haptic", methods=["POST"])
def simulate_haptic():
    """Simulate wearable pulse triggers."""
    data = request.get_json(silent=True) or {}
    pattern = data.get("pattern", "announcement_pulse")
    return jsonify({
        "status": "success",
        "pattern": pattern,
        "haptic_profile": {
            "vibrations": [200, 100, 200] if pattern == "alert" else [150, 80, 150, 80, 300],
            "intensity": "high" if pattern == "alert" else "medium"
        },
        "delivered": True
    })

# -------------------------------------------------------------
# Static Asset Delivery & PWA Serving (Zero Node.js dependency)
# -------------------------------------------------------------

@app.route("/assets/<path:filename>")
def serve_assets(filename):
    """Serve bundled JS/CSS chunks directly from static/assets."""
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(os.path.join(assets_dir, filename)):
        return send_from_directory(assets_dir, filename)
    return ("Asset not found", 404)

@app.route("/sw.js")
def service_worker():
    """Serve PWA Service Worker with required headers for immediate activation."""
    sw_file = get_asset_file("sw.js")
    if sw_file:
        response = make_response(send_file(sw_file, mimetype="application/javascript"))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Service-Worker-Allowed"] = "/"
        return response
    return ("Service worker not found", 404)

@app.route("/manifest.webmanifest")
@app.route("/manifest.json")
def pwa_manifest():
    """Serve PWA Manifest."""
    for name in ["manifest.webmanifest", "manifest.json"]:
        manifest_file = get_asset_file(name)
        if manifest_file:
            return send_file(manifest_file, mimetype="application/manifest+json")
    return ("Manifest not found", 404)

@app.route("/icons/<path:filename>")
def serve_icons(filename):
    """Serve application icons."""
    icons_dir = os.path.join(STATIC_DIR, "icons")
    if os.path.exists(os.path.join(icons_dir, filename)):
        return send_from_directory(icons_dir, filename)
    return ("Icon not found", 404)

@app.route("/offline.html")
def offline_page():
    """Serve offline fallback page."""
    offline_file = get_asset_file("offline.html")
    if offline_file:
        return send_file(offline_file)
    return ("Offline page not found", 404)

@app.route("/favicon.ico")
def favicon():
    """Serve favicon."""
    fav = get_asset_file("favicon.ico")
    if fav:
        return send_file(fav)
    return ("Favicon not found", 404)

# -------------------------------------------------------------
# Frontend SPA & Flask Template Routes
# -------------------------------------------------------------

def render_app():
    """Render the application shell for any client-side route."""
    template_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(template_path):
        return render_template("index.html")
    
    static_index = get_asset_file("index.html")
    if static_index:
        response = make_response(send_file(static_index))
        response.headers["Cache-Control"] = "no-cache"
        return response

    return """
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><title>TransitHear</title></head>
    <body style="font-family:sans-serif;padding:40px;text-align:center;">
        <h1>TransitHear Python Backend Active</h1>
        <p>Please ensure <code>static/</code> or <code>templates/index.html</code> is present.</p>
    </body>
    </html>
    """, 200

@app.route("/")
@app.route("/map")
@app.route("/communication")
@app.route("/recovery")
@app.route("/wearable")
def app_views():
    """Serve TransitHear views directly."""
    return render_app()

@app.route("/<path:path>")
def catch_all(path):
    """Catch-all for SPA subroutes or static files."""
    static_file = get_asset_file(path)
    if static_file and os.path.isfile(static_file):
        return send_file(static_file)
    return render_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    args = [a.lower() for a in sys.argv[1:]]
    # Check if dev mode is requested or default
    is_dev = "dev" in args or os.environ.get("FLASK_DEBUG", "1") in ("1", "true", "True")
    
    print("\n" + "=" * 62)
    print(f"[*] TransitHear Server: http://127.0.0.1:{port}")
    print(f"[*] Local Environment: {sys.executable}")
    print(f"[*] Mode: {'Development (Hot Reloading Active)' if is_dev else 'Production'}")
    print(f"[*] Zero node_modules dependency | Full PWA enabled")
    print("=" * 62 + "\n")
    app.run(host="0.0.0.0", port=port, debug=is_dev)
