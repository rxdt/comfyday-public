"""Unit tests for weather normalization helpers."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

import httpx

from backend_models import LocationRecord
from weather_api import (
    build_snapshot,
    explain_weather_provider_failure,
    fetch_tomorrow_bundle,
    fetch_weatherstack_bundle,
    required_float,
    total_precip_intensity_in,
)


class WeatherApiTests(unittest.IsolatedAsyncioTestCase):
    """Keep provider normalization deterministic."""

    def _location(self) -> LocationRecord:
        """Build one provider-ready test location."""
        return LocationRecord(
            query="Montara",
            display_name="Montara, San Mateo",
            latitude=37.5422,
            longitude=-122.5161,
            timezone="America/Los_Angeles",
            country="United States",
            country_code="US",
            admin1="California",
            admin2="San Mateo County",
            geocoder="test",
            tomorrow_location="37.5422,-122.5161",
        )

    def test_build_snapshot_infers_snow_and_night(self) -> None:
        """Snow codes and local evening hours should set normalized booleans."""
        snapshot = build_snapshot(
            query="Outer Sunset",
            location_name="Outer Sunset, San Francisco",
            temperature_f=39,
            feels_like_f=34,
            wind_speed_mph=13,
            wind_gust_mph=20,
            precip_probability_pct=110,
            precip_in=0.2,
            weather_code=5000,
            observed_at=datetime(2026, 1, 10, 3, 0, tzinfo=UTC),
            timezone_name="America/Los_Angeles",
            source="test",
        )
        self.assertTrue(snapshot.snow)
        self.assertTrue(snapshot.night)
        self.assertEqual(snapshot.feels_like_f, 34)
        self.assertEqual(snapshot.wind_speed_mph, 13)
        self.assertEqual(snapshot.wind_gust_mph, 20)
        self.assertEqual(snapshot.precip_probability_pct, 100)

    def test_total_precip_intensity_combines_components(self) -> None:
        """All precipitation components should contribute to one combined intensity."""
        self.assertEqual(
            total_precip_intensity_in(
                {
                    "rainIntensity": 0.02,
                    "snowIntensity": 0.03,
                    "sleetIntensity": 0.01,
                    "freezingRainIntensity": 0.04,
                }
            ),
            0.1,
        )

    def test_required_provider_fields_fail_closed(self) -> None:
        """Missing provider fields should not become fake default weather."""
        with self.assertRaisesRegex(RuntimeError, "temperature"):
            required_float({}, "temperature")

    def test_explain_provider_failure_covers_rate_limit_and_timeout(self) -> None:
        """Provider failure messages should stay short and actionable."""
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(429, request=request)
        self.assertIn(
            "rate limited",
            explain_weather_provider_failure(httpx.HTTPStatusError("boom", request=request, response=response)),
        )
        self.assertEqual("request timeout", explain_weather_provider_failure(httpx.ReadTimeout("slow", request=request)))

    async def test_tomorrow_bundle_reads_temperature_apparent(self) -> None:
        """Tomorrow.io `temperatureApparent` should become normalized feels-like temperature."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/realtime"):
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "time": "2026-05-07T20:00:00Z",
                            "values": {
                                "temperature": 58,
                                "temperatureApparent": 51,
                                "windSpeed": 14,
                                "windGust": 19,
                                "precipitationProbability": 0,
                                "weatherCode": 2100,
                            },
                        }
                    },
                )
            return httpx.Response(200, json={"timelines": {"hourly": []}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            bundle = await fetch_tomorrow_bundle(client, self._location(), api_key="x", hours_ahead=0)
        self.assertEqual(bundle.current.temperature_f, 58)
        self.assertEqual(bundle.current.feels_like_f, 51)
        self.assertEqual(bundle.current.wind_speed_mph, 14)
        self.assertEqual(bundle.current.wind_gust_mph, 19)

    async def test_weatherstack_bundle_reads_feelslike(self) -> None:
        """Weatherstack `feelslike` should become normalized feels-like temperature."""

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "location": {
                            "name": "Montara",
                            "region": "California",
                            "country": "United States",
                            "timezone_id": "America/Los_Angeles",
                            "localtime": "2026-05-07 13:00",
                        },
                        "current": {
                            "temperature": 58,
                            "feelslike": 51,
                            "wind_speed": 14,
                            "wind_gust": 19,
                            "weather_code": 2100,
                            "weather_descriptions": ["Light fog"],
                            "precip": 0,
                        },
                        "forecast": {},
                    },
                )
            )
        ) as client:
            bundle = await fetch_weatherstack_bundle(
                client,
                self._location(),
                api_key="x",
                concise_location_label=lambda *args, **kwargs: "Montara, San Mateo",
                max_forecast_hours=0,
            )
        self.assertEqual(bundle.current.temperature_f, 58)
        self.assertEqual(bundle.current.feels_like_f, 51)
        self.assertEqual(bundle.current.wind_speed_mph, 14)
        self.assertEqual(bundle.current.wind_gust_mph, 19)


if __name__ == "__main__":
    unittest.main()
