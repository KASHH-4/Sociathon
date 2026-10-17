"""Transit status and wearable blueprint (backwards-compatible stubs now DB-backed)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import get_repo

bp = Blueprint("transit", __name__)


@bp.route("/api/transit/status", methods=["GET"])
def transit_status():
    device_id = request.args.get("device_id", "").strip()
    repo = get_repo()

    if device_id:
        journey = repo.get_active_journey(device_id)
        if journey:
            train_number = journey.get("train_number")
            stops = repo.get_stops(train_number) if train_number else []
            stops_sorted = sorted(stops, key=lambda s: s.get("seq", 0))
            train = repo.get_train(train_number) if train_number else None
            return jsonify({
                "train_number": train_number,
                "train_name": train.get("name") if train else "Unknown",
                "origin": journey.get("origin_code"),
                "destination": journey.get("dest_code"),
                "status": "In Progress",
                "stops": [
                    {
                        "station": s.get("station_code"),
                        "time": str(s.get("dep") or s.get("arr") or ""),
                        "platform": s.get("platform"),
                        "status": "expected",
                    }
                    for s in stops_sorted
                ],
                "simulated": True,
            })

    # Fall back to original static shape
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
            {"station": "Pune Junction", "time": "20:25", "status": "expected"},
        ],
        "step_free_destination_verified": True,
        "simulated": True,
    })


@bp.route("/api/wearable/simulate-haptic", methods=["POST"])
def simulate_haptic():
    data = request.get_json(silent=True) or {}
    pattern = data.get("pattern", "announcement_pulse")
    return jsonify({
        "status": "success",
        "pattern": pattern,
        "haptic_profile": {
            "vibrations": [200, 100, 200] if pattern == "alert" else [150, 80, 150, 80, 300],
            "intensity": "high" if pattern == "alert" else "medium",
        },
        "delivered": True,
        "simulated": True,
    })
