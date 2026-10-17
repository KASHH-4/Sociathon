"""Journey blueprint."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import get_repo
from ..resolver import _build_candidate_set

bp = Blueprint("journey", __name__)


@bp.route("/api/journey", methods=["POST"])
def create_journey():
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", "").strip()
    mode = data.get("mode", "route")
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400
    if mode not in ("booking", "route"):
        return jsonify({"error": "mode must be 'booking' or 'route'"}), 400

    origin = data.get("origin", "").strip()
    dest = data.get("destination", "").strip()
    if not origin or not dest:
        return jsonify({"error": "origin and destination are required"}), 400

    repo = get_repo()

    # Resolve station codes (accept code or name)
    def _resolve_station(val: str) -> str | None:
        stations = repo.get_stations()
        # Try exact code match first
        for s in stations:
            if s.get("code", "").lower() == val.lower():
                return s["code"]
        # Fuzzy name match
        from ..normalize import match_alias
        match = match_alias(val, stations)
        return match["code"] if match else val.upper()

    origin_code = _resolve_station(origin)
    dest_code = _resolve_station(dest)

    train_number = data.get("train_number")
    if mode == "booking" and not train_number:
        return jsonify({"error": "train_number is required for booking mode"}), 400

    # Deactivate previous journeys for this device
    repo.deactivate_journeys(device_id)

    journey_data = {
        "device_id": device_id,
        "mode": mode,
        "train_number": train_number,
        "origin_code": origin_code,
        "dest_code": dest_code,
        "boarding_date": data.get("boarding_date"),
        "status": "active",
    }
    journey = repo.create_journey(journey_data)

    # Build candidate set to return
    all_trains = repo.get_trains()
    all_stops = repo.get_stops()
    candidate_numbers = _build_candidate_set(journey, all_trains, all_stops)
    candidates = [t for t in all_trains if t.get("number") in candidate_numbers]

    return jsonify({
        "journey": journey,
        "candidates": candidates,
    }), 201


@bp.route("/api/journey/current", methods=["GET"])
def current_journey():
    device_id = request.args.get("device_id", "").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400

    repo = get_repo()
    journey = repo.get_active_journey(device_id)
    if not journey:
        return jsonify({"journey": None}), 200

    # Build progress from stops
    train_number = journey.get("train_number")
    stops = repo.get_stops(train_number) if train_number else []
    stops_sorted = sorted(stops, key=lambda s: s.get("seq", 0))

    stop_list = []
    for s in stops_sorted:
        stop_list.append({
            "station_code": s.get("station_code"),
            "arr": str(s.get("arr", "")),
            "dep": str(s.get("dep", "")),
            "platform": s.get("platform"),
            "seq": s.get("seq"),
        })

    return jsonify({
        "journey": journey,
        "stops": stop_list,
        "simulated": True,
    })


@bp.route("/api/trains", methods=["GET"])
def search_trains():
    q = request.args.get("q", "").strip()
    repo = get_repo()
    trains = repo.get_trains(q or None)
    return jsonify({"trains": trains[:20]})


@bp.route("/api/stations", methods=["GET"])
def search_stations():
    q = request.args.get("q", "").strip()
    repo = get_repo()
    stations = repo.get_stations(q or None)
    return jsonify({"stations": stations[:20]})
