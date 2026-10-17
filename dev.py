"""
TransitHear Dev Shortcut
Runs the Flask application in dev mode strictly using the local .venv.
"""
import sys
import os

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "dev"]
    import app
    app.app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
