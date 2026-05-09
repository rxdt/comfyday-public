"""Async tests for ZIP-only provider orchestration and scene fallback behavior."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from backend_models import ForecastBundle, LocationRecord, SceneState, WeatherSnapshot
from weather_service import WeatherSceneService, normalize_zip_code


class WeatherServiceTests(unittest.IsolatedAsyncioTestCase):
    """Keep ZIP-only provider fallback and stale-scene behavior stable."""

    def setUp(self) -> None:
        self.service = WeatherSceneService()
        self.location = LocationRecord(
            query="94110",
            display_name="Mission District, San Francisco",
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
            query="94110",
            location_name="Mission District, San Francisco",
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
        """The app should always boot on 94110, independent of env defaults."""
        with patch.dict("os.environ", {"WEATHER_QUERY": "94122", "TOMORROW_LOCATION": "94122"}):
            self.assertEqual(WeatherSceneService().default_query, "94110")

    async def test_normalize_zip_code_accepts_only_five_digits(self) -> None:
        """ZIP normalization should reject any free-text or malformed input."""
        self.assertEqual(normalize_zip_code("94110", "94110"), "94110")
        self.assertEqual(normalize_zip_code(None, "94110"), "94110")
        with self.assertRaisesRegex(ValueError, "exactly 5 digits"):
            normalize_zip_code("Mission", "94110")
        with self.assertRaisesRegex(ValueError, "exactly 5 digits"):
            normalize_zip_code("9411", "94110")

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
            result = await self.service.fetch_weather_bundle("94110", hours_ahead=3)
        self.assertIs(result, bundle)
        weatherstack_mock.assert_awaited()

    async def test_fetch_weather_bundle_passes_multi_day_hours_to_provider(self) -> None:
        """Service should forward long-range forecast offsets without truncating them."""
        self.service.tomorrow_api_key = "tomorrow"
        bundle = ForecastBundle(current=self.snapshot, hourly=[], resolved_location=self.location)
        with (
            patch.object(self.service, "resolve_weather_location", AsyncMock(return_value=self.location)),
            patch("weather_service.fetch_tomorrow_bundle", AsyncMock(return_value=bundle)) as tomorrow_mock,
        ):
            result = await self.service.fetch_weather_bundle("94110", hours_ahead=168, country_hint="US")
        self.assertIs(result, bundle)
        tomorrow_mock.assert_awaited_once()
        self.assertEqual(tomorrow_mock.await_args.kwargs["hours_ahead"], 168)

    async def test_get_scene_uses_cached_bundle_after_provider_failure(self) -> None:
        """Provider failure should return a stale scene from the cached weather bundle."""
        bundle = ForecastBundle(current=self.snapshot, hourly=[], resolved_location=self.location)
        self.service.weather_bundle_cache["94110"] = bundle
        with patch.object(self.service, "fetch_weather_bundle", AsyncMock(side_effect=RuntimeError("down"))):
            scene = await self.service.get_scene(0, query="94110")
        self.assertIsInstance(scene, SceneState)
        self.assertTrue(scene.stale)
        self.assertTrue(scene.source.endswith("-cache"))
        self.assertEqual(scene.location_name, "Mission District, San Francisco")

    async def test_get_scene_raises_when_providers_fail_without_cache(self) -> None:
        """Provider failure without cache should not return fake demo weather."""
        with patch.object(self.service, "fetch_weather_bundle", AsyncMock(side_effect=RuntimeError("down"))):
            with self.assertRaisesRegex(RuntimeError, "Live weather unavailable"):
                await self.service.get_scene(0, query="94110")

    async def test_forecast_failure_without_cached_hourly_data_does_not_project_weather(self) -> None:
        """Forecast fallback should not invent future weather from current conditions."""
        bundle = ForecastBundle(current=self.snapshot, hourly=[], resolved_location=self.location)
        self.service.weather_bundle_cache["94110"] = bundle
        with patch.object(self.service, "fetch_weather_bundle", AsyncMock(side_effect=RuntimeError("down"))):
            with self.assertRaisesRegex(RuntimeError, "Live weather unavailable"):
                await self.service.get_scene(3, query="94110")


if __name__ == "__main__":
    unittest.main()
