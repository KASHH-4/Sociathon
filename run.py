"""
TransitHear Pure Python Runner
Enforces 100% local virtual environment (.venv). Zero node_modules required.

Usage:
  python run.py dev    (Development server with hot reloading on http://127.0.0.1:5000)
  python run.py        (Standard server)
"""

import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, ".venv")

if sys.platform == "win32":
    VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
else:
    VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")

def ensure_venv():
    """Ensure running inside local .venv. If not, auto-create and re-execute."""
    if not os.path.exists(VENV_PYTHON):
        print(f"[TransitHear] Creating local Python virtual environment in {VENV_DIR}...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR], cwd=BASE_DIR)
        print("[TransitHear] Virtual environment created.")
        subprocess.check_call([VENV_PYTHON, "-m", "pip", "install", "-r", "requirements.txt"], cwd=BASE_DIR)

    current_py = os.path.normpath(sys.executable).lower()
    target_py = os.path.normpath(VENV_PYTHON).lower()
    if current_py != target_py:
        print(f"[TransitHear] Enforcing local virtual environment: {VENV_PYTHON}")
        ret = subprocess.call([VENV_PYTHON] + sys.argv, cwd=BASE_DIR)
        sys.exit(ret)

ensure_venv()

if __name__ == "__main__":
    import app
    port = int(os.environ.get("PORT", 5000))
    args = [a.lower() for a in sys.argv[1:]]
    is_dev = "dev" in args or len(args) == 0 or os.environ.get("FLASK_DEBUG", "1") in ("1", "true", "True")
    local_ip = app.get_local_ip() if hasattr(app, "get_local_ip") else "127.0.0.1"
    
    print("\n" + "=" * 62)
    print(f"[*] TransitHear Local:   http://127.0.0.1:{port}")
    print(f"[*] Same Network (LAN): http://{local_ip}:{port}")
    print(f"[*] Live Demo (LAN):    http://{local_ip}:{port}/live")
    print(f"[*] Local Environment:  {sys.executable}")
    print(f"[*] Mode:               {'Development (Hot Reloading Active)' if is_dev else 'Production'}")
    print(f"[*] Zero node_modules dependency | Full PWA enabled")
    print("=" * 62 + "\n")
    app.app.run(host="0.0.0.0", port=port, debug=is_dev)
