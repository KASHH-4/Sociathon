"""Preferences blueprint."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import get_repo

bp = Blueprint("prefs", __name__)


@bp.route("/api/preferences", methods=["GET"])
def get_prefs():
    device_id = request.args.get("device_id", "").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400
    repo = get_repo()
    prefs = repo.get_preferences(device_id)
    return jsonify({"preferences": prefs})


@bp.route("/api/preferences", methods=["PUT", "POST"])
def update_prefs():
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", "").strip() or request.args.get("device_id", "").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400

    allowed = {"pa_monitoring", "haptic", "sleep_sentinel", "language", "vibration_patterns"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    repo = get_repo()
    prefs = repo.upsert_preferences(device_id, updates)
    return jsonify({"preferences": prefs})
