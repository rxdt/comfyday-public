"""San Francisco weather interpretation and outfit-selection logic."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from backend_models import OutfitWeatherContext, WeatherSnapshot


SF_ZIP_TO_HOOD: dict[str, tuple[str, str]] = {
    "94102": (
        "Tenderloin, Hayes Valley, North of Market, San Francisco",
        "microclimate_mix",
    ),
    "94103": ("South of Market (SoMa), San Francisco", "sunbelt"),
    "94104": ("Financial District, San Francisco", "microclimate_mix"),
    "94105": ("Mission Bay, San Francisco", "sunbelt"),
    "94107": ("Potrero / Mission Bay, San Francisco", "sunbelt"),
    "94108": ("Chinatown, Nob Hill, San Francisco", "microclimate_mix"),
    "94109": ("Polk, Russian / Nob Hill, San Francisco", "microclimate_mix"),
    "94110": ("Mission District, San Francisco", "sunbelt"),
    "94111": ("Embarcadero / FiDi, San Francisco", "microclimate_mix"),
    "94112": ("Ingleside-Excelsior, San Francisco", "microclimate_mix"),
    "94113": ("Glen Park, San Francisco", "sunbelt"),
    "94114": ("Castro / Noe Valley, San Francisco", "sunbelt"),
    "94115": ("Japantown / Pacific Heights, San Francisco", "microclimate_mix"),
    "94116": ("Outer Sunset, San Francisco", "coastal"),
    "94117": ("Haight-Ashbury, San Francisco", "microclimate_mix"),
    "94118": ("Inner Richmond, San Francisco", "coastal"),
    "94121": ("Outer Richmond, San Francisco", "coastal"),
    "94122": ("Outer Sunset, San Francisco", "coastal"),
    "94123": ("Marina / Cow Hollow, San Francisco", "microclimate_mix"),
    "94124": ("Bayview-Hunters Point, San Francisco", "sunbelt"),
    "94127": ("St. Francis Wood / West Portal, San Francisco", "microclimate_mix"),
    "94129": ("Presidio, San Francisco", "coastal"),
    "94130": ("Treasure Island, San Francisco", "microclimate_mix"),
    "94131": ("Twin Peaks, San Francisco", "sunbelt"),
    "94132": ("Lake Merced, San Francisco", "coastal"),
    "94133": ("North Beach / Chinatown, San Francisco", "microclimate_mix"),
    "94134": ("Visitacion Valley, San Francisco", "sunbelt"),
    "94143": ("UC San Francisco, San Francisco", "microclimate_mix"),
    "94158": ("Mission Bay, San Francisco", "sunbelt"),
}
SF_TIMEZONE = ZoneInfo("America/Los_Angeles")

TEMPERATURE_BUCKETS = (
    ("0_to_47", float("-inf"), 47, "0_to_48_dry_very_cold"),  # cold tail
    ("47_to_49", 47, 49, "48_to_50_dry_cold"),  # 2F
    ("49_to_51", 49, 51, "50_to_51_dry_cold_layer"),  # 1F
    ("51_to_52", 51, 52, "50_to_52_dry_very_cold"),  # 1F
    ("52_to_52.5", 52, 52.5, "52_to_61_cool_wet_or_dry_layer"),
    ("52.5_to_53", 52.5, 53, "51_to_53_dry_cold_layer"),  # 1F
    ("53_to_54", 53, 54, "53_to_55_dry_cool_layer"),  # 1F
    ("54_to_55", 54, 55, "54_to_55_dry_layered"),  # 1F
    ("55_to_56", 55, 56, "55_to_57_dry_black_layer"),  # 1F
    ("55_to_56.5", 56, 56.5, "55_to_56_dry_possible_rain_umbrella"),
    ("56.5_to_57", 56.5, 57, "56_to_57_dry_chunky_cardigan"),  # 0.5F
    ("57_to_58", 57, 58, "57_to_57_5_dry_cool_layer"),  # 1F
    ("58_to_59", 58, 59, "57_to_59_dry_cool_layer"),  # 1F
    ("59_to_60", 59, 60, "59_to_61_dry_sweatsuit_layer"),  # 1F
    ("60_to_60_5", 60, 60.5, "60_to_61_dry_layered_beanie"),  # 0.5F
    ("60_5_to_61", 60.5, 61, "61_to_62_dry_light_layer"),  # 0.5F
    ("61_to_61_5", 61, 61.5, "62_to_62_5_dry_mild_layer"),  # 0.5F
    ("61_5_to_62", 61.5, 62, "62_5_to_63_dry_light_layer"),  # 0.5F
    ("62_to_62_5", 62, 62.5, "62_to_64_dry_cardigan"),  # 0.5F
    ("62_5_to_63", 62.5, 63, "63_to_63_5_dry_jacket_uggs"),  # 0.5F
    ("63_to_63_5", 63, 63.5, "64_to_65_dry_light_layer"),  # 0.5F
    ("63_5_to_64", 63.5, 64, "65_to_66_dry_light_layer"),  # 0.5F
    ("64_to_64_5", 64, 64.5, "66_to_67_dry_mild_layer"),  # 0.5F
    ("64_5_to_65", 64.5, 65, "67_to_67_5_dry_zip_hoodie"),  # 0.5F
    ("65_to_65_5", 65, 65.5, "67_to_68_dry_warm_light"),  # 0.5F
    ("65_5_to_66", 65.5, 66, "67_to_69_dry_warm_light"),  # 0.5F
    ("66_to_67", 66, 67, "66_to_67_dry_mild_layer"),  # 1F
    ("67_to_68", 67, 68, "67_to_67_5_dry_zip_hoodie"),  # 1F
    ("68_to_69", 68, 69, "67_to_68_dry_warm_light"),  # 1F
    ("69_to_69.5", 69, 69.5, "69_to_69_5_dry_warm_layer"),
    ("69_to_70", 69, 70, "69_to_71_dry_warm_light"),  # 1F
    ("70_to_70.5", 70, 70.5, "71_to_73_dry_warm"),  # 0.5
    ("70.5_to_71", 70.5, 71, "70_to_70_5_dry_warm_clear"),
    ("71_to_71.5", 71, 71.5, "72_5_to_73_dry_warm_clear"),  # 1F
    ("71.5_to_72", 71.5, 72, "70_5_to_71_dry_warm_clear"),
    ("72_to_73", 72, 73, "73_to_75_dry_warm_clear"),  # 1F
    ("73_to_74", 73, 74, "74_5_to_76_dry_warm_clear"),  # 1F
    ("74_to_75", 74, 75, "75_to_78_dry_hot"),  # 1F
    ("75_to_77", 75, 77, "75_to_78_dry_hot"),  # 2F
    ("77_to_80", 77, 80, "78_to_80_dry_hot"),  # 3F
    ("80_to_85", 80, 85, "80_to_85_dry_very_hot"),  # 5F
    ("85_plus", 85, float("inf"), "85_plus_dry_very_hot"),  # hot tail
)
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
    "0_to_47": "Full on winter clothing.",
    "47_to_49": "Keep outerwear on.",
    "49_to_51": "Grab the beanie.",
    "51_to_52": "Cold enough to bundle up",
    "52_to_52.5": "So chilly; keep layers on.",
    "52.5_to_53": "It's chilly enough for that coat",
    "53_to_54": "Layer like it will still feel chilly.",
    "54_to_55": "A base layer plus outerwear works best.",
    "55_to_56": "Approaching light jacket weather.",
    "55_to_56.5": "Light jacket weather.",
    "56.5_to_57": "A chunkier layer makes sense.",
    "57_to_58": "Use a layer you can keep on.",
    "58_to_59": "A hoodie, jacket, or sweatshirt works.",
    "59_to_60": "Hoodie, cardigan, or light jacket range.",
    "60_to_60_5": "Layers plus beanie weather.",
    "60_5_to_61": "Bringing an extra layer makes sense.",
    "61_to_61_5": "A lighter layered look works.",
    "61_5_to_62": "Classic SF layering weather.",
    "62_to_62_5": "Cardigan or sweater by default.",
    "62_5_to_63": "A jacket still helps.",
    "63_to_63_5": "A light layer is enough.",
    "63_5_to_64": "Removable layers make sense.",
    "64_to_64_5": "Comfortable with an optional layer.",
    "64_5_to_65": "A light outer layer is optional.",
    "65_to_65_5": "You can dress lighter.",
    "65_5_to_66": "Warm-leaning but not summer-hot.",
    "66_to_67": "Lighter clothing, but not summer-hot.",
    "67_to_68": "Warm enough for less clothing.",
    "68_to_69": "Short sleeves or shorts could work.",
    "69_to_69.5": "Warm enough to dress like it's CA.",
    "69_to_70": "Wear warm weather cute",
    "70_to_70.5": "A warm-weather outfit works.",
    "70.5_to_71": "Work the warm weather outfit.",
    "71_to_71.5": "Warm-weather simplicity now.",
    "71.5_to_72": "It's a shorts and tank moment",
    "72_to_73": "Dress for the warm weather you want.",
    "73_to_74": "It's warm enough to dress skimpy.",
    "74_to_75": "A hotter-weather outfit works because you're hot.",
    "75_to_77": "Hot by SF standards. A 10.",
    "77_to_80": "Hot enough for your smallest outfit.",
    "80_to_85": "Prioritize breathable clothing and water.",
    "85_plus": "Heat-conscious outfit, no extra layers.",
}


def selected_weather_preset_key(context: OutfitWeatherContext) -> str:
    """Map adjusted weather signals to one generated outfit image key."""
    temp = context.effective_temp_f
    actual_wet = context.rain_level != "none"
    is_wet = actual_wet or "wet" in context.derived_conditions

    if is_wet:
        if temp < 48:
            return (
                "0_to_48_snow_or_windstorm"
                if actual_wet and {"snow", "wind"} & context.derived_conditions
                else ("0_to_48_rainstorm" if actual_wet else "0_to_48_dry_very_cold")
            )
        if actual_wet:
            if temp < 53:
                return "48_to_52_storming"
            if temp < 57:
                return "52_to_57_raining_cold"
            if temp < 61:
                return "57_to_61_raining_cool"
            if temp < 66:
                return "50_to_51_dry_high_precip"
            if temp < 69:
                return "61_to_69_raining_mild"
            return "69_to_80_raining_warm"
        if temp < 50:
            return "48_to_50_dry_cold"
        if temp < 51:
            return "50_to_52_dry_very_cold"
        if temp < 53:
            return "50_to_51_dry_cold_layer"
        if temp < 56:
            return "51_to_53_dry_cold_layer"
        if temp < 58:
            return "55_to_56_dry_possible_rain_umbrella"
        if temp < 61:
            return "52_to_61_cool_wet_or_dry_layer"
        if temp < 69:
            return "61_to_71_drizzle_mild"
        return "69_to_80_raining_warm"

    return next(
        key for _bucket, low, high, key in TEMPERATURE_BUCKETS if low <= temp < high
    )


def get_outfit(context: OutfitWeatherContext) -> tuple[dict[str, str], str]:
    """Select one pre-generated FLUX outfit image for the interpreted weather."""
    preset_key = selected_weather_preset_key(context)
    return (
        {
            "preset_key": preset_key,
            "generated_image_url": f"/static/generated/flux2/{preset_key}.png",
        },
        context.outfit_note,
    )


def display_location_name(fallback_name: str, query: str) -> str:
    """Return a concise SF display name from a known ZIP code."""
    return SF_ZIP_TO_HOOD.get(query.strip(), (fallback_name, ""))[0]


def interpret_weather_for_messaging_and_outfit_selection(
    snapshot: WeatherSnapshot, query: str
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
    if (snapshot.wind_speed_mph is not None and snapshot.wind_speed_mph >= 13) or (
        snapshot.wind_gust_mph is not None and snapshot.wind_gust_mph >= 18
    ):
        derived_conditions.add("wind")

    rain_level = "wet" if snapshot.snow or snapshot.precip_in > 0 else "none"
    if rain_level != "none":
        derived_conditions.add("wet")

    local_dt = snapshot.observed_at.astimezone(SF_TIMEZONE)

    derived_microclimate_zone = SF_ZIP_TO_HOOD.get(query.strip(), ("", None))[1]

    if snapshot.precip_probability_pct >= 35 and rain_level == "none":
        derived_conditions.add("wet")

    feels_like_f = (
        snapshot.feels_like_f
        if snapshot.feels_like_f is not None
        else snapshot.temperature_f
    )
    effective_temp_f = (snapshot.temperature_f * 0.4) + (feels_like_f * 0.6)
    if (
        8 <= local_dt.hour < 18
        and "fog" not in derived_conditions
        and ("sun" in lowered or snapshot.weather_code == 1000)
    ):
        effective_temp_f += 0.75
    if "cloud" in derived_conditions:
        effective_temp_f -= 0.5
    if "fog" in derived_conditions:
        effective_temp_f -= 0.5
    if rain_level != "none":
        effective_temp_f -= 0.5
    if derived_microclimate_zone == "coastal":
        effective_temp_f -= 0.75
    elif derived_microclimate_zone == "sunbelt":
        effective_temp_f += 0.75
    wind_mph = max(snapshot.wind_speed_mph or 0, snapshot.wind_gust_mph or 0)
    if 13 <= wind_mph < 20:
        effective_temp_f -= 0.75
    elif 20 <= wind_mph < 28:
        effective_temp_f -= 2
    elif wind_mph >= 28:
        effective_temp_f -= 4

    bucket = next(
        label
        for label, low, high, _key in TEMPERATURE_BUCKETS
        if low <= effective_temp_f < high
    )
    note_parts = [BUCKET_NOTES[bucket]]
    if rain_level != "none":
        note_parts.append("It's wet; use water-safe shoes and an umbrella.")
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
