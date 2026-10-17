"""Simulate blueprint — all scenarios labelled simulated: true."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import get_repo
from ..pipeline import process
from ..events import push, broadcast

bp = Blueprint("simulate", __name__)

# ---------------------------------------------------------------------------
# Canned transcripts per scenario
# ---------------------------------------------------------------------------
_SCENARIOS: dict[str, dict] = {
    "platform_change": {
        "transcript": (
            "Attention passengers. Train number 12123 Deccan Queen Express "
            "will now arrive at platform 5 instead of platform 2. "
            "All passengers please proceed to platform 5. "
            "Kripaya dhyan den — train 12123 Deccan Queen platform 5 par aayegi."
        ),
        "insert_official": {
            "kind": "platform_change",
            "new_platform": 5,
            "train_number": "12123",
            "station_code": "PUNE",
        },
    },
    "delay": {
        "transcript": (
            "We regret to announce that train 12125 Pragati Express is running "
            "approximately 25 minutes late. The train is now expected to depart "
            "Pune Junction at 08:50 hours. Inconvenience is regretted."
        ),
        "insert_official": {
            "kind": "delay",
            "delay_minutes": 25,
            "train_number": "12125",
            "station_code": "PUNE",
        },
    },
    "early_arrival": {
        "transcript": (
            "Good news for passengers of train 12128 Intercity Express. "
            "The train is arriving ahead of schedule and is expected at "
            "Lonavala platform 2 in approximately five minutes."
        ),
    },
    "cancellation": {
        "transcript": (
            "Passengers are informed that train number 11009 Sinhagad Express "
            "scheduled to depart from CSMT has been cancelled today. "
            "Passengers are advised to check for alternative trains."
        ),
        "insert_official": {
            "kind": "cancellation",
            "train_number": "11009",
            "station_code": "CSMT",
        },
    },
    "safety": {
        "transcript": (
            "Attention all passengers on platform 3. Please mind the gap "
            "when boarding the train. Keep away from the edge of the platform. "
            "An emergency situation has been reported. All passengers please "
            "follow instructions from railway staff."
        ),
    },
    "misrecognized_number": {
        # One digit off: 12126 instead of 12128 — but train name present
        "transcript": (
            "Train one two one two six Intercity Express will arrive at "
            "platform 4 at Pune Junction. Passengers please be ready."
        ),
    },
    "other_train": {
        # 12009 Shatabdi — not on CSMT→PUNE corridor
        "transcript": (
            "Train 12009 Shatabdi Express from Mumbai Central to Ahmedabad "
            "will depart from platform 7. All passengers please proceed."
        ),
    },
    "noise": {
        "transcript": "Testing testing one two three. Microphone check. Is this on?",
    },
}


@bp.route("/api/simulate/announcement", methods=["POST"])
def simulate_announcement():
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", "demo-device").strip()
    scenario = data.get("scenario", "platform_change")

    if scenario not in _SCENARIOS:
        return jsonify({
            "error": f"Unknown scenario. Valid: {list(_SCENARIOS.keys())}"
        }), 400

    sc = _SCENARIOS[scenario]
    repo = get_repo()

    # Insert a matching official update if the scenario needs it
    official_inserted = None
    if "insert_official" in sc:
        official_inserted = repo.create_official_update({
            **sc["insert_official"],
            "source": "simulated",
        })

    result = process(
        device_id=device_id,
        transcript=sc["transcript"],
        stt_source="simulated",
        stt_confidence=0.82,
        language="en-IN",
        simulated=True,
    )
    result["simulated"] = True
    result["scenario"] = scenario
    if official_inserted:
        result["official_update_inserted"] = official_inserted

    return jsonify(result), 200


@bp.route("/api/simulate/official-update", methods=["POST"])
def simulate_official_update():
    data = request.get_json(silent=True) or {}
    required = ["train_number", "station_code", "kind"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400
    valid_kinds = {"platform_change", "delay", "early_arrival", "cancellation"}
    if data["kind"] not in valid_kinds:
        return jsonify({"error": f"kind must be one of {valid_kinds}"}), 400

    repo = get_repo()
    row = repo.create_official_update({
        "train_number": data["train_number"],
        "station_code": data["station_code"],
        "kind": data["kind"],
        "new_platform": data.get("new_platform"),
        "delay_minutes": data.get("delay_minutes"),
        "source": "simulated",
    })
    return jsonify({"update": row, "simulated": True}), 201


@bp.route("/api/simulate/emergency", methods=["POST"])
def simulate_emergency():
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", "").strip()
    message = data.get("message", "Emergency on platform 3. Please follow staff instructions.")
    kind = data.get("kind", "platform_emergency")

    repo = get_repo()
    event = repo.create_emergency({
        "device_id": device_id or "all",
        "kind": kind,
        "message": message,
    })

    # Broadcast to all or specific device
    payload = {**event, "simulated": True, "haptic_pattern": [800, 200, 800, 200, 800]}
    if device_id:
        push(device_id, "emergency", payload)
    else:
        broadcast("emergency", payload)

    return jsonify({"event": event, "simulated": True}), 201
