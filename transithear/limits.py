"""
Input size limits and per-device rate limiter (token bucket).
"""
from __future__ import annotations

import threading
import time

from .config import MAX_TRANSCRIPT_CHARS, RATE_LIMIT_PER_MIN

_lock = threading.Lock()
_buckets: dict[str, dict] = {}   # device_id → {tokens, last_refill}


def check_transcript(text: str) -> tuple[bool, str]:
    """Return (ok, error_message). ok is True if transcript is acceptable."""
    if not text or not text.strip():
        return False, "Transcript is empty"
    if len(text) > MAX_TRANSCRIPT_CHARS:
        return False, f"Transcript exceeds maximum {MAX_TRANSCRIPT_CHARS} characters"
    return True, ""


def check_rate_limit(device_id: str) -> tuple[bool, str]:
    """Return (ok, error_message). ok is True if under rate limit."""
    now = time.time()
    with _lock:
        if device_id not in _buckets:
            _buckets[device_id] = {"tokens": RATE_LIMIT_PER_MIN, "last_refill": now}
        bucket = _buckets[device_id]
        elapsed = now - bucket["last_refill"]
        refill = elapsed * (RATE_LIMIT_PER_MIN / 60.0)
        bucket["tokens"] = min(RATE_LIMIT_PER_MIN, bucket["tokens"] + refill)
        bucket["last_refill"] = now
        if bucket["tokens"] < 1:
            return False, f"Rate limit exceeded: {RATE_LIMIT_PER_MIN} requests/min"
        bucket["tokens"] -= 1
    return True, ""
