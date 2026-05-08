"""Scene assembly for the one-image FLUX-static runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend_models import LocationRecord, SceneState, WeatherSnapshot
from outfit_logic import display_location_name, get_outfit, interpret_weather_for_messaging_and_outfit_selection

FRONT_POSE_ID = "front"
BASE_IMAGE_URL = "/static/assets/base/girl-real-pose-front.png"
FALLBACK_FLUX_IMAGE_URL = "/static/generated/flux2/mild_weather_near_the_bay.png"


def existing_static_image_url(url: str) -> str:
    """Return a usable static image URL, falling back when a generated rerun file is absent."""
    static_root = Path(__file__).resolve().parent / "static"
    path = static_root / url.removeprefix("/static/")
    if path.exists():
        return url
    fallback_path = static_root / FALLBACK_FLUX_IMAGE_URL.removeprefix("/static/")
    return FALLBACK_FLUX_IMAGE_URL if fallback_path.exists() else BASE_IMAGE_URL


def build_scene(
    snapshot: WeatherSnapshot,
    previous: SceneState | None,
    *,
    mode: str,
    hours_ahead: int,
    resolved_location: LocationRecord | None = None,
) -> SceneState:
    """Build the frontend payload from weather signals and one generated outfit image."""
    context = interpret_weather_for_messaging_and_outfit_selection(snapshot, resolved_location, snapshot.query)
    selected, outfit_note = get_outfit(snapshot, context, resolved_location=resolved_location)
    generated_image_url = existing_static_image_url(selected["generated_image_url"])
    selected_layer_keys = [selected["preset_key"]]
    current_signature = (
        mode,
        hours_ahead,
        FRONT_POSE_ID,
        context.bucket,
        context.rain_level,
        snapshot.snow,
        snapshot.night,
        generated_image_url,
        tuple(selected_layer_keys),
    )
    version = previous.version if previous else 0
    changed = not previous or current_signature != previous.signature()
    if changed:
        version += 1
    location_query = " ".join(
        part
        for part in (
            snapshot.query,
            resolved_location.query if resolved_location else "",
            resolved_location.display_name if resolved_location else "",
        )
        if part
    )
    return SceneState(
        version=version,
        location_name=display_location_name(snapshot.location_name, location_query),
        query=snapshot.query,
        weather_latitude=resolved_location.latitude if resolved_location else None,
        weather_longitude=resolved_location.longitude if resolved_location else None,
        mode=mode,
        hours_ahead=hours_ahead,
        target_time=snapshot.observed_at.isoformat(),
        temperature_f=round(snapshot.temperature_f, 1),
        feels_like_f=round(snapshot.feels_like_f, 1) if snapshot.feels_like_f is not None else None,
        precip_probability_pct=snapshot.precip_probability_pct,
        description=snapshot.description,
        wind_label=wind_label(snapshot),
        bucket=context.bucket,
        rain_level=context.rain_level,
        snow=snapshot.snow,
        night=snapshot.night,
        outfit_note=outfit_note,
        stale=False,
        source=snapshot.source,
        changed=changed,
        last_updated=datetime.now(UTC).isoformat(),
        base_image_url=generated_image_url,
        subject_pose=FRONT_POSE_ID,
        render_mode="flux_static",
        generated_image_url=generated_image_url,
        selected_layer_keys=selected_layer_keys,
        layers=[],
    )


def wind_label(snapshot: WeatherSnapshot) -> str | None:
    """Return a compact wind label only when provider wind data is meaningful."""
    wind = snapshot.wind_speed_mph or 0
    gust = snapshot.wind_gust_mph or 0
    if gust >= 35 or wind >= 25:
        return "strong wind"
    if gust >= 24 or wind >= 18:
        return "windy"
    if gust >= 18 or wind >= 12:
        return "breezy"
    return None
