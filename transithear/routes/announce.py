"""Announcements blueprint."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import get_repo
from ..pipeline import process

bp = Blueprint("announce", __name__)


@bp.route("/api/announcements/ingest", methods=["POST"])
def ingest():
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", "").strip()
    transcript = data.get("transcript", "").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400
    if not transcript:
        return jsonify({"error": "transcript is required"}), 400

    from ..limits import check_transcript
    ok, err = check_transcript(transcript)
    if not ok:
        status = 413 if "exceeds maximum" in err else 400
        return jsonify({"error": err}), status

    result = process(
        device_id=device_id,
        transcript=transcript,
        stt_source=data.get("stt_source", "browser"),
        stt_confidence=data.get("stt_confidence"),
        language=data.get("language"),
        simulated=bool(data.get("simulated", False)),
    )

    if result.get("rate_limited"):
        return jsonify({"error": result["reason"]}), 429

    return jsonify(result), 200


@bp.route("/api/announcements", methods=["GET"])
def list_announcements():
    device_id = request.args.get("device_id", "").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400
    limit = min(int(request.args.get("limit", 20)), 100)
    repo = get_repo()
    anns = repo.list_announcements(device_id, limit=limit)
    return jsonify({"announcements": anns})


@bp.route("/api/announcements/<ann_id>/ack", methods=["POST"])
def acknowledge(ann_id: str):
    repo = get_repo()
    ann = repo.acknowledge_announcement(ann_id)
    if ann is None:
        return jsonify({"error": "Announcement not found"}), 404
    return jsonify({"announcement": ann})


# Keep existing stub path working — now DB-backed
@bp.route("/api/transit/announcements", methods=["GET"])
def transit_announcements_compat():
    """Backwards-compatible endpoint: returns recent announcements or seed data."""
    device_id = request.args.get("device_id", "").strip()
    repo = get_repo()
    if device_id:
        anns = repo.list_announcements(device_id, limit=10)
        if anns:
            return jsonify({"announcements": anns})
    # Fall back to the original static response shape
    return jsonify({
        "announcements": [
            {
                "id": "ann-101",
                "timestamp": "19:06",
                "type": "audio_transcript",
                "urgency": "normal",
                "title": "Approaching Lonavala",
                "text": "Approaching Lonavala station. Doors will open on the left side. Mind the gap.",
                "sign_language_available": True,
                "verified": True,
                "simulated": True,
            },
        ]
    })
