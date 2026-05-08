"""Backend smoke tests for the current front-only FLUX-static runtime path."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from backend_models import LocationRecord, OutfitWeatherContext, WeatherSnapshot
from outfit_logic import (
    TEMPERATURE_BUCKETS,
    display_location_name,
    get_outfit,
    interpret_weather_for_messaging_and_outfit_selection,
    selected_weather_preset_key,
)
from scene_builder import build_scene
from weather_service import WeatherSceneService


class BackendRuntimeTests(unittest.TestCase):
    """Keep the backend modules aligned with the shipped FLUX-static path."""

    def _require_private_assets(self) -> None:
        """Skip private-image assertions in the public-safe repo copy."""
        if not Path("static/generated/flux2").exists():
            self.skipTest("private generated outfit images are not included in the public-safe repo")

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
        """Build a deterministic weather snapshot for outfit-logic tests."""
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

    def _selection_for(self, snapshot: WeatherSnapshot) -> tuple[dict[str, str], object]:
        """Run the outfit-logic entry points and return context plus chosen layers."""
        context = interpret_weather_for_messaging_and_outfit_selection(snapshot, None, snapshot.query)
        selected, note = get_outfit(snapshot, context)
        return selected, context, note

    def _scene_snapshot(self) -> WeatherSnapshot:
        """Build an explicit provider-like snapshot for scene-builder tests."""
        return self._snapshot(
            query="94103",
            temperature_f=58,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )

    def test_cool_weather_selects_midlayer_top(self) -> None:
        """Cool SF weather should keep a base top plus hoodie in the selected stack."""
        snapshot = self._snapshot(
            query="Mission",
            temperature_f=56,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertEqual(context.bucket, "temp_56_to_57")
        self.assertEqual(selected["preset_key"], "54_to_56_degree_weather_and_dry")
        self.assertEqual(selected["generated_image_url"], "/static/generated/flux2/54_to_56_degree_weather_and_dry.png")
        self.assertIn("layer", note.lower())

    def test_94110_58_degrees_selects_layered_cool_outfit(self) -> None:
        """Mission zip weather around 58F should not use warm-weather short-sleeve presets."""
        snapshot = self._snapshot(
            query="94110",
            temperature_f=58,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 23, 30, tzinfo=UTC),
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertEqual(context.derived_microclimate_zone, "sunbelt")
        self.assertEqual(context.bucket, "upper_50s")
        self.assertEqual(selected["preset_key"], "cool_weather_near_the_bay_or_coast")
        self.assertIn("jacket", note.lower())

    def test_foggy_cold_coast_does_not_match_cloudy_mission_low_50s(self) -> None:
        """Cold beach fog should use a harsher layer preset than cloudy Mission low-50s."""
        beach = self._snapshot(
            query="Outer Sunset",
            temperature_f=51,
            description="Foggy",
            weather_code=2000,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        mission = self._snapshot(
            query="94110",
            temperature_f=53,
            description="Some clouds",
            weather_code=1101,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        beach_selected, beach_context, _beach_note = self._selection_for(beach)
        mission_selected, mission_context, _mission_note = self._selection_for(mission)

        self.assertEqual(beach_context.derived_microclimate_zone, "coastal")
        self.assertIn("fog", beach_context.derived_conditions)
        self.assertEqual(beach_context.bucket, "temp_51_to_52")
        self.assertEqual(beach_selected["preset_key"], "cold_weather_with_wind_condition")
        self.assertEqual(mission_context.derived_microclimate_zone, "sunbelt")
        self.assertEqual(mission_context.bucket, "temp_53_to_54")
        self.assertEqual(mission_selected["preset_key"], "51_to_54_degree_weather_and_dry")
        self.assertNotEqual(beach_selected["preset_key"], mission_selected["preset_key"])

    def test_63_degree_band_has_its_own_layered_mapping(self) -> None:
        """63F should no longer be swallowed by the broader mild bucket."""
        snapshot = self._snapshot(
            query="Marina",
            temperature_f=63,
            description="Partly cloudy",
            weather_code=1101,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertEqual(context.bucket, "low_mid_60s")
        self.assertEqual(selected["preset_key"], "early_60s_weather_and_dry")
        self.assertIn("cardigan", note.lower())

    def test_common_sf_temperature_boundaries_are_tight_and_ordered(self) -> None:
        """SF's common 52-72F range should be densest near canonical low-60s weather."""
        self.assertEqual(
            TEMPERATURE_BUCKETS,
            (
                ("very_cold", float("-inf"), 48),
                ("cold", 48, 50),
                ("around_50", 50, 51),
                ("temp_51_to_52", 51, 52),
                ("temp_52_to_53", 52, 53),
                ("temp_53_to_54", 53, 54),
                ("temp_54_to_55", 54, 55),
                ("temp_55_to_56", 55, 56),
                ("temp_56_to_57", 56, 57),
                ("upper_50s", 57, 59),
                ("low_60s", 59, 61),
                ("early_60s", 61, 62),
                ("low_mid_60s", 62, 64),
                ("mid_60s", 64, 65),
                ("upper_60s", 65, 67),
                ("near_70", 67, 69),
                ("low_70s", 69, 71),
                ("warm_low_70s", 71, 73),
                ("warm_mid_70s", 73, 76),
                ("hot", 76, 80),
                ("very_hot", 80, float("inf")),
            ),
        )

    def test_reachable_daytime_presets_have_generated_images(self) -> None:
        """Every reachable provider-data preset should have one generated FLUX file."""
        reachable = set()
        zones = (None, "coastal", "mixed_microclimate", "sunbelt")
        rain_levels = ("none", "drizzle", "rain", "storm")
        condition_sets = (
            frozenset(),
            frozenset({"cloud"}),
            frozenset({"fog"}),
            frozenset({"wind"}),
            frozenset({"fog", "wind"}),
            frozenset({"wet"}),
        )
        for bucket, low, high in TEMPERATURE_BUCKETS:
            if low == float("-inf"):
                sample_temps = (40, high - 0.1)
            elif high == float("inf"):
                sample_temps = (low, low + 2, 90)
            else:
                width = high - low
                sample_temps = (low, low + width * 0.25, low + width * 0.5, low + width * 0.75, high - 0.1)
            for zone in zones:
                for rain_level in rain_levels:
                    for conditions in condition_sets:
                        for temp in sample_temps:
                            context = OutfitWeatherContext(
                                effective_temp_f=temp,
                                bucket=bucket,
                                rain_level=rain_level,
                                derived_conditions=conditions,
                                derived_microclimate_zone=zone,
                                local_hour=12,
                                outfit_note="",
                            )
                            reachable.add(selected_weather_preset_key(context))
        self.assertGreaterEqual(len(reachable), 30)
        flux_dir = Path("static/generated/flux2")
        if not flux_dir.exists():
            return
        ignored = {
            "at_home_warm_sunbelt_casual-sweats-and-tee-dresses-test-flux-gen",
            "cold_dry",
            "warm_weather_at_night",
        }
        deployable_image_keys = {path.stem for path in flux_dir.glob("*.png") if path.stem not in ignored}
        self.assertEqual(deployable_image_keys, reachable)
        for key in reachable:
            self.assertGreater((flux_dir / f"{key}.png").stat().st_size, 0, key)

    def test_microclimate_zone_does_not_change_provider_based_preset(self) -> None:
        """Microclimate is UI messaging only; real temp/rain/fog/wind choose the outfit."""
        keys = {
            selected_weather_preset_key(
                OutfitWeatherContext(
                    effective_temp_f=63,
                    bucket="low_mid_60s",
                    rain_level="none",
                    derived_conditions=frozenset(),
                    derived_microclimate_zone=zone,
                    local_hour=12,
                    outfit_note="",
                )
            )
            for zone in (None, "coastal", "mixed_microclimate", "sunbelt")
        }
        self.assertEqual(keys, {"early_60s_weather_and_dry"})

    def test_rain_and_snow_edges_choose_coarse_safe_presets(self) -> None:
        """Rare wet/snow branches should fail safe into warm outerwear, not light dry looks."""
        snow = self._snapshot(
            query="94110",
            temperature_f=40,
            description="Snow",
            weather_code=5000,
            observed_at=datetime(2026, 1, 7, 18, 0, tzinfo=UTC),
            precip_in=0.2,
            snow=True,
        )
        storm = self._snapshot(
            query="94110",
            temperature_f=54,
            description="Storm",
            weather_code=8000,
            observed_at=datetime(2026, 1, 7, 18, 0, tzinfo=UTC),
            precip_in=0.2,
        )
        snow_context = interpret_weather_for_messaging_and_outfit_selection(snow, None, snow.query)
        storm_context = interpret_weather_for_messaging_and_outfit_selection(storm, None, storm.query)
        self.assertEqual(selected_weather_preset_key(snow_context), "very_cold_weather_and_wet_snow_or_windstorm")
        self.assertEqual(selected_weather_preset_key(storm_context), "cold_weather_and_wet_storming")

    def test_very_cold_plain_rainstorm_stays_separate_from_snow_or_windstorm(self) -> None:
        """The coldest brr preset should require snow, wind, or fog on top of very cold storm weather."""
        plain_storm = self._snapshot(
            query="94110",
            temperature_f=40,
            description="Heavy rain",
            weather_code=4201,
            observed_at=datetime(2026, 1, 7, 18, 0, tzinfo=UTC),
            precip_in=0.2,
        )
        windy_storm = self._snapshot(
            query="94110",
            temperature_f=40,
            description="Windy storm",
            weather_code=3001,
            observed_at=datetime(2026, 1, 7, 18, 0, tzinfo=UTC),
            precip_in=0.2,
        )
        plain_context = interpret_weather_for_messaging_and_outfit_selection(plain_storm, None, plain_storm.query)
        windy_context = interpret_weather_for_messaging_and_outfit_selection(windy_storm, None, windy_storm.query)
        self.assertEqual(selected_weather_preset_key(plain_context), "cold_weather_and_wet_rainstorm")
        self.assertEqual(selected_weather_preset_key(windy_context), "very_cold_weather_and_wet_snow_or_windstorm")

    def test_50_degree_dry_slot_uses_cold_wind_image_without_broad_override(self) -> None:
        """A slim 50-51F dry slot should surface the puffer image without taking over low 50s."""
        slot = self._snapshot(
            query="Mission",
            temperature_f=50.5,
            description="Clear",
            weather_code=1000,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        lower = self._snapshot(
            query="Mission",
            temperature_f=49.5,
            description="Clear",
            weather_code=1000,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        upper = self._snapshot(
            query="Mission",
            temperature_f=51.5,
            description="Clear",
            weather_code=1000,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        self.assertEqual(self._selection_for(slot)[0]["preset_key"], "cold_weather_with_wind_condition")
        self.assertEqual(self._selection_for(lower)[0]["preset_key"], "cold_weather_and_dry")
        self.assertEqual(self._selection_for(upper)[0]["preset_key"], "51_to_54_degree_weather_and_dry")

    def test_50_degree_windy_slot_uses_new_wind_image_without_broad_override(self) -> None:
        """The new windy image should only take the slim 50-51F fog/wind slice."""
        slot = self._snapshot(
            query="Mission",
            temperature_f=50.5,
            description="Windy",
            weather_code=3001,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        lower = self._snapshot(
            query="Mission",
            temperature_f=49.5,
            description="Windy",
            weather_code=3001,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        upper = self._snapshot(
            query="Mission",
            temperature_f=51.5,
            description="Windy",
            weather_code=3001,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        self.assertEqual(self._selection_for(slot)[0]["preset_key"], "50_to_51_degree_weather_with_wind_condition")
        self.assertEqual(self._selection_for(lower)[0]["preset_key"], "cold_weather_with_wind_condition")
        self.assertEqual(self._selection_for(upper)[0]["preset_key"], "cold_weather_with_wind_condition")

    def test_50_degree_dry_high_precipitation_uses_umbrella_slot_only(self) -> None:
        """High precip probability should use the umbrella image only when dry weather displays as 50F."""
        slot = self._snapshot(
            query="Mission",
            temperature_f=50.4,
            description="Cloudy",
            weather_code=1101,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
            precip_probability_pct=45,
        )
        lower = self._snapshot(
            query="Mission",
            temperature_f=49.5,
            description="Cloudy",
            weather_code=1101,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
            precip_probability_pct=45,
        )
        upper = self._snapshot(
            query="Mission",
            temperature_f=50.5,
            description="Cloudy",
            weather_code=1101,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
            precip_probability_pct=45,
        )
        active_rain = self._snapshot(
            query="Mission",
            temperature_f=50.4,
            description="Rain",
            weather_code=4200,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
            precip_probability_pct=85,
            precip_in=0.06,
        )
        self.assertEqual(self._selection_for(slot)[0]["preset_key"], "50_to_51_degree_weather_dry_high_precipitation")
        self.assertEqual(self._selection_for(lower)[0]["preset_key"], "cold_weather_and_dry")
        self.assertEqual(self._selection_for(upper)[0]["preset_key"], "cold_weather_with_wind_condition")
        self.assertEqual(self._selection_for(active_rain)[0]["preset_key"], "cold_weather_and_wet_raining")

    def test_dry_cold_boundary_presets_stay_distinct(self) -> None:
        """Cold dry boundary samples should not accidentally collapse into one preset."""
        samples = {
            47.5: "very_cold_weather_and_dry",
            49.5: "cold_weather_and_dry",
            50.5: "cold_weather_with_wind_condition",
            51.5: "51_to_54_degree_weather_and_dry",
            52.5: "51_to_54_degree_weather_and_dry",
            53.5: "51_to_54_degree_weather_and_dry",
            54.5: "54_to_56_degree_weather_and_dry",
            55.5: "54_to_56_degree_weather_and_dry",
            56.5: "54_to_56_degree_weather_and_dry",
            58.0: "cool_weather_near_the_bay_or_coast",
            61.5: "mild_weather_in_a_warm_neighborhood",
            63.0: "early_60s_weather_and_dry",
            64.5: "mild_weather_near_the_bay",
        }
        for temp, expected_key in samples.items():
            with self.subTest(temp=temp):
                snapshot = self._snapshot(
                    query="Mission",
                    temperature_f=temp,
                    description="Clear",
                    weather_code=1000,
                    observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
                )
                self.assertEqual(self._selection_for(snapshot)[0]["preset_key"], expected_key)

    def test_hot_mission_day_selects_tank_and_jeans(self) -> None:
        """Warm east-side late-summer weather should collapse to the lightest shipped base look."""
        snapshot = self._snapshot(
            query="Mission",
            temperature_f=76,
            description="Clear, sunny",
            weather_code=1000,
            observed_at=datetime(2026, 8, 20, 21, 0, tzinfo=UTC),
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertEqual(context.bucket, "hot")
        self.assertEqual(selected["preset_key"], "hot_weather_near_the_coast_or_bay")
        self.assertIn("hot", note.lower())

    def test_outer_sunset_marine_summer_uses_provider_conditions_only(self) -> None:
        """Microclimate should not invent fog/wind when provider data says clear."""
        snapshot = self._snapshot(
            query="Outer Sunset",
            temperature_f=61,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 7, 15, 22, 0, tzinfo=UTC),
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertEqual(context.derived_microclimate_zone, "coastal")
        self.assertNotIn("fog", context.derived_conditions)
        self.assertNotIn("wind", context.derived_conditions)
        self.assertEqual(context.bucket, "early_60s")
        self.assertEqual(selected["preset_key"], "mild_weather_in_a_warm_neighborhood")

    def test_provider_wind_drives_wind_specific_outfit(self) -> None:
        """Wind-specific outfits should come from provider wind data, not zone guesses."""
        snapshot = self._snapshot(
            query="Outer Sunset",
            temperature_f=61,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 7, 15, 22, 0, tzinfo=UTC),
            wind_speed_mph=14,
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertIn("wind", context.derived_conditions)
        self.assertEqual(selected["preset_key"], "mild_weather_near_the_coast_with_wind_condition")
        self.assertNotIn("wind makes", note.lower())

    def test_scene_compacts_provider_wind_into_weather_line_label(self) -> None:
        """Provider wind should surface as a compact weather-line label, not outfit-note prose."""
        scene = build_scene(
            self._snapshot(
                query="Outer Sunset",
                temperature_f=61,
                description="Mostly clear",
                weather_code=1100,
                observed_at=datetime(2026, 7, 15, 22, 0, tzinfo=UTC),
                wind_speed_mph=14,
            ),
            None,
            mode="current",
            hours_ahead=0,
        )
        self.assertEqual(scene.wind_label, "breezy")

    def test_drizzle_day_still_layers(self) -> None:
        """Drizzle should force a layered outfit even on a brighter-looking SF day."""
        snapshot = self._snapshot(
            query="Marina",
            temperature_f=60,
            description="Drizzle",
            weather_code=4000,
            observed_at=datetime(2026, 4, 10, 20, 0, tzinfo=UTC),
            precip_probability_pct=45,
            precip_in=0.02,
        )
        selected, context, note = self._selection_for(snapshot)
        self.assertEqual(context.rain_level, "drizzle")
        self.assertIn("wet", context.derived_conditions)
        self.assertEqual(selected["preset_key"], "cool_weather_and_wet_windy_drizzle")
        self.assertIn("drizzle", note.lower())

    def test_sleep_window_away_from_home_still_uses_weather_outfit(self) -> None:
        """Nighttime away from home should not collapse every location into pajamas."""
        snapshot = self._snapshot(
            query="Mission",
            temperature_f=58,
            description="Clear",
            weather_code=1000,
            observed_at=datetime(2026, 5, 7, 6, 30, tzinfo=UTC),
        )
        context = interpret_weather_for_messaging_and_outfit_selection(snapshot, None, snapshot.query)
        selected, _note = get_outfit(snapshot, context)
        self.assertEqual(selected["preset_key"], "cool_weather_near_the_bay_or_coast")

    def test_9pm_forecast_still_uses_weather_outfit_away_from_home(self) -> None:
        """A 9pm forecast away from home should still reflect weather/location differences."""
        snapshot = self._snapshot(
            query="Mission",
            temperature_f=70,
            description="Clear",
            weather_code=1000,
            observed_at=datetime(2026, 5, 8, 4, 30, tzinfo=UTC),
        )
        context = interpret_weather_for_messaging_and_outfit_selection(snapshot, None, snapshot.query)
        selected, _note = get_outfit(snapshot, context)
        self.assertEqual(context.local_hour, 21)
        self.assertEqual(selected["preset_key"], "warm_clear_weather_near_the_bay")

    def test_72_degree_clear_weather_does_not_select_sundress(self) -> None:
        """72F clear weather should stay casual-layered, not jump to a sundress preset."""
        for query in ("San Francisco", "94110"):
            with self.subTest(query=query):
                snapshot = self._snapshot(
                    query=query,
                    temperature_f=72,
                    description="Warm and clear",
                    weather_code=1000,
                    observed_at=datetime(2026, 5, 7, 21, 0, tzinfo=UTC),
                )
                selected, context, _note = self._selection_for(snapshot)
                self.assertEqual(context.bucket, "warm_low_70s")
                self.assertEqual(selected["preset_key"], "warm_weather_in_a_warm_neighborhood")

    def test_feels_like_temperature_drives_outfit_bucket_when_present(self) -> None:
        """Outfit selection should use apparent temperature without changing displayed temperature."""
        snapshot = self._snapshot(
            query="Montara",
            temperature_f=58,
            feels_like_f=51,
            description="Light fog",
            weather_code=2100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        selected, context, _note = self._selection_for(snapshot)
        self.assertEqual(snapshot.temperature_f, 58)
        self.assertEqual(context.effective_temp_f, 51)
        self.assertEqual(context.bucket, "temp_51_to_52")
        self.assertEqual(selected["preset_key"], "cold_weather_with_wind_condition")

    def test_displayed_temperature_can_differ_from_feels_like_outfit_route(self) -> None:
        """Displayed 52F should still route by provider feels-like when apparent temp is colder."""
        snapshot = self._snapshot(
            query="94110",
            temperature_f=52.4,
            feels_like_f=51.4,
            description="Clear",
            weather_code=1000,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        selected, context, _note = self._selection_for(snapshot)
        self.assertEqual(round(snapshot.temperature_f), 52)
        self.assertEqual(context.bucket, "temp_51_to_52")
        self.assertEqual(selected["preset_key"], "51_to_54_degree_weather_and_dry")

    def test_scene_uses_static_flux_image_without_runtime_layers(self) -> None:
        """The frontend should receive one generated base image and no runtime layers."""
        scene = build_scene(self._scene_snapshot(), None, mode="current", hours_ahead=0)
        self.assertEqual(scene.render_mode, "flux_static")
        self.assertEqual(scene.base_image_url, scene.generated_image_url)
        self.assertEqual(scene.layers, [])

    def test_scene_is_fixed_front_pose(self) -> None:
        """Scene assembly should always resolve to the shipped front pose."""
        scene = build_scene(self._scene_snapshot(), None, mode="current", hours_ahead=0)
        self.assertEqual(scene.subject_pose, "front")
        self.assertEqual(scene.render_mode, "flux_static")
        self.assertTrue(scene.generated_image_url)

    def test_location_resolution_keeps_neighborhood_label(self) -> None:
        """SF neighborhood queries should remain neighborhood-first when resolved."""
        service = WeatherSceneService()
        label = service.location_from_geo(
            "Mission",
            {
                "latitude": 37.7599,
                "longitude": -122.4148,
                "name": "San Francisco",
                "admin2": "San Francisco County",
                "admin1": "California",
                "country": "United States",
                "country_code": "US",
                "timezone": "America/Los_Angeles",
            },
        ).display_name
        self.assertEqual(label, "Mission, San Francisco")

    def test_sf_zip_display_names_resolve_to_neighborhoods(self) -> None:
        """Known SF ZIP codes should display useful neighborhood labels, not raw ZIP labels."""
        self.assertEqual(display_location_name("94122, San Francisco", "94122"), "Sunset District, San Francisco")
        self.assertEqual(display_location_name("94122, San Francisco", ""), "Sunset District, San Francisco")
        self.assertEqual(display_location_name("94118, San Francisco", "94118"), "Richmond District, San Francisco")
        self.assertEqual(display_location_name("94110, San Francisco", "94110"), "Mission District, San Francisco")

    def test_scene_uses_resolved_zip_for_neighborhood_label(self) -> None:
        """Provider labels like `San Francisco` should still display the user's SF ZIP neighborhood."""
        snapshot = self._snapshot(
            query="San Francisco",
            temperature_f=58,
            description="Mostly clear",
            weather_code=1100,
            observed_at=datetime(2026, 5, 7, 20, 0, tzinfo=UTC),
        )
        location = LocationRecord(
            query="94122",
            display_name="94122, San Francisco",
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
        self.assertEqual(scene.location_name, "Sunset District, San Francisco")


if __name__ == "__main__":
    unittest.main()
