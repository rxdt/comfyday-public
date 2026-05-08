"""Fixture-backed integration checks for real ZIP-to-weather scene generation."""

from __future__ import annotations

import json
import os
import unittest
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from dotenv import dotenv_values

from backend_models import ForecastBundle, LocationRecord, WeatherSnapshot
from weather_service import WeatherSceneService

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "integration"
RECORD_ENV = "COMFY_RECORD_INTEGRATION"


def _snapshot_to_dict(snapshot: WeatherSnapshot) -> dict[str, object]:
    """Serialize one snapshot with ISO datetimes for replay."""
    data = asdict(snapshot)
    data["observed_at"] = snapshot.observed_at.isoformat()
    return data


def _snapshot_from_dict(data: dict[str, object]) -> WeatherSnapshot:
    """Rebuild one snapshot from a recorded fixture."""
    return WeatherSnapshot(
        query=str(data["query"]),
        location_name=str(data["location_name"]),
        temperature_f=float(data["temperature_f"]),
        precip_probability_pct=int(data["precip_probability_pct"]),
        description=str(data["description"]),
        precip_in=float(data["precip_in"]),
        weather_code=int(data["weather_code"]),
        snow=bool(data["snow"]),
        night=bool(data["night"]),
        observed_at=datetime.fromisoformat(str(data["observed_at"])),
        source=str(data["source"]),
        feels_like_f=float(data["feels_like_f"]) if data.get("feels_like_f") is not None else None,
        wind_speed_mph=float(data["wind_speed_mph"]) if data.get("wind_speed_mph") is not None else None,
        wind_gust_mph=float(data["wind_gust_mph"]) if data.get("wind_gust_mph") is not None else None,
    )


def _bundle_to_dict(bundle: ForecastBundle) -> dict[str, object]:
    """Serialize a forecast bundle for offline replay."""
    return {
        "resolved_location": asdict(bundle.resolved_location),
        "current": _snapshot_to_dict(bundle.current),
        "hourly": [_snapshot_to_dict(snapshot) for snapshot in bundle.hourly],
    }


def _bundle_from_dict(data: dict[str, object]) -> ForecastBundle:
    """Rebuild a forecast bundle from a recorded fixture."""
    location = LocationRecord(**dict(data["resolved_location"]))
    return ForecastBundle(
        current=_snapshot_from_dict(dict(data["current"])),
        hourly=[_snapshot_from_dict(dict(snapshot)) for snapshot in list(data["hourly"])],
        resolved_location=location,
    )


class IntegrationWeatherTests(unittest.IsolatedAsyncioTestCase):
    """Run one live provider fetch once, then replay from fixtures after that."""

    async def _load_or_record_bundle(
        self,
        name: str,
        *,
        query: str,
        hours_ahead: int = 0,
        country_hint: str | None = None,
    ) -> ForecastBundle:
        """Load a recorded bundle or fetch it live and persist it for later runs."""
        path = FIXTURE_DIR / f"{name}.json"
        if path.exists():
            return _bundle_from_dict(json.loads(path.read_text()))

        if os.getenv(RECORD_ENV) != "1":
            self.skipTest(f"missing fixture {path.name}; rerun once with {RECORD_ENV}=1")

        env = {k: v for k, v in dotenv_values(".env").items() if v}
        with patch.dict(os.environ, env, clear=False):
            service = WeatherSceneService()
            bundle = await service.fetch_weather_bundle(query, hours_ahead=hours_ahead, country_hint=country_hint)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_bundle_to_dict(bundle), indent=2))
        return bundle

    async def test_sf_scene_integration_fixture(self) -> None:
        """A recorded 94110 bundle should replay into a valid current scene."""
        bundle = await self._load_or_record_bundle(
            "sf_94110_current",
            query="94110",
            hours_ahead=0,
            country_hint="US",
        )
        service = WeatherSceneService()
        with patch.object(service, "fetch_weather_bundle", AsyncMock(return_value=bundle)):
            scene = await service.get_scene(0, query="94110", country_hint="US")
        self.assertEqual(scene.query, "94110")
        self.assertEqual(scene.location_name, "Inner Mission, Bernal Heights, San Francisco")
        self.assertAlmostEqual(scene.weather_latitude or 0.0, 37.77493, places=1)
        self.assertAlmostEqual(scene.weather_longitude or 0.0, -122.41942, places=1)
        self.assertTrue(scene.generated_image_url.startswith("/static/generated/flux2/"))
        self.assertEqual(scene.render_mode, "flux_static")

    async def test_mexico_city_scene_integration_fixture(self) -> None:
        """A recorded 16999 bundle should replay into a valid Mexico City scene."""
        bundle = await self._load_or_record_bundle(
            "mexico_city_16999_current",
            query="16999",
            hours_ahead=0,
            country_hint="MX",
        )
        service = WeatherSceneService()
        with patch.object(service, "fetch_weather_bundle", AsyncMock(return_value=bundle)):
            scene = await service.get_scene(0, query="16999", country_hint="MX")
        self.assertEqual(scene.query, "16999")
        self.assertIn("Mexico City", scene.location_name)
        self.assertAlmostEqual(scene.weather_latitude or 0.0, 19.432608, places=1)
        self.assertAlmostEqual(scene.weather_longitude or 0.0, -99.133209, places=1)
        self.assertTrue(scene.generated_image_url.startswith("/static/generated/flux2/"))
        self.assertEqual(scene.render_mode, "flux_static")
