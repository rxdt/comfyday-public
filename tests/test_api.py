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
            location_name="Inner Mission, Bernal Heights, San Francisco",
            query="94110",
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
            base_image_url="/static/generated/flux2/57_to_59_dry_cool_layer.png",
            subject_pose="front",
            render_mode="flux_static",
            generated_image_url="/static/generated/flux2/57_to_59_dry_cool_layer.png",
            selected_layer_keys=["57_to_59_dry_cool_layer"],
            layers=[],
        )
        with patch.object(main.scene_service, "get_scene", AsyncMock(return_value=scene)):
            client = TestClient(main.app)
            response = client.get("/api/scene", params={"query": "94110", "hours_ahead": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["location_name"], "Inner Mission, Bernal Heights, San Francisco")
        self.assertEqual(response.json()["feels_like_f"], 53.0)

    def test_scene_endpoint_rejects_out_of_range_forecast_hours(self) -> None:
        """FastAPI validation should reject forecast offsets beyond the supported window."""
        response = TestClient(main.app).get("/api/scene", params={"hours_ahead": 169})
        self.assertEqual(response.status_code, 422)

    def test_scene_endpoint_supports_multi_day_forecasts(self) -> None:
        """The API should allow checking weather several days ahead."""
        scene = SceneState(
            version=1,
            location_name="Inner Mission, Bernal Heights, San Francisco",
            query="94110",
            weather_latitude=37.7599,
            weather_longitude=-122.4148,
            mode="forecast",
            hours_ahead=72,
            target_time=datetime.now(UTC).isoformat(),
            temperature_f=61.0,
            feels_like_f=60.0,
            precip_probability_pct=5,
            description="Mostly clear",
            wind_label=None,
            bucket="61_to_62",
            rain_level="none",
            snow=False,
            night=False,
            outfit_note="note",
            stale=False,
            source="test",
            changed=True,
            last_updated=datetime.now(UTC).isoformat(),
            base_image_url="/static/generated/flux2/61_to_62_dry_light_layer.png",
            subject_pose="front",
            render_mode="flux_static",
            generated_image_url="/static/generated/flux2/61_to_62_dry_light_layer.png",
            selected_layer_keys=["61_to_62_dry_light_layer"],
            layers=[],
        )
        client = TestClient(main.app)
        for hours in (48, 72, 168):
            with self.subTest(hours=hours):
                with patch.object(main.scene_service, "get_scene", AsyncMock(return_value=scene)) as mocked:
                    response = client.get("/api/scene", params={"query": "94110", "hours_ahead": hours})
                self.assertEqual(response.status_code, 200)
                mocked.assert_awaited_once()

    def test_scene_endpoint_rejects_more_than_seven_days(self) -> None:
        """The API should cap forecasts at seven days."""
        response = TestClient(main.app).get("/api/scene", params={"hours_ahead": 169})
        self.assertEqual(response.status_code, 422)

    def test_scene_endpoint_maps_weather_runtime_errors(self) -> None:
        """Provider/runtime weather failures should return 503 instead of fake demo weather."""
        with patch.object(main.scene_service, "get_scene", AsyncMock(side_effect=RuntimeError("live weather down"))):
            response = TestClient(main.app).get("/api/scene", params={"query": "94110"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("live weather down", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
