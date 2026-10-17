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
    """Ensure execution occurs strictly within the local .venv.
    Skipped automatically on cloud hosts (Render, Railway, etc.) where
    a managed Python environment is already active."""
    # Skip on any cloud/CI environment — they manage their own venv
    cloud_signals = ("RENDER", "RAILWAY_ENVIRONMENT", "HEROKU_APP_NAME", "CI")
    if any(os.environ.get(s) for s in cloud_signals):
        return
    # Skip if .venv doesn't exist and we're not on Windows dev machine
    if not os.path.exists(VENV_PYTHON) and sys.platform != "win32":
        return
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
# Register TransitHear blueprints
# -------------------------------------------------------------
from transithear.routes.health import bp as health_bp
from transithear.routes.journey import bp as journey_bp
from transithear.routes.announce import bp as announce_bp
from transithear.routes.stream import bp as stream_bp
from transithear.routes.simulate import bp as simulate_bp
from transithear.routes.facilities import bp as facilities_bp
from transithear.routes.recovery import bp as recovery_bp
from transithear.routes.comm import bp as comm_bp
from transithear.routes.prefs import bp as prefs_bp
from transithear.routes.audit import bp as audit_bp
from transithear.routes.transit import bp as transit_bp

for bp in (health_bp, journey_bp, announce_bp, stream_bp, simulate_bp,
           facilities_bp, recovery_bp, comm_bp, prefs_bp, audit_bp, transit_bp):
    app.register_blueprint(bp)

# -------------------------------------------------------------
# Live demo page routes
# -------------------------------------------------------------

@app.route("/live")
def live_page():
    return render_template("live.html")

@app.route("/live/audit")
def live_audit_page():
    return render_template("audit.html")

# -------------------------------------------------------------
# Static Asset Delivery & PWA Serving (Zero Node.js dependency)
# -------------------------------------------------------------

@app.route("/assets/<path:filename>")
@app.route("/<path:prefix>/assets/<path:filename>")
def serve_assets(filename, prefix=None):
    """Serve bundled JS/CSS chunks directly from static/assets."""
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(os.path.join(assets_dir, filename)):
        return send_from_directory(assets_dir, filename)
    return ("Asset not found", 404)

@app.route("/live/<path:filename>")
def serve_live_static(filename):
    """Serve static files for the /live page."""
    live_dir = os.path.join(STATIC_DIR, "live")
    full_path = os.path.join(live_dir, filename)
    if os.path.exists(full_path):
        return send_from_directory(live_dir, filename)
    return ("File not found", 404)

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
    static_index = get_asset_file("index.html")
    if static_index and os.path.isfile(static_index):
        response = make_response(send_file(static_index))
        response.headers["Cache-Control"] = "no-cache"
        return response

    template_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(template_path):
        return render_template("index.html")

    return """
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><title>TransitHear</title></head>
    <body style="font-family:sans-serif;padding:40px;text-align:center;">
        <h1>TransitHear Python Backend Active</h1>
        <p>Please ensure <code>static/index.html</code> is present.</p>
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
    # Do not mask missing live or API routes with the React SPA shell
    if path.startswith("live/") or path.startswith("api/"):
        return ("Not Found", 404)
    return render_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    args = [a.lower() for a in sys.argv[1:]]
    # Check if dev mode is requested or default
    is_dev = "dev" in args or os.environ.get("FLASK_DEBUG", "1") in ("1", "true", "True")

    from transithear.config import SUPABASE_ENABLED, GEMINI_ENABLED, GEMINI_MODEL
    from transithear.db import get_repo, is_store_degraded
    _repo = get_repo()

    print("\n" + "=" * 62)
    print(f"[*] TransitHear Server: http://127.0.0.1:{port}")
    print(f"[*] Local Environment: {sys.executable}")
    print(f"[*] Mode: {'Development (Hot Reloading Active)' if is_dev else 'Production'}")
    print(f"[*] Store: {'Supabase' if SUPABASE_ENABLED and not is_store_degraded() else 'MemoryRepo (seed data)'}")
    print(f"[*] Gemini: {'ENABLED (' + GEMINI_MODEL + ')' if GEMINI_ENABLED else 'DISABLED (rules fallback)'}")
    print(f"[*] Live demo: http://127.0.0.1:{port}/live")
    print(f"[*] Zero node_modules dependency | Full PWA enabled")
    print("=" * 62 + "\n")
    app.run(host="0.0.0.0", port=port, debug=is_dev)