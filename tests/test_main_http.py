"""HTTP contract tests for the ZIP-only FastAPI surface."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main
from backend_models import SceneState


def _scene_state() -> SceneState:
    """Create one minimal JSON-serializable scene payload for route tests."""
    now = datetime(2026, 5, 8, 1, 0, tzinfo=UTC).isoformat()
    return SceneState(
        version=1,
        location_name="Inner Mission, Bernal Heights, San Francisco",
        query="94110",
        weather_latitude=37.7599,
        weather_longitude=-122.4148,
        mode="current",
        hours_ahead=0,
        target_time=now,
        temperature_f=58.0,
        feels_like_f=58.0,
        precip_probability_pct=0,
        description="Mostly clear",
        wind_label=None,
        bucket="59_to_60",
        rain_level="none",
        snow=False,
        night=False,
        outfit_note="Hoodie weather.",
        stale=False,
        source="test",
        changed=True,
        last_updated=now,
        base_image_url="/static/generated/flux2/59_to_61_dry_sweatsuit_layer.png",
        subject_pose="front",
        render_mode="flux_static",
        generated_image_url="/static/generated/flux2/59_to_61_dry_sweatsuit_layer.png",
        selected_layer_keys=["59_to_61_dry_sweatsuit_layer"],
        layers=[],
    )


def test_index_boots_with_default_zip() -> None:
    """The shell page should embed the default ZIP bootstrap payload."""
    client = TestClient(main.app)
    response = client.get("/")
    assert response.status_code == 200
    assert '"query": "94110"' in response.text


def test_api_scene_rejects_non_zip_query() -> None:
    """The API should reject any non-5-digit query before hitting backend logic."""
    client = TestClient(main.app)
    response = client.get("/api/scene", params={"query": "94abc"})
    assert response.status_code == 422


def test_api_scene_translates_backend_errors() -> None:
    """ValueError should become 400 and RuntimeError should become 503."""
    client = TestClient(main.app)
    with patch.object(main.scene_service, "get_scene", AsyncMock(side_effect=ValueError("bad zip"))):
        response = client.get("/api/scene", params={"query": "94110"})
        assert response.status_code == 400
        assert response.json()["detail"] == "bad zip"
    with patch.object(main.scene_service, "get_scene", AsyncMock(side_effect=RuntimeError("weather down"))):
        response = client.get("/api/scene", params={"query": "94110"})
        assert response.status_code == 503
        assert response.json()["detail"] == "weather down"


def test_api_scene_serializes_scene_payload() -> None:
    """A successful route call should pass through the scene payload unchanged."""
    client = TestClient(main.app)
    scene = _scene_state()
    with patch.object(main.scene_service, "get_scene", AsyncMock(return_value=scene)) as mocked:
        response = client.get(
            "/api/scene",
            params={"query": "94110", "hours_ahead": 3},
            headers={"x-vercel-ip-country": "US"},
        )
        assert response.status_code == 200
        assert response.json()["query"] == "94110"
        assert response.json()["hours_ahead"] == 0
        mocked.assert_awaited_once_with(3, query="94110", country_hint="US")
