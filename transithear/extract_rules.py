"""
Rule-based announcement gate and field extractor.
Fast, deterministic; used as a cheap pre-filter and as the fallback
when Gemini is unavailable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .normalize import normalize, find_train_numbers

# ---------------------------------------------------------------------------
# Transit vocabulary for the announcement gate
# ---------------------------------------------------------------------------
_TRANSIT_VOCAB_RE = re.compile(
    r"\b("
    r"platform|train|arriv|depart|delay|late|cancel|running|express|"
    r"intercity|shatabdi|deccan|pragati|sinhagad|rajdhani|duronto|"
    r"mind\s+the\s+gap|mind\s+gap|"
    r"rail|station|coach|berth|track|signal|"
    # Hindi/Marathi Roman
    r"gaadi|gadi|rail|plataform|vialamb|vilayamb|vilank|vilambh|"
    r"platform|gaadi|chhutegi|aayegi|rukegi|"
    # Devanagari
    r"प्लेटफॉर्म|गाड़ी|गाडी|विलंब|रद्द|आगमन|प्रस्थान|ट्रेन"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

_EXTRACTABLE_RE = re.compile(
    r"\b\d{4,6}\b"                          # train number
    r"|platform\s*\d{1,2}"                  # platform
    r"|delayed?\s+by\s+\d+"                 # delay
    r"|\d+\s*min"                            # delay minutes
    r"|cancel"                               # cancellation
    r"|विलंब|रद्द|प्लेटफॉर्म",              # Devanagari
    re.IGNORECASE | re.UNICODE,
)

# ---------------------------------------------------------------------------
# Announcement type patterns
# ---------------------------------------------------------------------------
_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cancellation",    re.compile(r"\bcancel(led|lation|s)?\b|\brद्द\b", re.I | re.U)),
    ("platform_change", re.compile(
        r"\b(platform\s+(change|number|shift|moved|now|is|has\s+changed)|"
        r"shifted\s+to\s+platform|now\s+arriving\s+at\s+platform|"
        r"arrive\s+at\s+platform|instead\s+of\s+platform|"
        r"instead\s+platform|platform\s+\d+\s+instead|"
        r"प्लेटफॉर्म\s+(बदल|नंबर))\b", re.I | re.U)),
    ("safety",          re.compile(
        r"\b(mind\s+the\s+gap|emergency|evacuate|fire|bomb|alert|danger)\b",
        re.I | re.U)),
    ("early_arrival",   re.compile(
        r"\b(early|ahead\s+of\s+schedule|early\s+arrival)\b", re.I | re.U)),
    ("delay",           re.compile(
        r"\b(delay|late|running\s+late|विलंब|minutes?\s+late)\b", re.I | re.U)),
    ("arrival",         re.compile(
        r"\b(arriv|arriving|आगमन)\b", re.I | re.U)),
    ("departure",       re.compile(
        r"\b(depart|departing|departs|प्रस्थान)\b", re.I | re.U)),
]

_PLATFORM_RE = re.compile(r"\bplatform\s*(?:number\s*)?(\d{1,2})\b", re.I)
_DELAY_RE = re.compile(r"\bdelay(?:ed)?\s+by\s+(\d+)\s*min|\b(\d+)\s*min(?:utes?)?\s+(?:delay|late)\b", re.I)
_TRAIN_NUM_RE = re.compile(r"\b(\d{5})\b")


@dataclass
class Extraction:
    is_announcement: bool
    language: str
    type: str                           # announcement type
    train_numbers_heard: list[str]
    train_name_heard: str | None
    station_mentioned: str | None
    platform: int | None
    delay_minutes: int | None
    new_time: str | None
    display_text: str
    recommended_action: str
    confidence: float
    uncertain_fields: list[str]
    extractor: str = "rules"
    degraded: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


def is_announcement(text: str) -> bool:
    """Quick gate: does this text look like a PA announcement?"""
    norm = normalize(text)
    has_vocab = bool(_TRANSIT_VOCAB_RE.search(norm))
    has_field = bool(_EXTRACTABLE_RE.search(norm))
    return has_vocab and has_field


def extract(text: str, normalized: str | None = None) -> Extraction:
    """
    Extract announcement fields using rules and regex.
    *normalized* can be passed in to avoid re-normalizing.
    """
    if normalized is None:
        normalized = normalize(text)

    ann = is_announcement(normalized)

    # Detect type
    ann_type = "other"
    for t, pattern in _TYPE_PATTERNS:
        if pattern.search(normalized):
            ann_type = t
            break

    # Extract train numbers
    train_nums = [c["number"] for c in find_train_numbers(normalized) if not c["malformed"]]

    # Platform
    platform: int | None = None
    pm = _PLATFORM_RE.search(normalized)
    if pm:
        platform = int(pm.group(1))

    # Delay minutes
    delay_mins: int | None = None
    dm = _DELAY_RE.search(normalized)
    if dm:
        val = dm.group(1) or dm.group(2)
        if val:
            delay_mins = int(val)

    # Display text (truncated to 140 chars)
    display = text[:140].strip()

    # Recommended action
    if ann_type == "platform_change":
        action = "Proceed to the new platform shown"
    elif ann_type == "cancellation":
        action = "Check alternative trains"
    elif ann_type == "delay":
        action = "Wait; check updated departure time"
    elif ann_type == "safety":
        action = "Follow safety instructions from staff"
    elif ann_type == "early_arrival":
        action = "Proceed to platform promptly"
    else:
        action = "Monitor announcements"

    # Uncertain fields
    uncertain: list[str] = []
    if not train_nums:
        uncertain.append("train_number")
    if platform is None and ann_type == "platform_change":
        uncertain.append("platform")
    if delay_mins is None and ann_type == "delay":
        uncertain.append("delay_minutes")

    # Confidence: 0.55 base, slightly higher if more fields found
    confidence = 0.55
    if train_nums:
        confidence += 0.05
    if platform is not None:
        confidence += 0.05
    if delay_mins is not None:
        confidence += 0.03

    # Language detection (simple heuristic)
    lang = "en-IN"
    if any(ord(ch) > 0x0900 for ch in text):
        lang = "hi-IN"
    elif any(kw in normalized for kw in ("gaadi", "gadi", "vilambh", "platform")):
        lang = "hi-IN"

    return Extraction(
        is_announcement=ann,
        language=lang,
        type=ann_type,
        train_numbers_heard=train_nums,
        train_name_heard=None,
        station_mentioned=None,
        platform=platform,
        delay_minutes=delay_mins,
        new_time=None,
        display_text=display,
        recommended_action=action,
        confidence=min(confidence, 0.68),  # rules cap at 0.68
        uncertain_fields=uncertain,
        extractor="rules",
    )
