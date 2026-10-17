"""Health check blueprint."""
from __future__ import annotations

from flask import Blueprint, jsonify

from ..config import SUPABASE_ENABLED, GEMINI_ENABLED, GEMINI_MODEL
from ..db import get_repo, is_store_degraded

bp = Blueprint("health", __name__)


@bp.route("/api/health", methods=["GET"])
def health():
    repo = get_repo()
    store = "supabase" if (SUPABASE_ENABLED and not is_store_degraded()) else "memory"
    return jsonify({
        "status": "online",
        "app": "TransitHear",
        "version": "2.0.0",
        "integrations": {
            "supabase": SUPABASE_ENABLED and not is_store_degraded(),
            "gemini": GEMINI_ENABLED,
            "gemini_model": GEMINI_MODEL if GEMINI_ENABLED else None,
            "official_railway_feed": False,   # always simulated
            "isl_translation": False,          # not yet wired
            "wearable": False,                 # simulated
        },
        "store": store,
        "store_degraded": is_store_degraded(),
        "simulated": {
            "official_feed": True,
            "wearable": True,
            "isl": True,
        },
        "pwa": True,
    })
