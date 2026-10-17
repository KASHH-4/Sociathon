"""
Pipeline: orchestrates steps 1-7 for POST /api/announcements/ingest.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from .limits import check_transcript, check_rate_limit
from .normalize import normalize
from .extract_rules import is_announcement as rules_gate, extract as rules_extract
from .extract_gemini import extract as gemini_extract
from .resolver import resolve
from .verifier import verify
from .reliability import fuse_and_decide
from .events import push
from .db import get_repo
from .config import GEMINI_ENABLED

logger = logging.getLogger(__name__)


def process(
    device_id: str,
    transcript: str,
    stt_source: str = "browser",
    stt_confidence: float | None = None,
    language: str | None = None,
    simulated: bool = False,
) -> dict[str, Any]:
    """
    Run the full TransitHear pipeline.
    Never raises — catches all exceptions and returns a safe response.
    """
    try:
        return _process_inner(
            device_id, transcript, stt_source,
            stt_confidence, language, simulated
        )
    except Exception as exc:
        logger.exception("Pipeline error for device %s: %s", device_id, exc)
        return {
            "id": str(uuid.uuid4()),
            "decision": "verify_with_staff",
            "reason": "Internal error during processing",
            "confidence": 0.0,
            "display_text": transcript[:140],
            "type": "other",
            "train": {"heard": None, "matched": None, "method": "error"},
            "platform": None,
            "delay_minutes": None,
            "recommended_action": "Please check with station staff",
            "trust": {"status": "unconfirmed", "label": "Error during processing"},
            "haptic_pattern": [250, 120, 250],
            "deduped": False,
            "extractor": "error",
            "degraded": True,
            "simulated": simulated,
            "rules_fired": [],
            "stage_scores": {},
            "error": str(exc),
        }


def _process_inner(
    device_id: str,
    transcript: str,
    stt_source: str,
    stt_confidence: float | None,
    language: str | None,
    simulated: bool,
) -> dict[str, Any]:
    repo = get_repo()

    # ------------------------------------------------------------------
    # 1. Input limits
    # ------------------------------------------------------------------
    ok, err = check_transcript(transcript)
    if not ok:
        return _no_persist_result(err, "ignore", transcript, simulated)

    ok, err = check_rate_limit(device_id)
    if not ok:
        return _no_persist_result(err, "ignore", transcript, simulated, rate_limited=True)

    stt_conf = float(stt_confidence) if stt_confidence is not None else (
        0.7 if stt_source == "browser" else 0.5
    )

    # ------------------------------------------------------------------
    # 2. Normalize
    # ------------------------------------------------------------------
    normalized = normalize(transcript)

    # ------------------------------------------------------------------
    # 3. Rules gate (cheap reject) — R7: non-announcements not persisted
    # ------------------------------------------------------------------
    if not rules_gate(normalized):
        return _no_persist_result(
            "Not a PA announcement", "ignore", transcript, simulated
        )

    # ------------------------------------------------------------------
    # 4. Extraction (Gemini or rules fallback)
    # ------------------------------------------------------------------
    journey = repo.get_active_journey(device_id)
    all_trains = repo.get_trains()

    # Build candidate trains for Gemini context
    if journey:
        all_stops = repo.get_stops()
        from .resolver import _build_candidate_set
        candidate_numbers = _build_candidate_set(journey, all_trains, all_stops)
        candidate_trains = [t for t in all_trains if t.get("number") in candidate_numbers]
    else:
        all_stops = repo.get_stops()
        candidate_trains = all_trains[:25]

    if GEMINI_ENABLED:
        extraction = gemini_extract(transcript, normalized, candidate_trains)
    else:
        extraction = rules_extract(transcript, normalized)
        extraction.degraded = True

    # ------------------------------------------------------------------
    # 5. Resolve
    # ------------------------------------------------------------------
    all_stations = repo.get_stations()
    all_stops = repo.get_stops()
    resolution = resolve(extraction, journey, all_trains, all_stops, all_stations)

    # ------------------------------------------------------------------
    # 6. Verify
    # ------------------------------------------------------------------
    official_updates = repo.get_official_updates(resolution.matched_train)
    verification = verify(extraction, resolution, all_stops, official_updates)

    # ------------------------------------------------------------------
    # 7. Reliability gate
    # ------------------------------------------------------------------
    prefs = repo.get_preferences(device_id)
    result = fuse_and_decide(
        device_id, stt_conf, extraction, resolution, verification, prefs, repo
    )

    # ------------------------------------------------------------------
    # 8. Persist (only real announcements, not non-announcements - R7)
    # ------------------------------------------------------------------
    ann_id = str(uuid.uuid4())

    if not result.get("deduped"):
        ann_row = {
            "id": ann_id,
            "device_id": device_id,
            "journey_id": journey.get("id") if journey else None,
            "raw_transcript": None,          # R7: never store audio
            "normalized_transcript": normalized,
            "stt_source": stt_source,
            "stt_confidence": stt_conf,
            "language": language or extraction.language,
            "extracted": _extraction_to_dict(extraction),
            "resolved_train": resolution.matched_train,
            "resolution": {
                "method": resolution.method,
                "heard": resolution.heard,
                "distance": resolution.distance,
                "corroboration": resolution.corroboration,
                "score": resolution.score,
                "notes": resolution.notes,
            },
            "verification": {
                "status": verification.status,
                "schedule_ok": verification.schedule_ok,
                "notes": verification.notes,
            },
            "confidence_final": result["confidence"],
            "decision": result["decision"],
            "reason": result["reason"],
            "simulated": simulated,
        }
        stored = repo.create_announcement(ann_row)
        ann_id = stored.get("id", ann_id)

        # Audit log (R8)
        repo.create_audit_log({
            "announcement_id": ann_id,
            "stage_scores": result["stage_scores"],
            "model_versions": {
                "gemini": result.get("extractor") == "gemini",
                "model": "gemini-2.5-flash",
            },
            "rules_fired": result["rules_fired"],
            "decision": result["decision"],
        })

        # SSE broadcast
        if result["decision"] != "ignore":
            push(device_id, "announcement", {**result, "id": ann_id})
    else:
        # Deduped: find the original ID if available
        existing = repo.list_announcements(device_id, limit=5)
        if existing:
            ann_id = existing[0].get("id", ann_id)

    result["id"] = ann_id
    result["simulated"] = simulated
    return result


def _no_persist_result(
    reason: str,
    decision: str,
    transcript: str,
    simulated: bool,
    rate_limited: bool = False,
) -> dict[str, Any]:
    """Return a result without persisting anything."""
    return {
        "id": str(uuid.uuid4()),
        "decision": decision,
        "reason": reason,
        "confidence": 0.0,
        "display_text": transcript[:140],
        "type": "other",
        "train": {"heard": None, "matched": None, "method": "none"},
        "platform": None,
        "delay_minutes": None,
        "recommended_action": "No action required",
        "trust": {"status": "unconfirmed", "label": "Not processed"},
        "haptic_pattern": [],
        "deduped": False,
        "extractor": "none",
        "degraded": False,
        "simulated": simulated,
        "rules_fired": [],
        "stage_scores": {},
        "rate_limited": rate_limited,
    }


def _extraction_to_dict(extraction: Any) -> dict:
    return {
        "is_announcement": extraction.is_announcement,
        "language": extraction.language,
        "type": extraction.type,
        "train_numbers_heard": extraction.train_numbers_heard,
        "train_name_heard": extraction.train_name_heard,
        "station_mentioned": extraction.station_mentioned,
        "platform": extraction.platform,
        "delay_minutes": extraction.delay_minutes,
        "new_time": extraction.new_time,
        "display_text": extraction.display_text,
        "recommended_action": extraction.recommended_action,
        "confidence": extraction.confidence,
        "uncertain_fields": extraction.uncertain_fields,
        "extractor": extraction.extractor,
        "degraded": extraction.degraded,
    }
