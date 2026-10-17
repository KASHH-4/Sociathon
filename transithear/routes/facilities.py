"""Facilities blueprint."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import get_repo

bp = Blueprint("facilities", __name__)


@bp.route("/api/facilities", methods=["GET"])
def get_facilities():
    station = request.args.get("station", "").strip()
    repo = get_repo()

    # Resolve station code from query param (may be name or code)
    station_code = None
    if station:
        stations = repo.get_stations()
        for s in stations:
            if (s.get("code", "").lower() == station.lower()
                    or station.lower() in s.get("name", "").lower()):
                station_code = s["code"]
                break
        if not station_code:
            station_code = station.upper()

    facilities = repo.get_facilities(station_code)
    return jsonify({
        "station": station or "all",
        "facilities": facilities,
        "simulated": True,
    })


@bp.route("/api/facilities/<facility_id>/report", methods=["POST"])
def report_facility(facility_id: str):
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id", "").strip()
    reported_status = data.get("reported_status", "").strip()
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400
    valid_statuses = {"present", "verified_operational", "unverified", "outdated", "conflicting"}
    if reported_status and reported_status not in valid_statuses:
        return jsonify({"error": f"reported_status must be one of {valid_statuses}"}), 400

    repo = get_repo()
    report = repo.create_facility_report(facility_id, {
        "device_id": device_id,
        "reported_status": reported_status,
        "note": data.get("note", ""),
    })
    return jsonify({"report": report}), 201
