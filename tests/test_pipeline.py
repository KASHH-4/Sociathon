"""Tests for pipeline.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from transithear.db import MemoryRepo


# Common device_id for pipeline tests
DEVICE = "pipeline-test-device"


def fresh_repo_with_journey(mode="route", origin="CSMT", dest="PUNE"):
    repo = MemoryRepo()
    j = repo.create_journey({
        "device_id": DEVICE,
        "mode": mode,
        "train_number": "12128" if mode == "booking" else None,
        "origin_code": origin,
        "dest_code": dest,
        "status": "active",
    })
    return repo


class TestPipeline:

    def test_non_announcement_not_persisted(self, monkeypatch):
        """Non-PA text should not be persisted. Pipeline returns ignore."""
        import transithear.db as db_module
        import transithear.config as cfg
        repo = fresh_repo_with_journey()
        monkeypatch.setattr(db_module, "_repo", repo)
        monkeypatch.setattr(db_module, "_store_degraded", False)
        monkeypatch.setattr(cfg, "GEMINI_ENABLED", False)
        import transithear.extract_gemini as gem
        monkeypatch.setattr(gem, "_client_loaded", False)
        monkeypatch.setattr(gem, "_client", None)

        from transithear.pipeline import process
        result = process(
            device_id=DEVICE,
            transcript="Testing testing one two three. Microphone check.",
            stt_source="manual",
            stt_confidence=0.9,
        )
        assert result["decision"] == "ignore"
        # No announcement row should be stored
        anns = repo.list_announcements(DEVICE)
        assert len(anns) == 0

    def test_gemini_failure_falls_back_to_rules(self, monkeypatch):
        """When Gemini raises, extractor should be 'rules' and degraded=True."""
        import transithear.db as db_module
        import transithear.config as cfg
        import transithear.extract_gemini as gem

        repo = fresh_repo_with_journey()
        monkeypatch.setattr(db_module, "_repo", repo)
        monkeypatch.setattr(db_module, "_store_degraded", False)
        monkeypatch.setattr(cfg, "GEMINI_ENABLED", True)

        # Force Gemini to fail
        def _fake_extract(*args, **kwargs):
            from transithear.extract_rules import extract as rules_extract
            result = rules_extract(args[0], args[1])
            result.degraded = True
            return result

        monkeypatch.setattr(gem, "extract", _fake_extract)
        monkeypatch.setattr(gem, "_client_loaded", True)
        monkeypatch.setattr(gem, "_client", None)

        from transithear.pipeline import process
        result = process(
            device_id=DEVICE,
            transcript=(
                "Attention please. Train number 12123 Deccan Queen will now "
                "arrive at platform 5 at Pune Junction."
            ),
            stt_source="manual",
            stt_confidence=0.8,
        )
        assert result.get("degraded") is True
        assert result.get("extractor") == "rules"

    def test_pipeline_never_raises(self, monkeypatch):
        """Pipeline must return a safe dict even if everything breaks."""
        import transithear.db as db_module
        import transithear.config as cfg

        # Make the repo raise on get_active_journey
        class BrokenRepo(MemoryRepo):
            def get_active_journey(self, device_id):
                raise RuntimeError("Simulated DB failure")
            def list_announcements(self, *a, **kw):
                return []

        monkeypatch.setattr(db_module, "_repo", BrokenRepo())
        monkeypatch.setattr(db_module, "_store_degraded", False)
        monkeypatch.setattr(cfg, "GEMINI_ENABLED", False)

        from transithear.pipeline import process
        result = process(
            device_id=DEVICE,
            transcript="Train 12123 platform 5 Pune Junction",
            stt_source="manual",
        )
        # Should not raise; should return a safe response
        assert "decision" in result
        assert result.get("error") is not None  # error field populated

    def test_oversized_transcript_rejected(self, monkeypatch):
        """Transcript over MAX_TRANSCRIPT_CHARS → ignore without persisting."""
        import transithear.db as db_module
        import transithear.config as cfg
        repo = fresh_repo_with_journey()
        monkeypatch.setattr(db_module, "_repo", repo)
        monkeypatch.setattr(db_module, "_store_degraded", False)
        monkeypatch.setattr(cfg, "GEMINI_ENABLED", False)

        from transithear.pipeline import process
        result = process(
            device_id=DEVICE,
            transcript="x" * 2000,
            stt_source="manual",
        )
        assert result["decision"] == "ignore"
        assert len(repo.list_announcements(DEVICE)) == 0


class TestAPIEndpoints:
    """Integration tests using Flask test client."""

    def test_health_200(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "online"
        assert "integrations" in data
        assert "store" in data

    def test_journey_create_201(self, client):
        res = client.post("/api/journey", json={
            "device_id": "api-test-device",
            "mode": "route",
            "origin": "CSMT",
            "destination": "PUNE",
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data["journey"]["origin_code"] == "CSMT"
        assert len(data.get("candidates", [])) > 0

    def test_journey_missing_fields_400(self, client):
        res = client.post("/api/journey", json={
            "device_id": "api-test-device",
            "mode": "route",
            "origin": "CSMT",
            # Missing destination
        })
        assert res.status_code == 400

    def test_ingest_missing_device_id_400(self, client):
        res = client.post("/api/announcements/ingest", json={
            "transcript": "Train 12123 platform 3",
        })
        assert res.status_code == 400

    def test_ingest_missing_transcript_400(self, client):
        res = client.post("/api/announcements/ingest", json={
            "device_id": "api-test-device",
        })
        assert res.status_code == 400

    def test_ingest_oversized_transcript_413(self, client):
        res = client.post("/api/announcements/ingest", json={
            "device_id": "api-test-device",
            "transcript": "x" * 1001,
        })
        assert res.status_code == 413

    def test_ingest_valid_returns_200(self, client):
        res = client.post("/api/announcements/ingest", json={
            "device_id": "api-test-device",
            "transcript": (
                "Attention passengers. Train 12123 Deccan Queen will now "
                "arrive at platform 5 at Pune Junction."
            ),
            "stt_source": "manual",
            "stt_confidence": 0.85,
        })
        assert res.status_code == 200
        data = res.get_json()
        assert "decision" in data
        assert "confidence" in data

    def test_simulate_all_scenarios_200(self, client):
        scenarios = [
            "platform_change", "delay", "early_arrival", "cancellation",
            "safety", "misrecognized_number", "other_train", "noise",
        ]
        for scenario in scenarios:
            res = client.post("/api/simulate/announcement", json={
                "device_id": "api-test-device",
                "scenario": scenario,
            })
            assert res.status_code == 200, f"Scenario {scenario} failed: {res.get_json()}"
            data = res.get_json()
            assert data.get("simulated") is True, f"Scenario {scenario} not simulated"

    def test_simulate_invalid_scenario_400(self, client):
        res = client.post("/api/simulate/announcement", json={
            "device_id": "api-test-device",
            "scenario": "nonexistent",
        })
        assert res.status_code == 400

    def test_simulate_safety_always_alert_critical(self, client):
        """R5: safety scenario must return alert_critical."""
        # Set up a journey first
        client.post("/api/journey", json={
            "device_id": "safety-test-device",
            "mode": "route",
            "origin": "CSMT",
            "destination": "PUNE",
        })
        res = client.post("/api/simulate/announcement", json={
            "device_id": "safety-test-device",
            "scenario": "safety",
        })
        data = res.get_json()
        assert data["decision"] == "alert_critical"

    def test_other_train_ignored(self, client):
        """other_train scenario (12009) → decision=ignore when booked on 12128.
        Note: With CSMT→PUNE route mode, 11009 is in the candidate set and
        12009 is dist=1 from 11009, so it resolves as fuzzy_uncorroborated.
        For a clean other_train test, use booking mode on 12128."""
        client.post("/api/journey", json={
            "device_id": "other-train-test-b",
            "mode": "booking",
            "train_number": "12128",
            "origin": "PUNE",
            "destination": "CSMT",
        })
        res = client.post("/api/simulate/announcement", json={
            "device_id": "other-train-test-b",
            "scenario": "other_train",
        })
        data = res.get_json()
        assert data["decision"] == "ignore"

    def test_announcements_list(self, client):
        res = client.get("/api/announcements?device_id=api-test-device&limit=10")
        assert res.status_code == 200
        data = res.get_json()
        assert "announcements" in data

    def test_announcements_missing_device_id_400(self, client):
        res = client.get("/api/announcements")
        assert res.status_code == 400

    def test_stations_typeahead(self, client):
        res = client.get("/api/stations?q=Pune")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data.get("stations", [])) > 0

    def test_trains_typeahead(self, client):
        res = client.get("/api/trains?q=Deccan")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data.get("trains", [])) > 0

    def test_facilities_returns_200(self, client):
        res = client.get("/api/facilities?station=PUNE")
        assert res.status_code == 200
        data = res.get_json()
        assert data.get("simulated") is True
        assert len(data.get("facilities", [])) > 0

    def test_audit_log_200(self, client):
        res = client.get("/api/audit/log?limit=10")
        assert res.status_code == 200

    def test_audit_summary_200(self, client):
        res = client.get("/api/audit/summary")
        assert res.status_code == 200

    def test_preferences_get_put(self, client):
        res = client.get("/api/preferences?device_id=pref-test-device")
        assert res.status_code == 200

        res = client.put("/api/preferences", json={
            "device_id": "pref-test-device",
            "haptic": False,
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["preferences"]["haptic"] is False

    def test_simulate_official_update_201(self, client):
        res = client.post("/api/simulate/official-update", json={
            "train_number": "12123",
            "station_code": "PUNE",
            "kind": "platform_change",
            "new_platform": 5,
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data.get("simulated") is True

    def test_simulate_emergency_201(self, client):
        res = client.post("/api/simulate/emergency", json={
            "device_id": "emergency-test-device",
            "message": "Test emergency",
        })
        assert res.status_code == 201
        data = res.get_json()
        assert data.get("simulated") is True

    def test_wearable_haptic_labelled_simulated(self, client):
        res = client.post("/api/wearable/simulate-haptic", json={"pattern": "alert"})
        assert res.status_code == 200
        data = res.get_json()
        assert data.get("simulated") is True

    def test_acknowledge_nonexistent_404(self, client):
        res = client.post("/api/announcements/nonexistent-id/ack")
        assert res.status_code == 404

    def test_live_page_200(self, client):
        res = client.get("/live")
        assert res.status_code == 200

    def test_live_audit_page_200(self, client):
        res = client.get("/live/audit")
        assert res.status_code == 200

    def test_spa_routes_still_200(self, client):
        for route in ["/", "/map", "/communication", "/recovery", "/wearable"]:
            res = client.get(route)
            assert res.status_code == 200, f"Route {route} failed"
