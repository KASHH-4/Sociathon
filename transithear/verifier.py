"""
Verifier: cross-checks announcement claims against schedule and official updates.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Verification:
    status: str                 # confirmed / conflict / unconfirmed
    official_row: dict[str, Any] | None
    schedule_ok: bool
    notes: list[str] = field(default_factory=list)


def verify(
    extraction: Any,
    resolution: Any,
    all_stops: list[dict[str, Any]],
    official_updates: list[dict[str, Any]],
) -> Verification:
    """
    Cross-check extraction claims against:
    1. official_updates (platform/delay/cancellation confirmations)
    2. train schedule (is the station a real stop? is the time plausible?)
    """
    matched_train = resolution.matched_train if resolution else None
    notes: list[str] = []

    if not matched_train:
        return Verification(
            status="unconfirmed",
            official_row=None,
            schedule_ok=False,
            notes=["No matched train to verify against"],
        )

    # -----------------------------------------------------------------------
    # 1. Official updates check
    # -----------------------------------------------------------------------
    relevant_updates = [
        u for u in official_updates
        if u.get("train_number") == matched_train
    ]

    # Further filter by station if mentioned
    if extraction.station_mentioned and relevant_updates:
        stn_lc = str(extraction.station_mentioned).lower()
        station_updates = [
            u for u in relevant_updates
            if stn_lc in str(u.get("station_code", "")).lower()
        ]
        if station_updates:
            relevant_updates = station_updates

    official_row: dict[str, Any] | None = None
    official_status = "unconfirmed"

    if relevant_updates:
        # Take the most recent
        def _ts(u: dict[str, Any]) -> str:
            return str(u.get("effective_at", ""))
        official_row = max(relevant_updates, key=_ts)

        kind = official_row.get("kind", "")
        ann_type = extraction.type

        # Platform check
        if ann_type == "platform_change" and extraction.platform is not None:
            official_platform = official_row.get("new_platform")
            if official_platform is not None:
                if int(official_platform) == int(extraction.platform):
                    official_status = "confirmed"
                    notes.append(
                        f"Official feed confirms platform {extraction.platform}"
                    )
                else:
                    official_status = "conflict"
                    notes.append(
                        f"Conflict: announcement says platform {extraction.platform}, "
                        f"official says {official_platform}"
                    )
            else:
                # Kind matches at least
                if kind == "platform_change":
                    official_status = "confirmed"
                    notes.append("Official feed confirms platform change (platform number TBC)")
        elif ann_type in ("delay", "cancellation"):
            if kind == ann_type or (kind == "delay" and ann_type == "delay"):
                official_status = "confirmed"
                notes.append(f"Official feed confirms {ann_type}")
            elif kind:
                official_status = "conflict"
                notes.append(f"Official update kind {kind!r} differs from announcement type {ann_type!r}")
        else:
            # Any official update is loosely corroborating
            official_status = "confirmed"
            notes.append("Official update exists for this train")
    else:
        notes.append("No official update — unconfirmed (normal in simulated feed)")

    # -----------------------------------------------------------------------
    # 2. Schedule check
    # -----------------------------------------------------------------------
    train_stops = [s for s in all_stops if s.get("train_number") == matched_train]
    schedule_ok = False

    if extraction.station_mentioned and train_stops:
        stn_lc = str(extraction.station_mentioned).lower()
        matching_stop = next(
            (s for s in train_stops
             if stn_lc in str(s.get("station_code", "")).lower()),
            None,
        )
        if matching_stop:
            schedule_ok = True
            notes.append(f"Station is a scheduled stop for {matched_train}")
            # Time plausibility: within ±3 hours of now (if we have a scheduled time)
            arr_str = matching_stop.get("arr") or matching_stop.get("dep")
            if arr_str:
                try:
                    now = datetime.now(timezone.utc)
                    hh, mm = [int(x) for x in str(arr_str).split(":")[:2]]
                    sched_mins = hh * 60 + mm
                    now_mins = now.hour * 60 + now.minute
                    diff = abs(sched_mins - now_mins)
                    # Handle midnight wrap-around
                    diff = min(diff, 1440 - diff)
                    if diff > 180:
                        notes.append(
                            f"Scheduled time {arr_str} is >3 h from now — "
                            f"possibly off-corridor announcement"
                        )
                except Exception:
                    pass
        else:
            notes.append(
                f"Mentioned station not found in {matched_train}'s schedule"
            )
    elif not extraction.station_mentioned:
        # Can't check without a station
        schedule_ok = True  # benefit of the doubt
        notes.append("No station mentioned; schedule check skipped")
    else:
        notes.append("No schedule data for this train")

    return Verification(
        status=official_status,
        official_row=official_row,
        schedule_ok=schedule_ok,
        notes=notes,
    )
