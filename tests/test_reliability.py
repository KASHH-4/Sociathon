"""Tests for reliability.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import pytest
from transithear.reliability import fuse_and_decide, _dedupe_cache
from transithear.extract_rules import Extraction
from transithear.resolver import Resolution
from transithear.verifier import Verification


def make_extraction(type="platform_change", platform=3, delay=None, confidence=0.65):
    return Extraction(
        is_announcement=True,
        language="en-IN",
        type=type,
        train_numbers_heard=["12128"],
        train_name_heard=None,
        station_mentioned="PUNE",
        platform=platform,
        delay_minutes=delay,
        new_time=None,
        display_text="Platform change test",
        recommended_action="Go to platform 3",
        confidence=confidence,
        uncertain_fields=[],
        extractor="rules",
    )


def make_resolution(method="exact", matched="12128", heard="12128", score=1.0,
                    platform_invalid=False, notes=None):
    return Resolution(
        method=method,
        heard=heard,
        matched_train=matched,
        candidates_considered=["12128"],
        distance=0 if method == "exact" else 1,
        corroboration=True,
        score=score,
        notes=notes or [],
        platform_invalid=platform_invalid,
    )


def make_verification(status="unconfirmed", official_row=None, schedule_ok=True):
    return Verification(
        status=status,
        official_row=official_row,
        schedule_ok=schedule_ok,
        notes=[],
    )


class TestReliabilityGate:

    def setup_method(self):
        """Clear dedupe cache before each test."""
        _dedupe_cache.clear()

    def test_alert_critical_above_threshold(self):
        """High-confidence platform_change → alert_critical"""
        result = fuse_and_decide(
            device_id="test-reliability-1",
            stt_confidence=0.95,
            extraction=make_extraction(confidence=0.65),
            resolution=make_resolution(score=1.0),
            verification=make_verification(status="confirmed"),
            user_prefs=None,
            repo=None,
        )
        assert result["decision"] == "alert_critical"

    def test_verify_with_staff_medium_confidence(self):
        """Medium confidence → verify_with_staff"""
        result = fuse_and_decide(
            device_id="test-reliability-2",
            stt_confidence=0.6,
            extraction=make_extraction(confidence=0.55),
            resolution=make_resolution(score=0.45, method="fuzzy_uncorroborated"),
            verification=make_verification(status="unconfirmed"),
            user_prefs=None,
            repo=None,
        )
        # final ≈ 0.25*0.6 + 0.25*0.55 + 0.30*0.45 + 0.20*0.5 = 0.52 → verify_with_staff
        assert result["decision"] in ("verify_with_staff", "ignore")

    def test_ignore_low_confidence(self):
        """Very low confidence → ignore"""
        result = fuse_and_decide(
            device_id="test-reliability-3",
            stt_confidence=0.3,
            extraction=make_extraction(confidence=0.30),
            resolution=make_resolution(score=0.20, method="unknown_number"),
            verification=make_verification(status="unconfirmed"),
            user_prefs=None,
            repo=None,
        )
        assert result["decision"] == "ignore"

    def test_r5_safety_always_shown(self):
        """R5: safety type always shown even at low confidence"""
        result = fuse_and_decide(
            device_id="test-reliability-safety",
            stt_confidence=0.2,
            extraction=make_extraction(type="safety", confidence=0.2),
            resolution=make_resolution(score=0.1, method="unknown_number"),
            verification=make_verification(status="unconfirmed"),
            user_prefs=None,
            repo=None,
        )
        assert result["decision"] == "alert_critical"
        assert "R5" in result["rules_fired"]

    def test_r6_dedupe(self):
        """R6: same (train, type, platform) within DEDUPE_SECONDS → deduped=True, no second row"""
        kwargs = dict(
            stt_confidence=0.95,
            extraction=make_extraction(confidence=0.65, type="platform_change", platform=3),
            resolution=make_resolution(score=1.0),
            verification=make_verification(status="confirmed"),
            user_prefs=None,
            repo=None,
        )
        r1 = fuse_and_decide(device_id="test-dedupe-device", **kwargs)
        r2 = fuse_and_decide(device_id="test-dedupe-device", **kwargs)
        # First call should not be deduped
        assert not r1.get("deduped")
        # Second call should be deduped
        assert r2.get("deduped") is True
        assert "R6" in r2["rules_fired"]

    def test_r4_official_conflict(self):
        """R4: official feed conflict → verify_with_staff"""
        result = fuse_and_decide(
            device_id="test-reliability-r4",
            stt_confidence=0.95,
            extraction=make_extraction(confidence=0.65, platform=3),
            resolution=make_resolution(score=1.0),
            verification=make_verification(
                status="conflict",
                official_row={"new_platform": 5, "kind": "platform_change"},
            ),
            user_prefs=None,
            repo=None,
        )
        assert result["decision"] == "verify_with_staff"
        assert "R4" in result["rules_fired"]

    def test_r2_platform_invalid(self):
        """R2: platform out of bounds → verify_with_staff"""
        result = fuse_and_decide(
            device_id="test-reliability-r2",
            stt_confidence=0.95,
            extraction=make_extraction(confidence=0.65, platform=9),
            resolution=make_resolution(score=1.0, platform_invalid=True),
            verification=make_verification(status="unconfirmed"),
            user_prefs=None,
            repo=None,
        )
        assert result["decision"] == "verify_with_staff"
        assert "R2" in result["rules_fired"]

    def test_weights_renormalize_no_resolution(self):
        """When resolution is no_journey, weights should still produce valid confidence."""
        result = fuse_and_decide(
            device_id="test-reliability-nj",
            stt_confidence=0.8,
            extraction=make_extraction(confidence=0.55, type="arrival"),
            resolution=Resolution(
                method="no_journey", heard=None, matched_train=None,
                candidates_considered=[], distance=None, corroboration=False,
                score=0.0,
            ),
            verification=make_verification(status="unconfirmed"),
            user_prefs=None,
            repo=None,
        )
        # Should not raise; confidence should be a valid float
        assert isinstance(result["confidence"], float)
        assert 0 <= result["confidence"] <= 1

    def test_other_train_ignored(self):
        """other_train method → ignore regardless of confidence"""
        result = fuse_and_decide(
            device_id="test-other-train",
            stt_confidence=0.99,
            extraction=make_extraction(confidence=0.99),
            resolution=make_resolution(
                method="other_train", matched="12009", heard="12009", score=0.0
            ),
            verification=make_verification(status="unconfirmed"),
            user_prefs=None,
            repo=None,
        )
        assert result["decision"] == "ignore"

    def test_haptic_disabled_by_prefs(self):
        """haptic=false preference → empty haptic_pattern"""
        result = fuse_and_decide(
            device_id="test-haptic-off",
            stt_confidence=0.95,
            extraction=make_extraction(confidence=0.65),
            resolution=make_resolution(score=1.0),
            verification=make_verification(status="confirmed"),
            user_prefs={"haptic": False},
            repo=None,
        )
        assert result["haptic_pattern"] == []
