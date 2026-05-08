"""Backend smoke tests for the ZIP-only FLUX-static runtime path."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime
from pathlib import Path

from backend_models import LocationRecord, OutfitWeatherContext, WeatherSnapshot
from outfit_logic import (
    SF_ZIP_TO_HOOD,
    TEMPERATURE_BUCKETS,
    display_location_name,
    get_outfit,
    interpret_weather_for_messaging_and_outfit_selection,
    selected_weather_preset_key,
)
from scene_builder import build_scene
from weather_service import WeatherSceneService, concise_location_label, normalize_zip_code, request_country_hint


class BackendRuntimeTests(unittest.TestCase):
    """Keep backend modules aligned with the shipped ZIP-only static runtime."""

    def _snapshot(
        self,
        *,
        query: str,
        temperature_f: float,
        description: str,
        weather_code: int,
        observed_at: datetime,
        precip_probability_pct: int = 0,
        precip_in: float = 0.0,
        snow: bool = False,
        feels_like_f: float | None = None,
        wind_speed_mph: float | None = None,
        wind_gust_mph: float | None = None,
    ) -> WeatherSnapshot:
        """Build a deterministic snapshot for outfit-selection tests."""
        return WeatherSnapshot(
            query=query,
            location_name=f"{query}, San Francisco",
            temperature_f=temperature_f,
            precip_probability_pct=precip_probability_pct,
            description=description,
            precip_in=precip_in,
            weather_code=weather_code,
            snow=snow,
            night=False,
            observed_at=observed_at,
            source="test",
            feels_like_f=feels_like_f,
            wind_speed_mph=wind_speed_mph,
            wind_gust_mph=wind_gust_mph,
        )

    def _selection_for(self, snapshot: WeatherSnapshot) -> tuple[dict[str, str], OutfitWeatherContext, str]:
        """Run the outfit logic for one snapshot."""
        context = interpret_weather_for_messaging_and_outfit_selection(snapshot, None, snapshot.query)
        selected, note = get_outfit(snapshot, context)
        return selected, context, note

    def test_sf_zip_map_contains_requested_labels(self) -> None:
        """Known SF ZIPs should map to stable neighborhood display labels."""
        self.assertEqual(SF_ZIP_TO_HOOD["94110"][0], "Inner Mission, Bernal Heights, San Francisco")
        self.assertEqual(SF_ZIP_TO_HOOD["94113"][0], "Glen Park, San Francisco")
        self.assertEqual(SF_ZIP_TO_HOOD["94122"][0], "Sunset, Inner Sunset, San Francisco")
        self.assertEqual(SF_ZIP_TO_HOOD["94143"][0], "UC San Francisco, San Francisco")
        self.assertEqual(SF_ZIP_TO_HOOD["94158"][0], "Mission Bay, San Francisco")

    def test_normalize_zip_code_uses_default_and_rejects_bad_input(self) -> None:
        """ZIP normalization should keep the API contract brutally simple."""
        self.assertEqual(normalize_zip_code(None, "94110"), "94110")
        self.assertEqual(normalize_zip_code("94122", "94110"), "94122")
        with self.assertRaisesRegex(ValueError, "exactly 5 digits"):
            normalize_zip_code("9411", "94110")
        with self.assertRaisesRegex(ValueError, "exactly 5 digits"):
            normalize_zip_code("9411a", "94110")

    def test_concise_location_label_keeps_sf_zip_names_and_short_provider_names(self) -> None:
        """Location labels should stay compact without losing useful country context."""
        self.assertEqual(
            concise_location_label("San Francisco, California, United States", query="94110"),
            "Inner Mission, Bernal Heights, San Francisco",
        )
        self.assertEqual(concise_location_label("Portland, Oregon, United States", query="97205"), "Portland, Oregon")
        self.assertEqual(concise_location_label("San Jose, California, United States", query="95112"), "San Jose")
        self.assertEqual(concise_location_label("Arcueil, Île-de-France Region, France", query="99999"), "Arcueil, Île-de-France Region")
        self.assertEqual(concise_location_label(None, query="12345"), "12345")

    def test_request_country_hint_prefers_proxy_country_headers(self) -> None:
        """Country hints should come from deployment proxy headers when present."""
        self.assertEqual(request_country_hint({"x-vercel-ip-country": "us"}), "US")
        self.assertEqual(request_country_hint({"cf-ipcountry": "de"}), "DE")
        self.assertIsNone(request_country_hint({"x-vercel-ip-country": "USA"}))
        self.assertIsNone(request_country_hint({}))

    def test_display_location_name_prefers_known_sf_zip(self) -> None:
        """Display labels should come from the SF ZIP map, not raw provider strings."""
        self.assertEqual(
            display_location_name("94122, San Francisco", "94122"),
            "Sunset, Inner Sunset, San Francisco",
        )
        self.assertEqual(
            display_location_name("94110, San Francisco", "94110"),
            "Inner Mission, Bernal Heights, San Francisco",
        )
        self.assertEqual(
            display_location_name("94113, San Francisco", "94113"),
            "Glen Park, San Francisco",
        )
        self.assertEqual(display_location_name("San Francisco", "99999"), "San Francisco")

    def test_temperature_buckets_are_zip_only_sf_centered_ranges(self) -> None:
        """Dry temperature routing should be tightest in the SF core range."""
        self.assertEqual(
            TEMPERATURE_BUCKETS,
            (
                ("0_to_48", float("-inf"), 48, "0_to_48_dry_very_cold"),
                ("48_to_50", 48, 50, "48_to_50_dry_cold"),
                ("50_to_51", 50, 51, "50_to_51_dry_cold_layer"),
                ("51_to_52", 51, 52, "50_to_52_dry_very_cold"),
                ("52_to_53", 52, 53, "51_to_53_dry_cold_layer"),
                ("53_to_54", 53, 54, "53_to_55_dry_cool_layer"),
                ("54_to_55", 54, 55, "54_to_55_dry_layered"),
                ("55_to_56", 55, 56, "55_to_57_dry_black_layer"),
                ("56_to_57", 56, 57, "56_to_57_dry_chunky_cardigan"),
                ("57_to_57_5", 57, 57.5, "57_to_57_5_dry_cool_layer"),
                ("57_5_to_58", 57.5, 58, "57_to_59_dry_cool_layer"),
                ("58_to_59", 58, 59, "59_to_61_dry_sweatsuit_layer"),
                ("59_to_60", 59, 60, "59_to_61_dry_sweatsuit_layer"),
                ("60_to_60_5", 60, 60.5, "60_to_61_dry_layered_beanie"),
                ("60_5_to_61", 60.5, 61, "61_to_62_dry_light_layer"),
                ("61_to_61_5", 61, 61.5, "62_to_62_5_dry_mild_layer"),
                ("61_5_to_62", 61.5, 62, "62_5_to_63_dry_light_layer"),
                ("62_to_62_5", 62, 62.5, "62_to_64_dry_cardigan"),
                ("62_5_to_63", 62.5, 63, "63_to_63_5_dry_jacket_uggs"),
                ("63_to_63_5", 63, 63.5, "64_to_65_dry_light_layer"),
                ("63_5_to_64", 63.5, 64, "65_to_66_dry_light_layer"),
                ("64_to_64_5", 64, 64.5, "66_to_67_dry_mild_layer"),
                ("64_5_to_65", 64.5, 65, "67_to_67_5_dry_zip_hoodie"),
                ("65_to_65_5", 65, 65.5, "67_to_68_dry_warm_light"),
                ("65_5_to_66", 65.5, 66, "67_to_69_dry_warm_light"),
                ("66_to_67", 66, 67, "66_to_67_dry_mild_layer"),
                ("67_to_68", 67, 68, "67_to_67_5_dry_zip_hoodie"),
                ("68_to_69", 68, 69, "67_to_68_dry_warm_light"),
                ("69_to_70", 69, 70, "69_to_71_dry_warm_light"),
                ("70_to_71", 70, 71, "71_to_73_dry_warm"),
                ("71_to_72", 71, 72, "72_5_to_73_dry_warm_clear"),
                ("72_to_73", 72, 73, "73_to_75_dry_warm_clear"),
                ("73_to_74", 73, 74, "74_5_to_76_dry_warm_clear"),
                ("74_to_75", 74, 75, "75_to_78_dry_hot"),
                ("75_to_77", 75, 77, "75_to_78_dry_hot"),
                ("77_to_80", 77, 80, "78_to_80_dry_hot"),
                ("80_to_85", 80, 85, "80_to_85_dry_very_hot"),
                ("85_plus", 85, float("inf"), "85_plus_dry_very_hot"),
            ),
        )

    def test_94110_58_degrees_selects_layered_cool_outfit(self) -> None:
        """Mission ZIP weather around 58F should stay in a layered cool-weather slot."""
        snapshot = self._snapshot(
            query="94110",
            temperature_f=58,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 23, 30, tzinfo=UTC),
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertEqual(context.derived_microclimate_zone, "sunbelt")
        self.assertEqual(context.bucket, "59_to_60")
        self.assertEqual(selected["preset_key"], "59_to_61_dry_sweatsuit_layer")
        self.assertIn("hoodie", note.lower())

    def test_foggy_94122_is_harsher_than_cloudy_94110(self) -> None:
        """Cold fog on the coast should route colder than a slightly warmer sunbelt cloud day."""
        coastal = self._snapshot(
            query="94122",
            temperature_f=51,
            description="Foggy",
            weather_code=2000,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        sunbelt = self._snapshot(
            query="94110",
            temperature_f=53,
            description="Some clouds",
            weather_code=1101,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        coastal_selected, coastal_context, _ = self._selection_for(coastal)
        sunbelt_selected, sunbelt_context, _ = self._selection_for(sunbelt)
        self.assertEqual(coastal_context.derived_microclimate_zone, "coastal")
        self.assertEqual(coastal_context.bucket, "0_to_48")
        self.assertEqual(coastal_selected["preset_key"], "0_to_48_dry_very_cold")
        self.assertEqual(sunbelt_context.derived_microclimate_zone, "sunbelt")
        self.assertEqual(sunbelt_context.bucket, "53_to_54")
        self.assertEqual(sunbelt_selected["preset_key"], "53_to_55_dry_cool_layer")

    def test_sunbelt_zip_adds_one_degree_to_effective_temp(self) -> None:
        """Sunbelt ZIPs should feel one degree lighter than non-SF-neutral ZIPs."""
        neutral = self._snapshot(
            query="99999",
            temperature_f=62,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        sunbelt = self._snapshot(
            query="94110",
            temperature_f=62,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        neutral_selected, neutral_context, _ = self._selection_for(neutral)
        sunbelt_selected, sunbelt_context, _ = self._selection_for(sunbelt)
        self.assertEqual(neutral_context.effective_temp_f, 62)
        self.assertEqual(sunbelt_context.effective_temp_f, 63)
        self.assertEqual(neutral_selected["preset_key"], "62_to_64_dry_cardigan")
        self.assertEqual(sunbelt_selected["preset_key"], "64_to_65_dry_light_layer")

    def test_wet_logic_uses_actual_wet_and_wet_safe_paths(self) -> None:
        """Actual precip and wet-risk paths should route to different generated presets."""
        dry = self._snapshot(
            query="94123",
            temperature_f=60,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        wet = self._snapshot(
            query="94123",
            temperature_f=60,
            description="Drizzle",
            weather_code=4000,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
            precip_probability_pct=45,
            precip_in=0.02,
        )
        dry_selected, dry_context, dry_note = self._selection_for(dry)
        wet_selected, wet_context, wet_note = self._selection_for(wet)
        self.assertEqual(dry_context.rain_level, "none")
        self.assertEqual(wet_context.rain_level, "wet")
        self.assertEqual(dry_selected["preset_key"], "60_to_61_dry_layered_beanie")
        self.assertEqual(wet_selected["preset_key"], "57_to_61_raining_cool")
        self.assertNotIn("umbrella", dry_note.lower())
        self.assertIn("umbrella", wet_note.lower())

    def test_select_hourly_snapshot_uses_nearest_target_hour(self) -> None:
        """Forecast requests should use the closest available hourly reading."""
        service = WeatherSceneService()
        current = self._snapshot(
            query="94110",
            temperature_f=58,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        hourly = [
            self._snapshot(
                query="94110",
                temperature_f=59,
                description="Mostly clear",
                weather_code=1100,
                observed_at=datetime(2026, 5, 7, 21, 50, tzinfo=UTC),
            ),
            self._snapshot(
                query="94110",
                temperature_f=60,
                description="Mostly clear",
                weather_code=1100,
                observed_at=datetime(2026, 5, 7, 22, 5, tzinfo=UTC),
            ),
        ]
        bundle = type("Bundle", (), {"current": current, "hourly": hourly})()
        chosen = service.select_hourly_snapshot(bundle, 2)
        self.assertEqual(chosen.temperature_f, 60)

    def test_low_end_wet_routes_cover_rain_snow_and_wet_risk(self) -> None:
        """Cold wet routing should distinguish rain, snow/wind, and wet-risk reuse."""
        rain = selected_weather_preset_key(
            OutfitWeatherContext(
                effective_temp_f=47.0,
                bucket="test",
                rain_level="wet",
                derived_conditions=frozenset({"wet"}),
                derived_microclimate_zone=None,
                local_hour=12,
                outfit_note="",
            )
        )
        snow_wind = selected_weather_preset_key(
            OutfitWeatherContext(
                effective_temp_f=47.0,
                bucket="test",
                rain_level="wet",
                derived_conditions=frozenset({"snow", "wind", "wet"}),
                derived_microclimate_zone=None,
                local_hour=12,
                outfit_note="",
            )
        )
        wet_risk = selected_weather_preset_key(
            OutfitWeatherContext(
                effective_temp_f=47.0,
                bucket="test",
                rain_level="none",
                derived_conditions=frozenset({"wet"}),
                derived_microclimate_zone=None,
                local_hour=12,
                outfit_note="",
            )
        )
        self.assertEqual(rain, "0_to_48_rainstorm")
        self.assertEqual(snow_wind, "0_to_48_snow_or_windstorm")
        self.assertEqual(wet_risk, "0_to_48_dry_very_cold")

    def test_non_ignored_flux2_images_are_reachable(self) -> None:
        """Every non-ignored generated image should be reachable from backend routing."""
        flux_dir = Path("static/generated/flux2")
        if not flux_dir.exists():
            return

        ignored = {
            "at_home_warm_sunbelt_casual-sweats-and-tee-dresses-test-flux-gen",
            "warm_at_night",
        }
        expected = {path.stem for path in flux_dir.glob("*.png")} - ignored

        reachable = set()
        sample_conditions = (
            ("none", frozenset()),
            ("wet", frozenset({"wet"})),
            ("wet", frozenset({"snow", "wind", "wet"})),
            ("none", frozenset({"wet"})),
        )
        for _bucket, low, high, _key in TEMPERATURE_BUCKETS:
            if low == float("-inf"):
                sample_temps = (40, 47.5)
            elif high == float("inf"):
                sample_temps = (85, 90)
            else:
                sample_temps = (low, (low + high) / 2, high - 0.1)
            for rain_level, conditions in sample_conditions:
                for temp in sample_temps:
                    reachable.add(
                        selected_weather_preset_key(
                            OutfitWeatherContext(
                                effective_temp_f=temp,
                                bucket="test",
                                rain_level=rain_level,
                                derived_conditions=conditions,
                                derived_microclimate_zone=None,
                                local_hour=12,
                                outfit_note="",
                            )
                        )
                    )

        self.assertEqual(sorted(expected - reachable), [])

    def test_only_ignored_flux2_images_are_unreferenced(self) -> None:
        """Only the intentional non-runtime images should stay unreferenced in outfit logic."""
        flux_dir = Path("static/generated/flux2")
        if not flux_dir.exists():
            return
        ignored = {
            "at_home_warm_sunbelt_casual-sweats-and-tee-dresses-test-flux-gen",
            "warm_at_night",
        }
        text = Path("outfit_logic.py").read_text()
        unreferenced = {path.stem for path in flux_dir.glob("*.png") if path.stem not in text}
        self.assertEqual(unreferenced, ignored)

    def test_provider_wind_cools_effective_temp_before_normal_selection(self) -> None:
        """Provider wind should cool effective temp before the normal temp bucket is chosen."""
        snapshot = self._snapshot(
            query="94122",
            temperature_f=61,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 7, 15, 22, 0, tzinfo=UTC),
            wind_speed_mph=14,
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertIn("wind", context.derived_conditions)
        self.assertEqual(selected["preset_key"], "57_to_57_5_dry_cool_layer")
        self.assertNotIn("wind makes", note.lower())

    def test_scene_uses_resolved_zip_label(self) -> None:
        """Scene labels should prefer the resolved ZIP neighborhood label."""
        snapshot = self._snapshot(
            query="94122",
            temperature_f=58,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        location = LocationRecord(
            query="94122",
            display_name="Sunset, Inner Sunset, San Francisco",
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
        scene = build_scene(snapshot, None, mode="current", hours_ahead=0, resolved_location=location)
        self.assertEqual(scene.location_name, "Sunset, Inner Sunset, San Francisco")

    def test_resolve_weather_location_prefers_us_postcode_match(self) -> None:
        """ZIP geocoding should choose a US row whose postcode list contains the ZIP."""
        service = WeatherSceneService()

        class FakeResponse:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return self.payload

        class FakeClient:
            async def get(self, _url: str, *, params: dict[str, object], headers: dict[str, str] | None = None) -> FakeResponse:
                self.last_name = params["name"]
                return FakeResponse(
                    {
                        "results": [
                            {
                                "name": "Arcueil",
                                "country": "France",
                                "country_code": "FR",
                                "latitude": 48.79993,
                                "longitude": 2.33256,
                                "postcodes": ["94110", "94113 CEDEX"],
                            },
                            {
                                "name": "San Francisco",
                                "country": "United States",
                                "country_code": "US",
                                "admin1": "California",
                                "admin2": "San Francisco County",
                                "timezone": "America/Los_Angeles",
                                "latitude": 37.77493,
                                "longitude": -122.41942,
                                "postcodes": ["94110", "94122"],
                            },
                        ]
                    }
                )

        location = asyncio.run(service.resolve_weather_location(FakeClient(), "94110"))
        self.assertEqual(location.country_code, "US")
        self.assertEqual(location.display_name, "Inner Mission, Bernal Heights, San Francisco")

    def test_resolve_weather_location_uses_sf_city_fallback_for_94113(self) -> None:
        """Unresolvable SF ZIPs should fall back to a generic San Francisco geocode."""
        service = WeatherSceneService()

        class FakeResponse:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return self.payload

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[str] = []

            async def get(self, _url: str, *, params: dict[str, object], headers: dict[str, str] | None = None) -> FakeResponse:
                name = str(params.get("name") or params.get("q"))
                self.calls.append(name)
                if name == "94113":
                    return FakeResponse(
                        {
                            "results": [
                                {
                                    "name": "Arcueil",
                                    "country": "France",
                                    "country_code": "FR",
                                    "latitude": 48.79993,
                                    "longitude": 2.33256,
                                    "postcodes": ["94113 CEDEX"],
                                }
                            ]
                        }
                    )
                return FakeResponse(
                    {
                        "results": [
                            {
                                "name": "San Francisco",
                                "country": "United States",
                                "country_code": "US",
                                "admin1": "California",
                                "admin2": "San Francisco County",
                                "timezone": "America/Los_Angeles",
                                "latitude": 37.77493,
                                "longitude": -122.41942,
                                "postcodes": ["94110", "94113", "94122"],
                            }
                        ]
                    }
                )

        client = FakeClient()
        location = asyncio.run(service.resolve_weather_location(client, "94113"))
        self.assertEqual(client.calls, ["94113", "San Francisco, California"])
        self.assertEqual(location.country_code, "US")
        self.assertEqual(location.display_name, "Glen Park, San Francisco")

    def test_resolve_weather_location_prefers_exact_non_us_postcode_match(self) -> None:
        """A non-US exact postcode hit should beat an unrelated first result."""
        service = WeatherSceneService()

        class FakeResponse:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return self.payload

        class FakeClient:
            async def get(self, _url: str, *, params: dict[str, object], headers: dict[str, str] | None = None) -> FakeResponse:
                return FakeResponse(
                    {
                        "results": [
                            {
                                "name": "Arcueil",
                                "country": "France",
                                "country_code": "FR",
                                "latitude": 48.79993,
                                "longitude": 2.33256,
                                "postcodes": ["16999 CEDEX"],
                            },
                            {
                                "name": "Mexico City",
                                "country": "Mexico",
                                "country_code": "MX",
                                "admin1": "Ciudad de México",
                                "latitude": 19.432608,
                                "longitude": -99.133209,
                                "postcodes": ["16999"],
                            },
                        ]
                    }
                )

        location = asyncio.run(service.resolve_weather_location(FakeClient(), "16999"))
        self.assertEqual(location.country_code, "MX")
        self.assertEqual(location.display_name, "Mexico City, Ciudad de México")
        self.assertEqual(location.latitude, 19.432608)
        self.assertEqual(location.longitude, -99.133209)

    def test_resolve_weather_location_berlin_zip_prefers_hinted_country(self) -> None:
        """Ambiguous postcodes should prefer the hinted-country exact match."""
        service = WeatherSceneService()

        class FakeResponse:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return self.payload

        class FakeClient:
            async def get(self, _url: str, *, params: dict[str, object], headers: dict[str, str] | None = None) -> FakeResponse:
                return FakeResponse(
                    {
                        "results": [
                            {
                                "name": "New York City",
                                "country": "United States",
                                "country_code": "US",
                                "admin1": "New York",
                                "latitude": 40.7128,
                                "longitude": -74.0060,
                                "postcodes": ["10115"],
                            },
                            {
                                "name": "Berlin",
                                "country": "Germany",
                                "country_code": "DE",
                                "admin1": "Land Berlin",
                                "latitude": 52.532,
                                "longitude": 13.3849,
                                "postcodes": ["10115"],
                            },
                        ]
                    }
                )

        location = asyncio.run(service.resolve_weather_location(FakeClient(), "10115", country_hint="US"))
        self.assertEqual(location.country_code, "US")
        self.assertEqual(location.display_name, "New York City, New York")
        self.assertEqual(location.latitude, 40.7128)
        self.assertEqual(location.longitude, -74.0060)

        location = asyncio.run(service.resolve_weather_location(FakeClient(), "10115", country_hint="DE"))
        self.assertEqual(location.country_code, "DE")
        self.assertEqual(location.display_name, "Berlin, Land Berlin")
        self.assertEqual(location.latitude, 52.532)
        self.assertEqual(location.longitude, 13.3849)

    def test_resolve_weather_location_uses_nominatim_for_hinted_non_us_gap(self) -> None:
        """If Open-Meteo misses the hinted country, Nominatim fallback should fill the gap."""
        service = WeatherSceneService()

        class FakeResponse:
            def __init__(self, payload: object) -> None:
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> object:
                return self.payload

        class FakeClient:
            async def get(self, url: str, *, params: dict[str, object], headers: dict[str, str] | None = None) -> FakeResponse:
                if "open-meteo" in url:
                    return FakeResponse(
                        {
                            "results": [
                                {
                                    "name": "Angoulême",
                                    "country": "France",
                                    "country_code": "FR",
                                    "latitude": 45.64997,
                                    "longitude": 0.15345,
                                    "postcodes": ["16999 CEDEX 9"],
                                }
                            ]
                        }
                    )
                return FakeResponse(
                    [
                        {
                            "name": "Mexico City",
                            "display_name": "Mexico City, Mexico",
                            "lat": "19.432608",
                            "lon": "-99.133209",
                        }
                    ]
                )

        location = asyncio.run(service.resolve_weather_location(FakeClient(), "16999", country_hint="MX"))
        self.assertEqual(location.country_code, "MX")
        self.assertEqual(location.display_name, "Mexico City, Mexico")
        self.assertAlmostEqual(location.latitude, 19.432608, places=6)
        self.assertAlmostEqual(location.longitude, -99.133209, places=6)

    def test_get_scene_uses_cached_bundle_when_live_fetch_fails(self) -> None:
        """Live provider errors should still produce a stale scene when cache exists."""
        service = WeatherSceneService()
        current = self._snapshot(
            query="94110",
            temperature_f=58,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        location = LocationRecord(
            query="94110",
            display_name="Inner Mission, Bernal Heights, San Francisco",
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
        bundle = type("Bundle", (), {"current": current, "hourly": [], "resolved_location": location})()
        service.weather_bundle_cache["94110"] = bundle
        service.current_scene_cache["94110"] = build_scene(
            current,
            None,
            mode="current",
            hours_ahead=0,
            resolved_location=location,
        )

        async def fail_fetch(_query: str, *, hours_ahead: int):
            raise RuntimeError(f"boom-{hours_ahead}")

        service.fetch_weather_bundle = fail_fetch  # type: ignore[method-assign]
        scene = asyncio.run(service.get_scene(0, "94110"))
        self.assertTrue(scene.stale)
        self.assertEqual(scene.location_name, "Inner Mission, Bernal Heights, San Francisco")
        self.assertTrue(scene.source.endswith("-cache"))

    def test_get_scene_raises_when_live_fetch_fails_without_cache(self) -> None:
        """A hard provider failure should bubble up when nothing cached can save the request."""
        service = WeatherSceneService()

        async def fail_fetch(_query: str, *, hours_ahead: int):
            raise RuntimeError(f"boom-{hours_ahead}")

        service.fetch_weather_bundle = fail_fetch  # type: ignore[method-assign]
        with self.assertRaisesRegex(RuntimeError, "no cached weather exists for ZIP 94110"):
            asyncio.run(service.get_scene(0, "94110"))

    def test_reachable_presets_have_generated_images(self) -> None:
        """Every reachable preset should have a generated FLUX file when private assets exist."""
        reachable = set()
        zones = (None, "coastal", "microclimate_mix", "sunbelt")
        wet_states = ("none", "wet")
        condition_sets = (
            frozenset(),
            frozenset({"cloud"}),
            frozenset({"fog"}),
            frozenset({"wind"}),
            frozenset({"fog", "wind"}),
            frozenset({"wet"}),
            frozenset({"snow", "wind", "wet"}),
        )
        for bucket, low, high, _dry_key in TEMPERATURE_BUCKETS:
            if low == float("-inf"):
                sample_temps = (40, high - 0.1)
            elif high == float("inf"):
                sample_temps = (low, low + 2, 90)
            else:
                sample_temps = (low, (low + high) / 2, high - 0.1)
            for zone in zones:
                for rain_level in wet_states:
                    for conditions in condition_sets:
                        for temp in sample_temps:
                            reachable.add(
                                selected_weather_preset_key(
                                    OutfitWeatherContext(
                                        effective_temp_f=temp,
                                        bucket=bucket,
                                        rain_level=rain_level,
                                        derived_conditions=conditions,
                                        derived_microclimate_zone=zone,
                                        local_hour=12,
                                        outfit_note="",
                                    )
                                )
                            )
        flux_dir = Path("static/generated/flux2")
        if not flux_dir.exists():
            return
        for key in reachable:
            self.assertTrue((flux_dir / f"{key}.png").exists(), key)


if __name__ == "__main__":
    unittest.main()
