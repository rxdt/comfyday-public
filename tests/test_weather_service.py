"""Async tests for provider orchestration and scene fallback behavior."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from backend_models import ForecastBundle, LocationRecord, SceneState, WeatherSnapshot
from weather_service import WeatherSceneService


class WeatherServiceTests(unittest.IsolatedAsyncioTestCase):
    """Keep provider fallback and stale-scene behavior stable."""

    def setUp(self) -> None:
        self.service = WeatherSceneService()
        self.location = LocationRecord(
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
        self.snapshot = WeatherSnapshot(
            query="Mission",
            location_name="Mission, San Francisco",
            temperature_f=58,
            precip_probability_pct=0,
            description="Mostly clear",
            precip_in=0,
            weather_code=1100,
            snow=False,
            night=False,
            observed_at=datetime(2026, 5, 7, 2, 0, tzinfo=UTC),
            source="test",
        )

    async def test_default_query_is_hardcoded_to_94110(self) -> None:
        """The app should always boot on the Mission ZIP, independent of env defaults."""
        with patch.dict("os.environ", {"WEATHER_QUERY": "94122", "TOMORROW_LOCATION": "94122"}):
            self.assertEqual(WeatherSceneService().default_query, "94110")

    async def test_fetch_weather_bundle_falls_back_to_weatherstack(self) -> None:
        """Tomorrow failure should fall through to Weatherstack when configured."""
        self.service.tomorrow_api_key = "tomorrow"
        self.service.weatherstack_api_key = "weatherstack"
        bundle = ForecastBundle(current=self.snapshot, hourly=[], resolved_location=self.location)
        with (
            patch.object(self.service, "resolve_weather_location", AsyncMock(return_value=self.location)),
            patch("weather_service.fetch_tomorrow_bundle", AsyncMock(side_effect=RuntimeError("tomorrow down"))),
            patch("weather_service.fetch_weatherstack_bundle", AsyncMock(return_value=bundle)) as weatherstack_mock,
        ):
            result = await self.service.fetch_weather_bundle("Mission", hours_ahead=3)
        self.assertIs(result, bundle)
        weatherstack_mock.assert_awaited()

    async def test_get_scene_uses_cached_bundle_after_provider_failure(self) -> None:
        """Provider failure should return a stale scene from the cached weather bundle."""
        bundle = ForecastBundle(current=self.snapshot, hourly=[], resolved_location=self.location)
        self.service.weather_bundle_cache["mission"] = bundle
        with patch.object(self.service, "fetch_weather_bundle", AsyncMock(side_effect=RuntimeError("down"))):
            scene = await self.service.get_scene(0, query="Mission")
        self.assertIsInstance(scene, SceneState)
        self.assertTrue(scene.stale)
        self.assertTrue(scene.source.endswith("-cache"))
        self.assertEqual(scene.location_name, "Mission District, San Francisco")

    async def test_get_scene_raises_when_providers_fail_without_cache(self) -> None:
        """Provider failure without cache should not return fake demo weather."""
        with patch.object(self.service, "fetch_weather_bundle", AsyncMock(side_effect=RuntimeError("down"))):
            with self.assertRaisesRegex(RuntimeError, "Live weather unavailable"):
                await self.service.get_scene(0, query="Mission")

    async def test_forecast_failure_without_cached_hourly_data_does_not_project_weather(self) -> None:
        """Forecast fallback should not invent future weather from current conditions."""
        bundle = ForecastBundle(current=self.snapshot, hourly=[], resolved_location=self.location)
        self.service.weather_bundle_cache["mission"] = bundle
        with patch.object(self.service, "fetch_weather_bundle", AsyncMock(side_effect=RuntimeError("down"))):
            with self.assertRaisesRegex(RuntimeError, "Live weather unavailable"):
                await self.service.get_scene(3, query="Mission")


if __name__ == "__main__":
    unittest.main()
