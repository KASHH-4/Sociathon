"""
Reliability gate: confidence fusion, safety rules, dedupe, decision, audit log.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from .config import THRESH_ALERT, THRESH_VERIFY, DEDUPE_SECONDS

logger = logging.getLogger(__name__)

# In-memory dedupe window: maps (device_id, train, type, platform_or_delay) → timestamp
_dedupe_cache: dict[str, float] = {}

# Haptic patterns (ms arrays)
_HAPTIC_PATTERNS = {
    "alert_critical": [400, 150, 400, 150, 800],
    "verify_with_staff": [250, 120, 250],
    "alert_info": [150],
    "safety": [800, 200, 800, 200, 800],
    "ignore": [],
}

VERIFICATION_SCORES = {
    "confirmed": 1.0,
    "unconfirmed": 0.5,
    "conflict": 0.0,
}

CRITICAL_TYPES = {"platform_change", "cancellation", "safety"}


def _dedupe_key(
    device_id: str,
    train: str | None,
    ann_type: str,
    platform: int | None,
    delay_minutes: int | None,
) -> str:
    raw = f"{device_id}:{train}:{ann_type}:{platform}:{delay_minutes}"
    return hashlib.md5(raw.encode()).hexdigest()


def fuse_and_decide(
    device_id: str,
    stt_confidence: float,
    extraction: Any,
    resolution: Any,
    verification: Any,
    user_prefs: dict[str, Any] | None,
    repo: Any,                          # Repo instance for writing audit log
) -> dict[str, Any]:
    """
    Fuse stage confidences, apply safety rules, dedupe, decide.
    Returns the full result dict (including haptic_pattern, rules_fired, stage_scores).
    """
    rules_fired: list[str] = []

    # -----------------------------------------------------------------------
    # Stage scores
    # -----------------------------------------------------------------------
    stt_score = max(0.0, min(1.0, float(stt_confidence or 0.7)))
    ext_score = max(0.0, min(1.0, float(extraction.confidence)))
    res_score = max(0.0, min(1.0, float(resolution.score)))
    ver_score = VERIFICATION_SCORES.get(verification.status, 0.5)

    stage_scores = {
        "stt": round(stt_score, 3),
        "extraction": round(ext_score, 3),
        "resolution": round(res_score, 3),
        "verification": round(ver_score, 3),
    }

    # Weights — renormalize if a stage is missing (score=0 means the stage didn't run
    # meaningfully; we still include it but at 0 weight if resolution is no_journey)
    weights = {"stt": 0.25, "extraction": 0.25, "resolution": 0.30, "verification": 0.20}

    # If no journey, resolution stage is essentially random — reduce its weight
    if resolution.method in ("no_journey", "no_number"):
        weights["resolution"] = 0.10
    total_w = sum(weights.values())
    final = sum(stage_scores[k] * weights[k] for k in weights) / total_w
    final = round(final, 3)

    ann_type = extraction.type
    matched_train = resolution.matched_train
    heard = resolution.heard

    # -----------------------------------------------------------------------
    # Determine if this is a critical type
    # -----------------------------------------------------------------------
    is_critical = (
        ann_type in CRITICAL_TYPES
        or (ann_type == "delay" and (extraction.delay_minutes or 0) >= 15)
    )

    # -----------------------------------------------------------------------
    # R5: Safety asymmetry — always shown regardless of confidence
    # -----------------------------------------------------------------------
    if ann_type == "safety":
        rules_fired.append("R5")
        decision = "alert_critical"
        reason = "Safety announcements always shown (unverified)"
        return _build_result(
            decision, reason, final, extraction, resolution, verification,
            rules_fired, stage_scores, user_prefs, "unverified"
        )

    # -----------------------------------------------------------------------
    # other_train or no_journey → ignore/informational
    # -----------------------------------------------------------------------
    if resolution.method == "other_train":
        decision = "ignore"
        reason = f"Train {heard} is not on your journey"
        return _build_result(
            decision, reason, final, extraction, resolution, verification,
            rules_fired, stage_scores, user_prefs
        )

    if resolution.method == "no_journey":
        # Show as informational if above verify threshold
        if final >= THRESH_VERIFY:
            decision = "alert_info"
            reason = "No active journey — shown for information only"
        else:
            decision = "ignore"
            reason = "No active journey and confidence too low"
        return _build_result(
            decision, reason, final, extraction, resolution, verification,
            rules_fired, stage_scores, user_prefs
        )

    # -----------------------------------------------------------------------
    # R6: Dedupe
    # -----------------------------------------------------------------------
    dk = _dedupe_key(device_id, matched_train, ann_type,
                     extraction.platform, extraction.delay_minutes)
    now = time.time()
    if dk in _dedupe_cache and (now - _dedupe_cache[dk]) < DEDUPE_SECONDS:
        rules_fired.append("R6")
        result = _build_result(
            "ignore", "Duplicate announcement (dedupe window)",
            final, extraction, resolution, verification,
            rules_fired, stage_scores, user_prefs
        )
        result["deduped"] = True
        return result
    _dedupe_cache[dk] = now

    # -----------------------------------------------------------------------
    # R2: Platform out of bounds
    # -----------------------------------------------------------------------
    if resolution.platform_invalid:
        rules_fired.append("R2")
        decision = "verify_with_staff"
        reason = "Platform number invalid for this station — please confirm with staff"
        return _build_result(
            decision, reason, final, extraction, resolution, verification,
            rules_fired, stage_scores, user_prefs
        )

    # -----------------------------------------------------------------------
    # R3: Station not on route — downgrade
    # -----------------------------------------------------------------------
    for note in (resolution.notes or []):
        if "not on train" in note or "not found in" in note:
            rules_fired.append("R3")
            final = max(0, final - 0.10)
            break

    # -----------------------------------------------------------------------
    # R4: Official feed conflict
    # -----------------------------------------------------------------------
    if verification.status == "conflict":
        rules_fired.append("R4")
        decision = "verify_with_staff"
        official_val = (
            verification.official_row.get("new_platform") if verification.official_row else None
        )
        reason = (
            f"Official feed conflicts with announcement"
            + (f" (official: platform {official_val})" if official_val else "")
        )
        return _build_result(
            decision, reason, final, extraction, resolution, verification,
            rules_fired, stage_scores, user_prefs, "conflict"
        )

    # -----------------------------------------------------------------------
    # Main decision
    # -----------------------------------------------------------------------
    if is_critical:
        if final >= THRESH_ALERT:
            decision = "alert_critical"
            reason = f"High confidence {ann_type} alert"
        elif final >= THRESH_VERIFY:
            decision = "verify_with_staff"
            reason = f"Moderate confidence {ann_type} — please confirm with staff"
        else:
            decision = "ignore"
            reason = f"Confidence too low for {ann_type} alert"
    else:
        if final >= THRESH_VERIFY:
            decision = "alert_info"
            reason = f"{ann_type} information"
        else:
            decision = "ignore"
            reason = f"Confidence too low for {ann_type} info"

    trust_label = _trust_label(verification.status, final)

    return _build_result(
        decision, reason, final, extraction, resolution, verification,
        rules_fired, stage_scores, user_prefs, trust_label
    )


def _trust_label(verification_status: str, confidence: float) -> str:
    if verification_status == "confirmed":
        return "Confirmed by official feed (simulated)"
    elif verification_status == "conflict":
        return "Conflict with official feed"
    elif confidence >= THRESH_ALERT:
        return "High confidence, not yet verified"
    elif confidence >= THRESH_VERIFY:
        return "Moderate confidence, not yet verified"
    else:
        return "Low confidence — treat with caution"


def _get_haptic(decision: str, ann_type: str, user_prefs: dict[str, Any] | None) -> list[int]:
    """Return haptic pattern from prefs override or defaults."""
    if user_prefs and not user_prefs.get("haptic", True):
        return []

    if user_prefs:
        patterns = user_prefs.get("vibration_patterns") or {}
        if decision in patterns:
            return patterns[decision]

    if ann_type == "safety":
        return _HAPTIC_PATTERNS["safety"]
    return _HAPTIC_PATTERNS.get(decision, [])


def _build_result(
    decision: str,
    reason: str,
    confidence: float,
    extraction: Any,
    resolution: Any,
    verification: Any,
    rules_fired: list[str],
    stage_scores: dict[str, float],
    user_prefs: dict[str, Any] | None,
    trust_label: str | None = None,
) -> dict[str, Any]:
    if trust_label is None:
        trust_label = _trust_label(
            verification.status if verification else "unconfirmed", confidence
        )

    heard = resolution.heard
    matched = resolution.matched_train
    method = resolution.method

    # R1: never present corrected number as heard
    show_correction = (
        heard is not None
        and matched is not None
        and heard != matched
        and method not in ("exact",)
    )

    train_info: dict[str, Any] = {
        "heard": heard,
        "matched": matched,
        "method": method,
    }
    if show_correction:
        train_info["correction_note"] = (
            f"Heard {heard}, matched to your train {matched}. Please confirm."
        )

    haptic = _get_haptic(decision, extraction.type, user_prefs)

    return {
        "decision": decision,
        "reason": reason,
        "confidence": confidence,
        "display_text": extraction.display_text,
        "type": extraction.type,
        "train": train_info,
        "platform": extraction.platform if not resolution.platform_invalid else None,
        "delay_minutes": extraction.delay_minutes,
        "recommended_action": extraction.recommended_action,
        "trust": {
            "status": verification.status if verification else "unconfirmed",
            "label": trust_label,
        },
        "haptic_pattern": haptic,
        "deduped": False,
        "extractor": extraction.extractor,
        "degraded": getattr(extraction, "degraded", False),
        "simulated": False,   # set by pipeline
        "rules_fired": rules_fired,
        "stage_scores": stage_scores,
    }
