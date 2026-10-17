"""Tests for resolver.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from transithear.resolver import resolve
from transithear.extract_rules import Extraction


def _extraction(train_numbers=None, train_name=None, station=None, platform=None):
    return Extraction(
        is_announcement=True,
        language="en-IN",
        type="platform_change",
        train_numbers_heard=train_numbers or [],
        train_name_heard=train_name,
        station_mentioned=station,
        platform=platform,
        delay_minutes=None,
        new_time=None,
        display_text="test",
        recommended_action="check platform",
        confidence=0.6,
        uncertain_fields=[],
        extractor="rules",
    )


# Seed data (minimal subset)
TRAINS = [
    {"number": "12123", "name": "Deccan Queen Express", "aliases": ["Deccan Queen", "DQ"], "origin_code": "CSMT", "dest_code": "PUNE"},
    {"number": "12124", "name": "Deccan Queen Express", "aliases": [], "origin_code": "PUNE", "dest_code": "CSMT"},
    {"number": "12125", "name": "Pragati Express", "aliases": [], "origin_code": "CSMT", "dest_code": "PUNE"},
    {"number": "12126", "name": "Pragati Express", "aliases": [], "origin_code": "PUNE", "dest_code": "CSMT"},
    {"number": "12127", "name": "Intercity Express", "aliases": [], "origin_code": "CSMT", "dest_code": "PUNE"},
    {"number": "12128", "name": "Intercity Express", "aliases": ["Intercity"], "origin_code": "PUNE", "dest_code": "CSMT"},
    {"number": "11009", "name": "Sinhagad Express", "aliases": [], "origin_code": "CSMT", "dest_code": "PUNE"},
    {"number": "12009", "name": "Shatabdi Express", "aliases": [], "origin_code": "MMCT", "dest_code": "ADI"},
]

STOPS = [
    {"train_number": "12127", "seq": 1, "station_code": "CSMT", "arr": None, "dep": "06:05", "platform": 2},
    {"train_number": "12127", "seq": 7, "station_code": "SVJR", "arr": "09:55", "dep": "09:57", "platform": 3},
    {"train_number": "12127", "seq": 8, "station_code": "PUNE", "arr": "10:10", "dep": None, "platform": 5},
    {"train_number": "12128", "seq": 1, "station_code": "PUNE", "arr": None, "dep": "17:10", "platform": 2},
    {"train_number": "12128", "seq": 3, "station_code": "LNL",  "arr": "18:25", "dep": "18:27", "platform": 2},
    {"train_number": "12128", "seq": 8, "station_code": "CSMT", "arr": "21:07", "dep": None, "platform": 9},
    {"train_number": "12123", "seq": 1, "station_code": "CSMT", "arr": None, "dep": "07:15", "platform": 3},
    {"train_number": "12123", "seq": 7, "station_code": "PUNE", "arr": "11:15", "dep": None, "platform": 3},
    {"train_number": "12125", "seq": 1, "station_code": "CSMT", "arr": None, "dep": "06:25", "platform": 1},
    {"train_number": "12125", "seq": 4, "station_code": "PUNE", "arr": "09:25", "dep": None, "platform": 2},
    {"train_number": "11009", "seq": 1, "station_code": "CSMT", "arr": None, "dep": "05:30", "platform": 4},
    {"train_number": "11009", "seq": 6, "station_code": "PUNE", "arr": "09:15", "dep": None, "platform": 6},
    {"train_number": "12009", "seq": 1, "station_code": "MMCT", "arr": None, "dep": "06:00", "platform": 1},
    {"train_number": "12009", "seq": 3, "station_code": "ADI",  "arr": "10:45", "dep": None, "platform": 4},
]

STATIONS = [
    {"code": "CSMT", "name": "Mumbai CSMT", "aliases": ["CST", "VT"], "platform_count": 18},
    {"code": "PUNE", "name": "Pune Junction", "aliases": ["Pune", "Pune Jn"], "platform_count": 6},
    {"code": "LNL",  "name": "Lonavala",     "aliases": ["Lonavla"], "platform_count": 3},
    {"code": "SVJR", "name": "Shivajinagar", "aliases": [], "platform_count": 4},
    {"code": "MMCT", "name": "Mumbai Central", "aliases": [], "platform_count": 5},
    {"code": "ADI",  "name": "Ahmedabad", "aliases": [], "platform_count": 6},
]

# Journey fixtures
BOOKING_JOURNEY_12128 = {
    "device_id": "test", "mode": "booking", "train_number": "12128",
    "origin_code": "PUNE", "dest_code": "CSMT", "status": "active",
}
ROUTE_JOURNEY_CSMT_PUNE = {
    "device_id": "test", "mode": "route", "train_number": None,
    "origin_code": "CSMT", "dest_code": "PUNE", "status": "active",
}


class TestResolver:

    def test_exact_match_booking_mode(self):
        """Exact train number in booking mode → method=exact, score=1.0"""
        ext = _extraction(train_numbers=["12128"])
        res = resolve(ext, BOOKING_JOURNEY_12128, TRAINS, STOPS, STATIONS)
        assert res.method == "exact"
        assert res.score == 1.0
        assert res.matched_train == "12128"

    def test_route_mode_candidate_set(self):
        """Route mode CSMT→PUNE should include 12123, 12125, 12127, 11009"""
        ext = _extraction(train_numbers=["12123"])
        res = resolve(ext, ROUTE_JOURNEY_CSMT_PUNE, TRAINS, STOPS, STATIONS)
        assert res.method == "exact"
        assert "12123" in res.candidates_considered
        # 12009 should NOT be in candidates (it's MMCT→ADI)
        assert "12009" not in res.candidates_considered

    def test_fuzzy_corroborated(self):
        """One digit off (12126 vs 12128) + train name present → fuzzy_corroborated"""
        # Journey: booking on 12128
        ext = _extraction(train_numbers=["12126"], train_name="Intercity Express")
        res = resolve(ext, BOOKING_JOURNEY_12128, TRAINS, STOPS, STATIONS)
        assert res.method == "fuzzy_corroborated"
        assert res.score == pytest.approx(0.70)
        assert res.matched_train == "12128"
        assert res.heard == "12126"

    def test_fuzzy_uncorroborated(self):
        """One digit off without corroboration → fuzzy_uncorroborated, score=0.45"""
        ext = _extraction(train_numbers=["12126"])  # no train name
        res = resolve(ext, BOOKING_JOURNEY_12128, TRAINS, STOPS, STATIONS)
        assert res.method == "fuzzy_uncorroborated"
        assert res.score == pytest.approx(0.45)

    def test_ambiguous_tie(self):
        """Two candidates at distance 1 → ambiguous, score=0.30"""
        # Journey covers both 12127 and 12123 (CSMT→PUNE)
        # Heard 12124 — distance 1 from 12123, 12125, 12127 all differ by 1
        # Use a heard number that gives ties: 12128 → 12127 and 12127 are both dist 1 ... 
        # Actually for CSMT→PUNE: candidates are 12123, 12125, 12127, 11009
        # heard=12124 → dist to 12123=1, dist to 12125=2, dist to 12127=2, dist to 11009=large
        # That's only one candidate at dist=1 (12123), so not ambiguous.
        # Let's use heard=12126: dist to 12127=1 AND dist to 12125=1 — tie!
        ext = _extraction(train_numbers=["12126"])
        res = resolve(ext, ROUTE_JOURNEY_CSMT_PUNE, TRAINS, STOPS, STATIONS)
        # 12126 vs 12127: dist=1; 12126 vs 12125: dist=1 → tie → ambiguous
        assert res.method == "ambiguous"
        assert res.score == pytest.approx(0.30)

    def test_other_train(self):
        """12009 Shatabdi (MMCT→ADI) is not on CSMT→PUNE.
        12009 vs 11009 is dist=1, so per spec it resolves as fuzzy_uncorroborated matched to 11009.
        A truly 'other_train' case needs a heard number that is a real train AND has no candidate
        within distance 1. We test this with a booking journey (only candidate is 12128)
        where we hear 12009 — distance from 12009 to 12128 is 3 → other_train."""
        # Booking journey on 12128; candidate=[12128]
        ext = _extraction(train_numbers=["12009"])
        # Use booking journey — candidate set is only [12128], dist=3 from 12009
        booking = {"device_id": "test", "mode": "booking", "train_number": "12128",
                   "origin_code": "PUNE", "dest_code": "CSMT", "status": "active"}
        res = resolve(ext, booking, TRAINS, STOPS, STATIONS)
        assert res.method == "other_train"
        assert res.score == 0.0

    def test_unknown_number(self):
        """A number that doesn't exist in any train → unknown_number"""
        ext = _extraction(train_numbers=["99999"])
        res = resolve(ext, ROUTE_JOURNEY_CSMT_PUNE, TRAINS, STOPS, STATIONS)
        assert res.method == "unknown_number"
        assert res.score == pytest.approx(0.20)

    def test_platform_exceeds_station_max(self):
        """Platform 9 at a 6-platform station (PUNE) → platform_invalid=True"""
        # Booking on 12128 PUNE→CSMT
        ext = _extraction(train_numbers=["12128"], station="PUNE", platform=9)
        res = resolve(ext, BOOKING_JOURNEY_12128, TRAINS, STOPS, STATIONS)
        assert res.platform_invalid is True

    def test_no_journey(self):
        """No active journey → no_journey method"""
        ext = _extraction(train_numbers=["12128"])
        res = resolve(ext, None, TRAINS, STOPS, STATIONS)
        assert res.method == "no_journey"
        assert res.score == 0.0

    def test_name_only_match(self):
        """No number heard but train name matches → name_only"""
        ext = _extraction(train_numbers=[], train_name="Deccan Queen Express")
        res = resolve(ext, ROUTE_JOURNEY_CSMT_PUNE, TRAINS, STOPS, STATIONS)
        assert res.method == "name_only"
        assert res.matched_train in ("12123", "12125", "12127", "11009")
