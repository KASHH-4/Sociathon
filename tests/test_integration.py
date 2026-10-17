"""End-to-end integration and smoke tests for TransitHear application."""
import json
import pytest


def test_spa_routes(client):
    """Test that all client-side SPA routes serve the application shell."""
    for path in ["/", "/map", "/communication", "/recovery", "/wearable", "/custom-spa-route"]:
        res = client.get(path)
        assert res.status_code == 200
        assert b'<div id="root">' in res.data
        assert res.headers.get("Cache-Control") == "no-cache"


def test_live_templates(client):
    """Test that /live and /live/audit serve their respective Jinja templates."""
    res_live = client.get("/live")
    assert res_live.status_code == 200
    assert b"TransitHear" in res_live.data

    res_audit = client.get("/live/audit")
    assert res_audit.status_code == 200
    assert b"TransitHear" in res_audit.data


def test_catch_all_404_for_missing_api_and_live(client):
    """Test that missing /api and /live routes return 404 instead of SPA shell."""
    res_api = client.get("/api/nonexistent-endpoint")
    assert res_api.status_code == 404

    res_live = client.get("/live/nonexistent-view")
    assert res_live.status_code == 404


def test_health_api(client):
    """Test the /api/health endpoint returns structured health status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] in ("ok", "online")
    assert "app" in data
    assert "store" in data


def test_transit_api(client):
    """Test the transit status and announcements endpoints."""
    res_status = client.get("/api/transit/status")
    assert res_status.status_code == 200
    data_status = res_status.get_json()
    assert "train_number" in data_status

    res_ann = client.get("/api/transit/announcements")
    assert res_ann.status_code == 200
    data_ann = res_ann.get_json()
    assert "announcements" in data_ann


def test_facilities_api(client):
    """Test the /api/facilities endpoint."""
    res = client.get("/api/facilities?station=PUNE")
    assert res.status_code == 200
    data = res.get_json()
    assert "facilities" in data


def test_communication_phrases_api(client):
    """Test communication quick phrases endpoint."""
    res = client.get("/api/communication/phrases")
    assert res.status_code == 200
    data = res.get_json()
    assert "phrases" in data


def test_wearable_haptic_api(client):
    """Test simulated wearable haptic pulse endpoint."""
    res = client.post("/api/wearable/simulate-haptic", json={"pattern": "alert"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["pattern"] == "alert"


def test_simulation_endpoints(client):
    """Test simulation trigger endpoints."""
    res_ann = client.post("/api/simulate/announcement", json={"scenario": "platform_change"})
    assert res_ann.status_code == 200
    data_ann = res_ann.get_json()
    assert "scenario" in data_ann
    assert data_ann.get("simulated") is True


def test_static_pwa_assets(client):
    """Test that critical PWA assets are served directly."""
    res_manifest = client.get("/manifest.webmanifest")
    assert res_manifest.status_code == 200

    res_sw = client.get("/sw.js")
    assert res_sw.status_code == 200


def test_live_core_assets(client):
    """Test that transit-live-core bridge JS and CSS are served directly."""
    res_js = client.get("/assets/transit-live-core.js")
    assert res_js.status_code == 200
    assert b"TransitHear Unified" in res_js.data

    res_css = client.get("/assets/transit-live-core.css")
    assert res_css.status_code == 200
    assert b"--th-navy" in res_css.data


def test_train_and_station_search(client):
    """Test train and station search APIs for live journey selection."""
    res_trains = client.get("/api/trains?q=Deccan")
    assert res_trains.status_code == 200
    assert "trains" in res_trains.get_json()

    res_stations = client.get("/api/stations?q=Pune")
    assert res_stations.status_code == 200
    assert "stations" in res_stations.get_json()

