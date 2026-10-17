"""
Deterministic train resolver — no LLM, no embeddings.
Picks the user's train from a candidate set using fuzzy digit matching
and corroboration signals.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .normalize import match_alias

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Levenshtein distance (character-level, on digit strings)
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Compute edit distance between two strings."""
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            temp = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = temp
    return dp[lb]


@dataclass
class Resolution:
    method: str           # exact / fuzzy_corroborated / fuzzy_uncorroborated /
                          # ambiguous / other_train / unknown_number / name_only /
                          # no_journey / no_number
    heard: str | None     # the raw number heard (never corrected)
    matched_train: str | None
    candidates_considered: list[str]
    distance: int | None
    corroboration: bool
    score: float
    notes: list[str] = field(default_factory=list)
    platform_invalid: bool = False


def _build_candidate_set(
    journey: dict[str, Any] | None,
    all_trains: list[dict[str, Any]],
    all_stops: list[dict[str, Any]],
) -> list[str]:
    """
    Return the list of train numbers that are relevant to this journey.
    booking mode → [booked train number]
    route mode → every train that passes through origin *before* destination
    no journey → []
    """
    if not journey:
        return []

    mode = journey.get("mode", "route")
    if mode == "booking":
        num = journey.get("train_number")
        return [num] if num else []

    # Route mode: find trains that stop at origin before destination
    origin = journey.get("origin_code", "")
    dest = journey.get("dest_code", "")

    # Group stops by train
    by_train: dict[str, list[dict[str, Any]]] = {}
    for stop in all_stops:
        tn = stop.get("train_number", "")
        by_train.setdefault(tn, []).append(stop)

    candidates = []
    for tn, stops in by_train.items():
        stops_sorted = sorted(stops, key=lambda s: s.get("seq", 0))
        codes = [s.get("station_code", "") for s in stops_sorted]
        if origin in codes and dest in codes:
            o_idx = codes.index(origin)
            d_idx = codes.index(dest)
            if o_idx < d_idx:
                candidates.append(tn)
    return candidates


def _corroborates(
    heard_number: str,
    candidate: dict[str, Any],
    extraction: Any,
    all_stops: list[dict[str, Any]],
) -> bool:
    """
    Corroboration: name/alias match OR mentioned station on the candidate's route.
    """
    # Name match
    if extraction.train_name_heard:
        name_lc = str(extraction.train_name_heard).lower()
        cand_name = str(candidate.get("name", "")).lower()
        aliases = [str(a).lower() for a in candidate.get("aliases", [])]
        if name_lc in cand_name or cand_name in name_lc:
            return True
        if any(name_lc in a or a in name_lc for a in aliases):
            return True

    # Station on route
    if extraction.station_mentioned:
        route_codes = {
            s.get("station_code", "")
            for s in all_stops
            if s.get("train_number") == candidate.get("number")
        }
        stn_lc = str(extraction.station_mentioned).lower()
        if any(stn_lc in code.lower() or stn_lc in "".join(route_codes).lower()
               for code in route_codes):
            return True
    return False


def resolve(
    extraction: Any,                    # Extraction dataclass
    journey: dict[str, Any] | None,
    all_trains: list[dict[str, Any]],
    all_stops: list[dict[str, Any]],
    all_stations: list[dict[str, Any]],
) -> Resolution:
    """
    Resolve the announcement to a specific train number.
    Returns a Resolution dataclass.
    """
    candidates = _build_candidate_set(journey, all_trains, all_stops)

    if not journey:
        return Resolution(
            method="no_journey",
            heard=None,
            matched_train=None,
            candidates_considered=[],
            distance=None,
            corroboration=False,
            score=0.0,
            notes=["No active journey; announcement shown as informational only"],
        )

    # Build lookup maps
    train_by_number: dict[str, dict[str, Any]] = {
        t["number"]: t for t in all_trains if "number" in t
    }
    station_by_code: dict[str, dict[str, Any]] = {
        s["code"]: s for s in all_stations if "code" in s
    }

    # Resolve via heard numbers
    heard_numbers = [
        n for n in extraction.train_numbers_heard
        if len(n) == 5  # only valid 5-digit numbers
    ]

    best_resolution: Resolution | None = None

    for heard in heard_numbers:
        # 1. Exact match in candidates
        if heard in candidates:
            res = Resolution(
                method="exact",
                heard=heard,
                matched_train=heard,
                candidates_considered=candidates,
                distance=0,
                corroboration=True,
                score=1.0,
            )
            # Apply sanity checks
            res = _apply_sanity_checks(res, extraction, candidates, all_stops, station_by_code, all_stations)
            return res  # exact match — return immediately

        # 2. Levenshtein to candidates
        distances: list[tuple[int, str]] = [
            (_levenshtein(heard, c), c) for c in candidates
        ]
        if distances:
            distances.sort()
            best_dist, best_cand = distances[0]
            tied = [c for d, c in distances if d == best_dist]

            if best_dist == 1:
                if len(tied) >= 2:
                    res = Resolution(
                        method="ambiguous",
                        heard=heard,
                        matched_train=None,
                        candidates_considered=candidates,
                        distance=best_dist,
                        corroboration=False,
                        score=0.30,
                        notes=[f"Multiple candidates at distance 1: {tied}"],
                    )
                    if best_resolution is None or res.score > best_resolution.score:
                        best_resolution = res
                else:
                    cand_obj = train_by_number.get(best_cand, {"number": best_cand})
                    corr = _corroborates(heard, cand_obj, extraction, all_stops)
                    if corr:
                        method = "fuzzy_corroborated"
                        score = 0.70
                    else:
                        method = "fuzzy_uncorroborated"
                        score = 0.45
                    res = Resolution(
                        method=method,
                        heard=heard,
                        matched_train=best_cand,
                        candidates_considered=candidates,
                        distance=best_dist,
                        corroboration=corr,
                        score=score,
                        notes=[f"Heard {heard}, closest candidate is {best_cand}"],
                    )
                    if best_resolution is None or res.score > best_resolution.score:
                        best_resolution = res
            else:
                # Distance > 1: check if it's a known real train NOT on user's route
                if heard in train_by_number:
                    res = Resolution(
                        method="other_train",
                        heard=heard,
                        matched_train=heard,
                        candidates_considered=candidates,
                        distance=best_dist,
                        corroboration=False,
                        score=0.0,
                        notes=[f"Train {heard} is real but not on this user's route"],
                    )
                else:
                    res = Resolution(
                        method="unknown_number",
                        heard=heard,
                        matched_train=None,
                        candidates_considered=candidates,
                        distance=best_dist,
                        corroboration=False,
                        score=0.20,
                        notes=[f"Train {heard} not found in any known train"],
                    )
                if best_resolution is None or res.score > best_resolution.score:
                    best_resolution = res
        else:
            # No candidates at all: treat heard number as unknown
            if heard in train_by_number:
                res = Resolution(
                    method="other_train",
                    heard=heard,
                    matched_train=heard,
                    candidates_considered=[],
                    distance=None,
                    corroboration=False,
                    score=0.0,
                    notes=["Real train, but no journey candidates to match against"],
                )
            else:
                res = Resolution(
                    method="unknown_number",
                    heard=heard,
                    matched_train=None,
                    candidates_considered=[],
                    distance=None,
                    corroboration=False,
                    score=0.20,
                )
            if best_resolution is None or res.score > best_resolution.score:
                best_resolution = res

    if best_resolution is not None:
        best_resolution = _apply_sanity_checks(
            best_resolution, extraction, candidates, all_stops, station_by_code, all_stations
        )
        return best_resolution

    # No numbers heard — try name-only match
    if extraction.train_name_heard and candidates:
        candidate_objects = [train_by_number[c] for c in candidates if c in train_by_number]
        matched = match_alias(extraction.train_name_heard, candidate_objects)
        if matched:
            res = Resolution(
                method="name_only",
                heard=None,
                matched_train=matched.get("number"),
                candidates_considered=candidates,
                distance=None,
                corroboration=True,
                score=0.60,
            )
            res = _apply_sanity_checks(res, extraction, candidates, all_stops, station_by_code, all_stations)
            return res

    return Resolution(
        method="no_number",
        heard=None,
        matched_train=None,
        candidates_considered=candidates,
        distance=None,
        corroboration=False,
        score=0.10,
        notes=["No train number or name heard"],
    )


def _apply_sanity_checks(
    res: Resolution,
    extraction: Any,
    candidates: list[str],
    all_stops: list[dict[str, Any]],
    station_by_code: dict[str, dict[str, Any]],
    all_stations: list[dict[str, Any]],
) -> Resolution:
    """
    Apply post-resolution sanity checks:
    - Platform must be within the station's platform_count.
    - Mentioned station must be on the matched train's route.
    """
    matched = res.matched_train

    # Platform check
    if extraction.platform is not None and extraction.station_mentioned:
        # Find station
        stn = None
        for s in all_stations:
            aliases_lc = [str(a).lower() for a in s.get("aliases", [])]
            name_lc = s.get("name", "").lower()
            stn_mention_lc = str(extraction.station_mentioned).lower()
            if stn_mention_lc in name_lc or stn_mention_lc in aliases_lc or s.get("code", "").lower() == stn_mention_lc:
                stn = s
                break
        if stn:
            platform_count = stn.get("platform_count", 10)
            if extraction.platform > platform_count or extraction.platform < 1:
                res.platform_invalid = True
                res.notes.append(
                    f"Platform {extraction.platform} exceeds station max {platform_count}"
                )

    # Mentioned station on route
    if matched and extraction.station_mentioned:
        route_codes = {
            s.get("station_code", "")
            for s in all_stops
            if s.get("train_number") == matched
        }
        stn_mention_lc = str(extraction.station_mentioned).lower()
        station_on_route = any(
            stn_mention_lc in code.lower()
            for code in route_codes
        ) or any(
            stn_mention_lc in s.get("name", "").lower()
            for s in all_stations
            if s.get("code") in route_codes
        )
        if route_codes and not station_on_route:
            res.score = max(0, res.score - 0.25)
            res.notes.append(
                f"Mentioned station '{extraction.station_mentioned}' not on train {matched}'s route"
            )

    return res
