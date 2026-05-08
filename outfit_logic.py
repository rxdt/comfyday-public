"""San Francisco weather interpretation and outfit-selection logic."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from backend_models import LocationRecord, OutfitWeatherContext, WeatherSnapshot


SF_ZIP_TO_HOOD: dict[str, tuple[str, str]] = {
    "94110": ("Mission District, San Francisco", "sunbelt"),
    "sunset": ("Sunset District, San Francisco", "coastal"),
    "richmond": ("Richmond District, San Francisco", "coastal"),
    "outer sunset": ("Outer Sunset, San Francisco", "coastal"),
    "inner sunset": ("Inner Sunset, San Francisco", "coastal"),
    "outer richmond": ("Outer Richmond, San Francisco", "coastal"),
    "inner richmond": ("Inner Richmond, San Francisco", "coastal"),
    "presidio": ("Presidio, San Francisco", "coastal"),
    "marina": ("Marina District, San Francisco", "mixed_microclimate"),
    "cow hollow": ("Cow Hollow, San Francisco", "mixed_microclimate"),
    "haight": ("Haight-Ashbury, San Francisco", "mixed_microclimate"),
    "lower haight": ("Lower Haight, San Francisco", "mixed_microclimate"),
    "nopa": ("NoPa, San Francisco", "mixed_microclimate"),
    "pac heights": ("Pacific Heights, San Francisco", "mixed_microclimate"),
    "mission": ("Mission District, San Francisco", "sunbelt"),
    "mission district": ("Mission District, San Francisco", "sunbelt"),
    "mission bay": ("Mission Bay, San Francisco", "sunbelt"),
    "outer mission": ("Outer Mission, San Francisco", "sunbelt"),
    "soma": ("SOMA, San Francisco", "sunbelt"),
    "dogpatch": ("Dogpatch, San Francisco", "sunbelt"),
    "potrero": ("Potrero Hill, San Francisco", "sunbelt"),
    "noe valley": ("Noe Valley, San Francisco", "sunbelt"),
    "fidi": ("Financial District, San Francisco", "sunbelt"),
}
SF_TIMEZONE = ZoneInfo("America/Los_Angeles")
TEMPERATURE_BUCKETS = (
    ("very_cold", float("-inf"), 48),
    ("cold", 48, 51),
    ("low_50s", 51, 54),
    ("mid_50s", 54, 57),
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
)
RAIN_LEVELS = (("none", 0.0, 0.0), ("drizzle", 0.0, 0.03), ("rain", 0.03, 0.15), ("storm", 0.15, float("inf")))
RAW_DESCRIPTION_TO_DERIVED_CONDITION = {
    "fog": ("fog", "mist", "marine layer"),
    "wind": ("wind", "gust", "breez"),
    "cloud": ("cloud", "overcast"),
    "wet": ("drizzle", "rain", "shower", "storm"),
}
WEATHER_CODE_TO_DERIVED_CONDITION = {
    2000: "fog",
    2100: "fog",
    3000: "wind",
    3001: "wind",
    3002: "wind",
    4000: "wet",
    4001: "wet",
    4200: "wet",
    4201: "wet",
    5000: "snow",
    5001: "snow",
    5100: "snow",
    5101: "snow",
    8000: "wet",
}
BUCKET_NOTES = {
    "very_cold": "Very cold; use the warmest outfit you have",
    "cold": "Cold; don't forget to layer up",
    "low_50s": "Low 50s; use a real layer",
    "mid_50s": "Mid-50s; dress like cool weather with a backup layer",
    "upper_50s": "Upper 50s; a hoodie, cardigan, or light jacket is the safe default",
    "low_60s": "Low 60s; keep a light jacket or cardigan on",
    "early_60s": "Early 60s; light layers still work best",
    "low_mid_60s": "Low-mid 60s; a very light cardigan works.",
    "mid_60s": "Mid-60s; use a real light layer",
    "upper_60s": "Upper 60s; use a removable light layer",
    "near_70": "Near 70; short sleeves can work, but keep SF shifts in mind",
    "low_70s": "Low 70s; lighter clothing works unless fog, rain, or wind happens soon",
    "warm_low_70s": "Low 70s; lighter clothing works unless fog, rain, or wind happens soon",
    "warm_mid_70s": "Mid-70s; dress light",
    "hot": "Hot; use the lightest warm-weather outfit.",
    "very_hot": "Very hot; prioritize breathable clothing and water.",
}
WEATHER_OUTFIT_PRESETS = {
    "very_hot_weather_in_a_warm_neighborhood": [
        "static/assets/prepared/approved/tank_top_teal.png",
        "static/assets/prepared/approved/shorts_blue_sweat_mini.png",
        "static/assets/prepared/approved/accessory_leather_handbag.png",
        "static/assets/prepared/approved/accessory_stanley_cup.png",
    ],
    "very_hot_weather_near_the_coast_or_bay": [
        "static/assets/prepared/approved/dress_long_white_blue_flower.png",
        "static/assets/prepared/approved/accessory_birkenstock_sandals.png",
        "static/assets/prepared/approved/accessory_pink_handbag.png",
    ],
    "hot_weather_in_a_warm_neighborhood": [
        "static/assets/prepared/approved/tank_top_grey_camisole.png",
        "static/assets/prepared/approved/jean_shorts_summer_mini.png",
        "static/assets/prepared/approved/accessory_leather_handbag.png",
        "static/assets/prepared/approved/accessory_stanley_cup.png",
    ],
    "hot_weather_near_the_coast_or_bay": [
        "static/assets/prepared/approved/tank_top_spaghetti_strap_blue_baby_doll.png",
        "static/assets/prepared/approved/short_jean_mini_skirt.png",
        "static/assets/prepared/approved/accessory_pink_handbag.png",
    ],
    "warm_weather_in_a_warm_neighborhood": [
        "static/assets/prepared/approved/blue_off_shoulder_top.png",
        "static/assets/prepared/approved/jeans_light_straight.png",
        "static/assets/prepared/approved/accessory_stanley_cup.png",
    ],
    "warm_weather_near_the_bay": [
        "static/assets/prepared/approved/t_shirt_fitted_yellow_striped.png",
        "static/assets/prepared/approved/jeans_pale_fitted_waist_baggy.png",
    ],
    "mild_weather_in_a_warm_neighborhood": [
        "static/assets/prepared/approved/tank_top_red.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/jeans_loose_with_folded_hems.png",
        "static/assets/prepared/approved/accessory_leather_handbag.png",
    ],
    "early_60s_weather_and_dry": [
        "static/assets/prepared/approved/top_vneck_white_brandy_melville.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/jeans_oversized_black_barrel_leg.png",
        "static/assets/prepared/approved/accessory_samba_sneakers.png",
    ],
    "mild_weather_near_the_bay": [
        "static/assets/prepared/approved/blue_button_up_blouse_brandy_melville.png",
        "static/assets/prepared/approved/jeans_light_straight.png",
        "static/assets/prepared/approved/accessory_pink_handbag.png",
    ],
    "mild_weather_near_the_coast_with_wind_condition": [
        "static/assets/prepared/approved/tank_top_red.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/jeans_light_straight.png",
    ],
    "mild_weather_near_the_coast_with_fog_condition": [
        "static/assets/prepared/approved/hoodie_pullover_plain_white.png",
        "static/assets/prepared/approved/jeans_loose_with_folded_hems.png",
        "static/assets/prepared/approved/accessory_pink_handbag.png",
    ],
    "mild_weather_near_the_bay_with_wind_condition": [
        "static/assets/prepared/approved/top_polka_dot_yellow_off_shoulder.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/jeans_long_loose_shorts_uo.png",
        "static/assets/prepared/approved/accessory_black_school_backpack.png",
    ],
    "cool_weather_with_fog_or_wind_condition": [
        "static/assets/prepared/approved/t_shirt_fitted_yellow_striped.png",
        "static/assets/prepared/approved/hoodie_pullover_plain_white.png",
        "static/assets/prepared/approved/jacket_fur_brown.png",
        "static/assets/prepared/approved/sweatpants_red.png",
    ],
    "cool_weather_near_the_bay_or_coast": [
        "static/assets/prepared/approved/blue_button_up_blouse_brandy_melville.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/jeans_loose_with_folded_hems.png",
    ],
    "cold_weather_and_dry": [
        "static/assets/prepared/approved/grey_long_sleeve_top_fitted.png",
        "static/assets/prepared/approved/jeans_oversized_black_barrel_leg.png",
        "static/assets/prepared/approved/accessory_pink_beanie_uo.jpg",
        "static/assets/prepared/approved/accessory_folded_polka_dot_umbrella.png",
    ],
    "54_to_56_degree_weather_and_dry": [
        "static/assets/prepared/approved/casual_sweats_and_tee.png",
        "static/assets/prepared/approved/grey_long_sleeve_top_fitted.png",
        "static/assets/prepared/approved/accessory_pink_beanie_uo.jpg",
    ],
    "cold_weather_with_wind_condition": [
        "static/assets/prepared/approved/jacket_white_puffer_fitted_waist.png",
        "static/assets/prepared/approved/jeans_uo_camo_baggy_pants.png",
        "static/assets/prepared/approved/accessory_pink_beanie_uo.jpg",
    ],
    "very_cold_weather_and_dry": [
        "static/assets/prepared/approved/jacket_white_puffer_fitted_waist.png",
        "static/assets/prepared/approved/jeans_uo_camo_baggy_pants.png",
        "static/assets/prepared/approved/accessory_dark_blue_beanie.png",
        "static/assets/prepared/approved/accessory_black_school_backpack.png",
    ],
    "very_cold_weather_with_wind_condition": [
        "static/assets/prepared/approved/grey_long_sleeve_top_fitted.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/jacket_fur_brown.png",
        "static/assets/prepared/approved/jeans_oversized_black_barrel_leg.png",
        "static/assets/prepared/approved/accessory_dark_blue_beanie.png",
    ],
    "mild_weather_and_wet_raining": [
        "static/assets/prepared/approved/blue_off_shoulder_top.png",
        "static/assets/prepared/approved/hoodie_pullover_plain_white.png",
        "static/assets/prepared/approved/long_rain_jacket_outerwear.png",
        "static/assets/prepared/approved/jeans_light_straight.png",
        "static/assets/prepared/approved/accessory_polka_dot_black_umbrella.png",
    ],
    "cold_weather_and_wet_raining": [
        "static/assets/prepared/approved/grey_long_sleeve_top_fitted.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/north_face_puffy_vest.png",
        "static/assets/prepared/approved/jeans_uo_camo_baggy_pants.png",
        "static/assets/prepared/approved/accessory_polka_dot_black_umbrella.png",
    ],
    "mild_weather_and_wet_drizzling": [
        "static/assets/prepared/approved/blue_off_shoulder_top.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/long_rain_jacket_outerwear.png",
        "static/assets/prepared/approved/jeans_loose_with_folded_hems.png",
        "static/assets/prepared/approved/accessory_folded_polka_dot_umbrella.png",
    ],
    "cool_weather_and_wet_windy_drizzle": [
        "static/assets/prepared/approved/t_shirt_fitted_yellow_striped.png",
        "static/assets/prepared/approved/hoodie_pullover_plain_white.png",
        "static/assets/prepared/approved/north_face_puffy_vest.png",
        "static/assets/prepared/approved/sweatpants_red.png",
        "static/assets/prepared/approved/accessory_ugg_mini_boots.png",
    ],
    "warm_weather_and_wet_raining": [
        "static/assets/prepared/approved/blue_button_up_blouse_brandy_melville.png",
        "static/assets/prepared/approved/hoodie_pullover_plain_white.png",
        "static/assets/prepared/approved/long_rain_jacket_outerwear.png",
        "static/assets/prepared/approved/jeans_pale_fitted_waist_baggy.png",
        "static/assets/prepared/approved/accessory_polka_dot_black_umbrella.png",
    ],
    "cool_weather_and_wet_raining": [
        "static/assets/prepared/approved/grey_long_sleeve_top_fitted.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/jacket_puffer_with_tan_undershirt.png",
        "static/assets/prepared/approved/jeans_oversized_black_barrel_leg.png",
        "static/assets/prepared/approved/accessory_polka_dot_black_umbrella.png",
    ],
    "cold_weather_and_wet_storming": [
        "static/assets/prepared/approved/t_shirt_fitted_yellow_striped.png",
        "static/assets/prepared/approved/hoodie_pullover_plain_white.png",
        "static/assets/prepared/approved/jacket_puffer_with_tan_undershirt.png",
        "static/assets/prepared/approved/jeans_uo_camo_baggy_pants.png",
        "static/assets/prepared/approved/accessory_open_black_umbrella.png",
    ],
    "cold_weather_and_wet_rainstorm": [
        "static/assets/prepared/approved/grey_long_sleeve_top_fitted.png",
        "static/assets/prepared/approved/white_zip_up_cardigan_brandy.png",
        "static/assets/prepared/approved/jacket_puffer_with_tan_undershirt.png",
        "static/assets/prepared/approved/jeans_oversized_black_barrel_leg.png",
        "static/assets/prepared/approved/accessory_open_black_umbrella.png",
    ],
    "warm_clear_weather_in_a_warm_neighborhood": [
        "static/assets/prepared/approved/dress_white_strapless.png",
        "static/assets/prepared/approved/accessory_leather_handbag.png",
    ],
    "warm_clear_weather_near_the_bay": [
        "static/assets/prepared/approved/dress_red_long_with_slit.png",
        "static/assets/prepared/approved/accessory_pink_handbag.png",
    ],
    "warm_clear_weather_near_the_coast": [
        "static/assets/prepared/approved/dress_long_pale_yellow_red_flower.png",
        "static/assets/prepared/approved/accessory_pink_handbag.png",
    ],
    "warm_light_weather_in_a_warm_neighborhood": [
        "static/assets/prepared/approved/tank_top_red.png",
        "static/assets/prepared/approved/skirt_white_flowy_knee_length.png",
        "static/assets/prepared/approved/accessory_leather_handbag.png",
        "static/assets/prepared/approved/accessory_stanley_cup.png",
    ],
    "warm_light_weather_near_the_bay": [
        "static/assets/prepared/approved/tank_top_light_blue_flower_pattern.png",
        "static/assets/prepared/approved/jeans_long_loose_shorts_uo.png",
        "static/assets/prepared/approved/accessory_pink_handbag.png",
    ],
    "warm_light_weather_near_the_coast": [
        "static/assets/prepared/approved/top_polka_dot_yellow_off_shoulder.png",
        "static/assets/prepared/approved/jeans_light_straight.png",
    ],
    "warm_clear_light_weather_in_a_warm_neighborhood": [
        "static/assets/prepared/approved/dress_strapless_polka_dot.png",
        "static/assets/prepared/approved/accessory_leather_handbag.png",
        "static/assets/prepared/approved/accessory_stanley_cup.png",
    ],
    "warm_clear_light_weather_near_the_bay": [
        "static/assets/prepared/approved/dress_tan_patterned_sheath.png",
        "static/assets/prepared/approved/accessory_pink_handbag.png",
    ],
}


def selected_weather_preset_key(context: OutfitWeatherContext) -> str:
    """Map interpreted weather signals to one generated outfit image key."""
    bucket = context.bucket
    rain_level = context.rain_level
    conditions = context.derived_conditions
    temp = context.effective_temp_f

    if rain_level == "storm":
        return (
            "cold_weather_and_wet_rainstorm"
            if bucket == "very_cold"
            else "cold_weather_and_wet_storming"
        )
    if rain_level == "rain":
        if bucket in {"very_cold", "cold", "low_50s", "mid_50s"}:
            return "cold_weather_and_wet_raining"
        if bucket in {"upper_50s", "low_60s"}:
            return "cool_weather_and_wet_raining"
        return (
            "warm_weather_and_wet_raining"
            if bucket in {"low_70s", "warm_low_70s", "warm_mid_70s", "hot", "very_hot"}
            else "mild_weather_and_wet_raining"
        )
    if rain_level == "drizzle":
        return (
            "cool_weather_and_wet_windy_drizzle"
            if bucket in {"very_cold", "cold", "low_50s", "mid_50s", "upper_50s", "low_60s"}
            else "mild_weather_and_wet_drizzling"
        )
    if bucket == "very_hot":
        return "very_hot_weather_near_the_coast_or_bay" if temp < 85 else "very_hot_weather_in_a_warm_neighborhood"
    if bucket == "hot":
        return "hot_weather_near_the_coast_or_bay" if temp < 78 else "hot_weather_in_a_warm_neighborhood"
    if bucket == "warm_mid_70s":
        return (
            "warm_clear_light_weather_near_the_bay"
            if temp < 74.5
            else "warm_clear_light_weather_in_a_warm_neighborhood"
        )
    if bucket == "warm_low_70s":
        if conditions & {"fog", "wind"}:
            return "warm_weather_near_the_bay"
        if temp >= 72.5:
            return "warm_clear_weather_in_a_warm_neighborhood"
        return "warm_weather_in_a_warm_neighborhood"
    if bucket == "low_70s":
        if conditions & {"fog", "wind"}:
            return "warm_weather_near_the_bay"
        if temp < 70:
            return "mild_weather_near_the_bay_with_wind_condition"
        if temp < 70.5:
            return "warm_clear_weather_near_the_bay"
        if temp < 71:
            return "warm_clear_weather_near_the_coast"
        return "warm_weather_in_a_warm_neighborhood"
    if bucket == "near_70":
        if conditions & {"fog", "wind"}:
            return "warm_light_weather_near_the_bay"
        if temp < 68:
            return "warm_light_weather_near_the_coast"
        return "warm_light_weather_in_a_warm_neighborhood"
    if bucket == "upper_60s":
        if "wind" in conditions or "fog" in conditions:
            return "mild_weather_near_the_coast_with_wind_condition"
        return "mild_weather_in_a_warm_neighborhood"
    if bucket == "mid_60s":
        if "fog" in conditions:
            return "mild_weather_near_the_coast_with_fog_condition"
        if "wind" in conditions:
            return "mild_weather_near_the_coast_with_wind_condition"
        return "mild_weather_near_the_bay"
    if bucket == "low_mid_60s":
        if "fog" in conditions:
            return "mild_weather_near_the_coast_with_fog_condition"
        if "wind" in conditions:
            return "mild_weather_near_the_coast_with_wind_condition"
        return "early_60s_weather_and_dry"
    if bucket == "early_60s":
        if "fog" in conditions:
            return "mild_weather_near_the_coast_with_fog_condition"
        if "wind" in conditions:
            return "mild_weather_near_the_coast_with_wind_condition"
        return "mild_weather_in_a_warm_neighborhood"
    if bucket == "low_60s":
        return (
            "cool_weather_with_fog_or_wind_condition"
            if conditions & {"fog", "wind"}
            else "cool_weather_near_the_bay_or_coast"
        )
    if bucket == "mid_50s":
        return "cold_weather_with_wind_condition" if conditions & {"fog", "wind"} else "54_to_56_degree_weather_and_dry"
    if bucket == "upper_50s":
        return (
            "cool_weather_with_fog_or_wind_condition"
            if conditions & {"fog", "wind"}
            else "cool_weather_near_the_bay_or_coast"
        )
    if bucket in {"cold", "low_50s"}:
        if conditions & {"fog", "wind"}:
            return "cold_weather_with_wind_condition"
        if 50 <= temp < 51:
            return "cold_weather_with_wind_condition"
        return "cold_weather_and_dry" if temp < 51 else "54_to_56_degree_weather_and_dry"
    return "very_cold_weather_with_wind_condition" if conditions & {"fog", "wind"} else "very_cold_weather_and_dry"


def get_outfit(
    snapshot: WeatherSnapshot, context: OutfitWeatherContext, *, resolved_location: LocationRecord | None = None
) -> tuple[dict[str, str], str]:
    """Select one pre-generated FLUX outfit image for the interpreted weather."""
    preset_key = selected_weather_preset_key(context)
    return (
        {"preset_key": preset_key, "generated_image_url": f"/static/generated/flux2/{preset_key}.png"},
        context.outfit_note,
    )


def display_location_name(fallback_name: str, query: str) -> str:
    """Return a concise SF display name from known ZIP/neighborhood aliases."""
    normalized_query = " ".join(query.strip().split()).casefold()
    return next((label for alias, (label, _zone) in SF_ZIP_TO_HOOD.items() if alias in normalized_query), fallback_name)


def interpret_weather_for_messaging_and_outfit_selection(
    snapshot: WeatherSnapshot, resolved_location: LocationRecord | None, query: str
) -> OutfitWeatherContext:
    """Convert raw weather into SF-specific clothing signals and an outfit note."""
    lowered = snapshot.description.lower()
    derived_conditions = {
        condition
        for condition, terms in RAW_DESCRIPTION_TO_DERIVED_CONDITION.items()
        if any(term in lowered for term in terms)
    }
    if snapshot.weather_code in WEATHER_CODE_TO_DERIVED_CONDITION:
        derived_conditions.add(WEATHER_CODE_TO_DERIVED_CONDITION[snapshot.weather_code])
    if (snapshot.wind_speed_mph is not None and snapshot.wind_speed_mph >= 12) or (
        snapshot.wind_gust_mph is not None and snapshot.wind_gust_mph >= 18
    ):
        derived_conditions.add("wind")

    rain_level = (
        "storm"
        if snapshot.snow
        else next(
            level
            for level, low, high in RAIN_LEVELS
            if (snapshot.precip_in <= 0 and level == "none") or low < snapshot.precip_in <= high
        )
    )
    if rain_level != "none":
        derived_conditions.add("wet")

    local_dt = snapshot.observed_at.astimezone(SF_TIMEZONE)

    normalized_query = " ".join(query.strip().split()).casefold()
    derived_microclimate_zone = next(
        (zone for alias, (_label, zone) in SF_ZIP_TO_HOOD.items() if alias in normalized_query), None
    )

    # Prefer provider apparent temperature when present; display still uses actual temperature.
    effective_temp_f = snapshot.feels_like_f if snapshot.feels_like_f is not None else snapshot.temperature_f

    if snapshot.precip_probability_pct >= 35 and rain_level == "none":
        derived_conditions.add("wet")

    bucket = next(label for label, low, high in TEMPERATURE_BUCKETS if low <= effective_temp_f < high)
    note_parts = [BUCKET_NOTES[bucket]]
    if rain_level == "drizzle":
        note_parts.append("Drizzle counts as wet; keep rain-safe shoes or an umbrella.")
    elif rain_level in {"rain", "storm"}:
        note_parts.append("It's raining, use water-safe shoes and an umbrella.")
    elif "wet" in derived_conditions:
        note_parts.append("Rain possible; keep a folded umbrella handy.")
    if "fog" in derived_conditions:
        note_parts.append("Fog can feel colder.")
    outfit_note = " ".join(note_parts)

    return OutfitWeatherContext(
        effective_temp_f=effective_temp_f,
        bucket=bucket,
        rain_level=rain_level,
        derived_conditions=frozenset(derived_conditions),
        derived_microclimate_zone=derived_microclimate_zone,
        local_hour=local_dt.hour,
        outfit_note=outfit_note,
    )
