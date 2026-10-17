"""Recovery blueprint."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import get_repo
from ..extract_gemini import rank_alternatives

bp = Blueprint("recovery", __name__)


@bp.route("/api/recovery", methods=["POST"])
def recovery():
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", "").strip()
    reason = data.get("reason", "Journey disrupted").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400

    repo = get_repo()
    journey = repo.get_active_journey(device_id)

    if not journey:
        return jsonify({"error": "No active journey found"}), 404

    from_code = journey.get("origin_code", "")
    to_code = journey.get("dest_code", "")
    alternatives = repo.get_alternatives(from_code, to_code)

    ranked = rank_alternatives(reason, journey, alternatives)

    return jsonify({
        "journey": journey,
        "reason": reason,
        "alternatives": ranked,
        "simulated": True,
    })
