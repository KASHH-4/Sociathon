"""
Repository interface + two implementations:
  SupabaseRepo — backed by Supabase / Postgres (supabase-py)
  MemoryRepo   — in-process dicts, seeded from data/seed/*.json

The app creates one global repo at startup via `get_repo()`.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Any

from .config import SUPABASE_ENABLED, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class Repo(ABC):
    # --- Stations ---
    @abstractmethod
    def get_stations(self, q: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_station(self, code: str) -> dict | None: ...

    # --- Trains ---
    @abstractmethod
    def get_trains(self, q: str | None = None) -> list[dict]: ...

    @abstractmethod
    def get_train(self, number: str) -> dict | None: ...

    @abstractmethod
    def get_stops(self, train_number: str | None = None) -> list[dict]: ...

    # --- Journeys ---
    @abstractmethod
    def create_journey(self, data: dict) -> dict: ...

    @abstractmethod
    def get_journey(self, journey_id: str) -> dict | None: ...

    @abstractmethod
    def get_active_journey(self, device_id: str) -> dict | None: ...

    @abstractmethod
    def deactivate_journeys(self, device_id: str) -> None: ...

    # --- Announcements ---
    @abstractmethod
    def create_announcement(self, data: dict) -> dict: ...

    @abstractmethod
    def get_announcement(self, ann_id: str) -> dict | None: ...

    @abstractmethod
    def list_announcements(self, device_id: str, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def acknowledge_announcement(self, ann_id: str) -> dict | None: ...

    # --- Audit log ---
    @abstractmethod
    def create_audit_log(self, data: dict) -> dict: ...

    @abstractmethod
    def list_audit_log(self, limit: int = 50) -> list[dict]: ...

    # --- Official updates ---
    @abstractmethod
    def get_official_updates(self, train_number: str | None = None) -> list[dict]: ...

    @abstractmethod
    def create_official_update(self, data: dict) -> dict: ...

    # --- Facilities ---
    @abstractmethod
    def get_facilities(self, station_code: str | None = None) -> list[dict]: ...

    @abstractmethod
    def create_facility_report(self, facility_id: str, data: dict) -> dict: ...

    @abstractmethod
    def update_facility_status(self, facility_id: str, status: str) -> None: ...

    # --- Alternatives ---
    @abstractmethod
    def get_alternatives(self, from_code: str, to_code: str) -> list[dict]: ...

    # --- Preferences ---
    @abstractmethod
    def get_preferences(self, device_id: str) -> dict: ...

    @abstractmethod
    def upsert_preferences(self, device_id: str, data: dict) -> dict: ...

    # --- Emergency events ---
    @abstractmethod
    def create_emergency(self, data: dict) -> dict: ...


# ---------------------------------------------------------------------------
# MemoryRepo
# ---------------------------------------------------------------------------

_SEED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "seed")


def _load_seed(filename: str) -> Any:
    path = os.path.join(_SEED_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Strip meta key
    if isinstance(data, dict):
        data.pop("_note", None)
        # Return first list value
        for v in data.values():
            if isinstance(v, list):
                return v
        return []
    if isinstance(data, list):
        return data
    return []


class MemoryRepo(Repo):
    def __init__(self) -> None:
        self._stations: list[dict] = _load_seed("stations.json")
        self._trains: list[dict] = _load_seed("trains.json")
        self._stops: list[dict] = _load_seed("train_stops.json")
        self._journeys: dict[str, dict] = {}
        self._announcements: dict[str, dict] = {}
        self._audit: list[dict] = []
        self._official_updates: list[dict] = _load_seed("official_updates.json")
        self._facilities: list[dict] = _load_seed("facilities.json")
        self._facility_reports: list[dict] = []
        self._alternatives: list[dict] = _load_seed("alternatives.json")
        self._preferences: dict[str, dict] = {}
        self._emergencies: list[dict] = []

    # --- Stations ---
    def get_stations(self, q: str | None = None) -> list[dict]:
        if not q:
            return self._stations
        q_lc = q.lower()
        return [
            s for s in self._stations
            if q_lc in s.get("name", "").lower()
            or q_lc in s.get("code", "").lower()
            or any(q_lc in str(a).lower() for a in s.get("aliases", []))
        ]

    def get_station(self, code: str) -> dict | None:
        return next((s for s in self._stations if s.get("code") == code), None)

    # --- Trains ---
    def get_trains(self, q: str | None = None) -> list[dict]:
        if not q:
            return self._trains
        q_lc = q.lower()
        return [
            t for t in self._trains
            if q_lc in t.get("name", "").lower()
            or q_lc in t.get("number", "").lower()
            or any(q_lc in str(a).lower() for a in t.get("aliases", []))
        ]

    def get_train(self, number: str) -> dict | None:
        return next((t for t in self._trains if t.get("number") == number), None)

    def get_stops(self, train_number: str | None = None) -> list[dict]:
        if train_number is None:
            return self._stops
        return [s for s in self._stops if s.get("train_number") == train_number]

    # --- Journeys ---
    def create_journey(self, data: dict) -> dict:
        journey = {**data, "id": _new_id(), "created_at": _now_iso(), "status": "active"}
        self._journeys[journey["id"]] = journey
        return journey

    def get_journey(self, journey_id: str) -> dict | None:
        return self._journeys.get(journey_id)

    def get_active_journey(self, device_id: str) -> dict | None:
        for j in reversed(list(self._journeys.values())):
            if j.get("device_id") == device_id and j.get("status") == "active":
                return j
        return None

    def deactivate_journeys(self, device_id: str) -> None:
        for j in self._journeys.values():
            if j.get("device_id") == device_id:
                j["status"] = "inactive"

    # --- Announcements ---
    def create_announcement(self, data: dict) -> dict:
        ann = {**data, "id": data.get("id") or _new_id(), "created_at": _now_iso()}
        self._announcements[ann["id"]] = ann
        return ann

    def get_announcement(self, ann_id: str) -> dict | None:
        return self._announcements.get(ann_id)

    def list_announcements(self, device_id: str, limit: int = 20) -> list[dict]:
        anns = [a for a in self._announcements.values() if a.get("device_id") == device_id]
        anns.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        return anns[:limit]

    def acknowledge_announcement(self, ann_id: str) -> dict | None:
        ann = self._announcements.get(ann_id)
        if ann:
            ann["acknowledged_at"] = _now_iso()
        return ann

    # --- Audit log ---
    def create_audit_log(self, data: dict) -> dict:
        row = {**data, "id": _new_id(), "created_at": _now_iso()}
        self._audit.append(row)
        return row

    def list_audit_log(self, limit: int = 50) -> list[dict]:
        return list(reversed(self._audit))[:limit]

    # --- Official updates ---
    def get_official_updates(self, train_number: str | None = None) -> list[dict]:
        if not train_number:
            return self._official_updates
        return [u for u in self._official_updates if u.get("train_number") == train_number]

    def create_official_update(self, data: dict) -> dict:
        row = {**data, "id": _new_id(), "effective_at": _now_iso(), "source": "simulated"}
        self._official_updates.append(row)
        return row

    # --- Facilities ---
    def get_facilities(self, station_code: str | None = None) -> list[dict]:
        if not station_code:
            return self._facilities
        return [f for f in self._facilities if f.get("station_code") == station_code]

    def create_facility_report(self, facility_id: str, data: dict) -> dict:
        report = {
            **data,
            "id": _new_id(),
            "facility_id": facility_id,
            "created_at": _now_iso(),
        }
        self._facility_reports.append(report)
        self._recompute_facility_status(facility_id)
        return report

    def _recompute_facility_status(self, facility_id: str) -> None:
        """Recompute facility status based on recent crowd-sourced reports."""
        from datetime import timedelta
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        recent = [
            r for r in self._facility_reports
            if r.get("facility_id") == facility_id
            and r.get("created_at", "") >= week_ago
        ]
        if not recent:
            return
        facility = next((f for f in self._facilities if f.get("id") == facility_id), None)
        if not facility:
            return
        # Count status votes
        counts: dict[str, int] = {}
        for r in recent:
            s = r.get("reported_status", "")
            counts[s] = counts.get(s, 0) + 1
        current = facility.get("status", "")
        for status, count in counts.items():
            if count >= 2 and status != current:
                facility["status"] = "conflicting"
                return
        # Check if outdated (no verified in 90 days)
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        lv = facility.get("last_verified_at", "")
        if lv and lv < cutoff:
            facility["status"] = "outdated"

    def update_facility_status(self, facility_id: str, status: str) -> None:
        for f in self._facilities:
            if f.get("id") == facility_id:
                f["status"] = status
                break

    # --- Alternatives ---
    def get_alternatives(self, from_code: str, to_code: str) -> list[dict]:
        return [
            a for a in self._alternatives
            if a.get("from_code") == from_code and a.get("to_code") == to_code
        ]

    # --- Preferences ---
    def get_preferences(self, device_id: str) -> dict:
        return self._preferences.get(device_id, {
            "device_id": device_id,
            "pa_monitoring": True,
            "haptic": True,
            "sleep_sentinel": False,
            "language": "en-IN",
            "vibration_patterns": {},
        })

    def upsert_preferences(self, device_id: str, data: dict) -> dict:
        existing = self.get_preferences(device_id)
        updated = {**existing, **data, "device_id": device_id}
        self._preferences[device_id] = updated
        return updated

    # --- Emergency events ---
    def create_emergency(self, data: dict) -> dict:
        row = {**data, "id": _new_id(), "created_at": _now_iso()}
        self._emergencies.append(row)
        return row


# ---------------------------------------------------------------------------
# SupabaseRepo
# ---------------------------------------------------------------------------

class SupabaseRepo(Repo):
    def __init__(self) -> None:
        from supabase import create_client  # type: ignore
        self._sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    def _exec(self, fn):
        """Execute a Supabase query and return data, or raise."""
        res = fn()
        if hasattr(res, "execute"):
            res = res.execute()
        return res.data if hasattr(res, "data") else res

    # --- Stations ---
    def get_stations(self, q: str | None = None) -> list[dict]:
        query = self._sb.table("stations").select("*")
        if q:
            query = query.ilike("name", f"%{q}%")
        return self._exec(lambda: query) or []

    def get_station(self, code: str) -> dict | None:
        rows = self._exec(lambda: self._sb.table("stations").select("*").eq("code", code).limit(1))
        return rows[0] if rows else None

    # --- Trains ---
    def get_trains(self, q: str | None = None) -> list[dict]:
        query = self._sb.table("trains").select("*")
        if q:
            query = query.ilike("name", f"%{q}%")
        return self._exec(lambda: query) or []

    def get_train(self, number: str) -> dict | None:
        rows = self._exec(lambda: self._sb.table("trains").select("*").eq("number", number).limit(1))
        return rows[0] if rows else None

    def get_stops(self, train_number: str | None = None) -> list[dict]:
        query = self._sb.table("train_stops").select("*")
        if train_number:
            query = query.eq("train_number", train_number)
        return self._exec(lambda: query) or []

    # --- Journeys ---
    def create_journey(self, data: dict) -> dict:
        rows = self._exec(lambda: self._sb.table("journeys").insert(data))
        return rows[0] if rows else data

    def get_journey(self, journey_id: str) -> dict | None:
        rows = self._exec(lambda: self._sb.table("journeys").select("*").eq("id", journey_id).limit(1))
        return rows[0] if rows else None

    def get_active_journey(self, device_id: str) -> dict | None:
        rows = self._exec(
            lambda: self._sb.table("journeys")
            .select("*")
            .eq("device_id", device_id)
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
        )
        return rows[0] if rows else None

    def deactivate_journeys(self, device_id: str) -> None:
        self._exec(
            lambda: self._sb.table("journeys")
            .update({"status": "inactive"})
            .eq("device_id", device_id)
        )

    # --- Announcements ---
    def create_announcement(self, data: dict) -> dict:
        rows = self._exec(lambda: self._sb.table("announcements").insert(data))
        return rows[0] if rows else data

    def get_announcement(self, ann_id: str) -> dict | None:
        rows = self._exec(lambda: self._sb.table("announcements").select("*").eq("id", ann_id).limit(1))
        return rows[0] if rows else None

    def list_announcements(self, device_id: str, limit: int = 20) -> list[dict]:
        return self._exec(
            lambda: self._sb.table("announcements")
            .select("*")
            .eq("device_id", device_id)
            .order("created_at", desc=True)
            .limit(limit)
        ) or []

    def acknowledge_announcement(self, ann_id: str) -> dict | None:
        rows = self._exec(
            lambda: self._sb.table("announcements")
            .update({"acknowledged_at": _now_iso()})
            .eq("id", ann_id)
        )
        return rows[0] if rows else None

    # --- Audit log ---
    def create_audit_log(self, data: dict) -> dict:
        rows = self._exec(lambda: self._sb.table("audit_log").insert(data))
        return rows[0] if rows else data

    def list_audit_log(self, limit: int = 50) -> list[dict]:
        return self._exec(
            lambda: self._sb.table("audit_log")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        ) or []

    # --- Official updates ---
    def get_official_updates(self, train_number: str | None = None) -> list[dict]:
        query = self._sb.table("official_updates").select("*")
        if train_number:
            query = query.eq("train_number", train_number)
        return self._exec(lambda: query) or []

    def create_official_update(self, data: dict) -> dict:
        rows = self._exec(lambda: self._sb.table("official_updates").insert(data))
        return rows[0] if rows else data

    # --- Facilities ---
    def get_facilities(self, station_code: str | None = None) -> list[dict]:
        query = self._sb.table("facilities").select("*")
        if station_code:
            query = query.eq("station_code", station_code)
        return self._exec(lambda: query) or []

    def create_facility_report(self, facility_id: str, data: dict) -> dict:
        row = {**data, "facility_id": facility_id}
        rows = self._exec(lambda: self._sb.table("facility_reports").insert(row))
        return rows[0] if rows else row

    def update_facility_status(self, facility_id: str, status: str) -> None:
        self._exec(
            lambda: self._sb.table("facilities")
            .update({"status": status})
            .eq("id", facility_id)
        )

    # --- Alternatives ---
    def get_alternatives(self, from_code: str, to_code: str) -> list[dict]:
        return self._exec(
            lambda: self._sb.table("alternatives")
            .select("*")
            .eq("from_code", from_code)
            .eq("to_code", to_code)
        ) or []

    # --- Preferences ---
    def get_preferences(self, device_id: str) -> dict:
        rows = self._exec(
            lambda: self._sb.table("user_preferences")
            .select("*")
            .eq("device_id", device_id)
            .limit(1)
        )
        if rows:
            return rows[0]
        return {
            "device_id": device_id,
            "pa_monitoring": True,
            "haptic": True,
            "sleep_sentinel": False,
            "language": "en-IN",
            "vibration_patterns": {},
        }

    def upsert_preferences(self, device_id: str, data: dict) -> dict:
        row = {**data, "device_id": device_id}
        rows = self._exec(
            lambda: self._sb.table("user_preferences")
            .upsert(row, on_conflict="device_id")
        )
        return rows[0] if rows else row

    # --- Emergency events ---
    def create_emergency(self, data: dict) -> dict:
        rows = self._exec(lambda: self._sb.table("emergency_events").insert(data))
        return rows[0] if rows else data


# ---------------------------------------------------------------------------
# Global repo singleton
# ---------------------------------------------------------------------------

_repo: Repo | None = None
_store_degraded = False


def get_repo() -> Repo:
    global _repo, _store_degraded
    if _repo is not None:
        return _repo

    if SUPABASE_ENABLED:
        try:
            _repo = SupabaseRepo()
            _store_degraded = False
            logger.info("Using SupabaseRepo")
            return _repo
        except Exception as exc:
            logger.warning("Supabase init failed (%s), falling back to MemoryRepo", exc)
            _store_degraded = True

    _repo = MemoryRepo()
    logger.info("Using MemoryRepo")
    return _repo


def is_store_degraded() -> bool:
    return _store_degraded
