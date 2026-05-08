"""API tests for the backend entrypoints with mocked service calls."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main
from backend_models import LocationRecord, SceneState


class ApiTests(unittest.TestCase):
    """Keep HTTP endpoint contracts stable without hitting live providers."""

    def test_scene_endpoint_serializes_mocked_scene(self) -> None:
        """`/api/scene` should return the scene payload from the service."""
        scene = SceneState(
            version=1,
            location_name="Mission, San Francisco",
            query="Mission",
            weather_latitude=37.7599,
            weather_longitude=-122.4148,
            mode="current",
            hours_ahead=0,
            target_time=datetime.now(UTC).isoformat(),
            temperature_f=58.0,
            feels_like_f=53.0,
            precip_probability_pct=0,
            description="Mostly clear",
            wind_label=None,
            bucket="cool",
            rain_level="none",
            snow=False,
            night=False,
            outfit_note="note",
            stale=False,
            source="test",
            changed=True,
            last_updated=datetime.now(UTC).isoformat(),
            base_image_url="/static/generated/flux2/cool_weather_near_the_bay_or_coast.png",
            subject_pose="front",
            render_mode="flux_static",
            generated_image_url="/static/generated/flux2/cool_weather_near_the_bay_or_coast.png",
            selected_layer_keys=["cool_weather_near_the_bay_or_coast"],
            layers=[],
        )
        with patch.object(main.scene_service, "get_scene", AsyncMock(return_value=scene)):
            client = TestClient(main.app)
            response = client.get("/api/scene", params={"query": "Mission", "hours_ahead": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["location_name"], "Mission, San Francisco")
        self.assertEqual(response.json()["feels_like_f"], 53.0)

    def test_scene_endpoint_rejects_out_of_range_forecast_hours(self) -> None:
        """FastAPI validation should reject forecast offsets beyond the supported window."""
        response = TestClient(main.app).get("/api/scene", params={"hours_ahead": 25})
        self.assertEqual(response.status_code, 422)

    def test_scene_endpoint_maps_weather_runtime_errors(self) -> None:
        """Provider/runtime weather failures should return 503 instead of fake demo weather."""
        with patch.object(main.scene_service, "get_scene", AsyncMock(side_effect=RuntimeError("live weather down"))):
            response = TestClient(main.app).get("/api/scene", params={"query": "Mission"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("live weather down", response.json()["detail"])

    def test_locations_endpoint_serializes_mocked_location(self) -> None:
        """`/api/locations` should return the resolved location payload."""
        location = LocationRecord(
            query="Mission",
            display_name="Mission, San Francisco",
            latitude=37.7599,
            longitude=-122.4148,
            timezone="America/Los_Angeles",
            country="United States",
            country_code="US",
            admin1="California",
            admin2="San Francisco County",
            geocoder="test",
            tomorrow_location="37.7599,-122.4148",
        )
        with patch.object(main.scene_service, "resolve_location", AsyncMock(return_value=location)):
            client = TestClient(main.app)
            response = client.get("/api/locations", params={"q": "Mission"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["display_name"], "Mission, San Francisco")

    def test_locations_endpoint_maps_resolution_errors(self) -> None:
        """Location validation/provider misses should become stable HTTP errors."""
        client = TestClient(main.app)
        with patch.object(main.scene_service, "resolve_location", AsyncMock(side_effect=ValueError("bad query"))):
            self.assertEqual(client.get("/api/locations", params={"q": "x"}).status_code, 400)
        with patch.object(main.scene_service, "resolve_location", AsyncMock(side_effect=RuntimeError("not found"))):
            self.assertEqual(client.get("/api/locations", params={"q": "x"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
