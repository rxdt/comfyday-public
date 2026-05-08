"""Scene assembly for the one-image FLUX-static runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from backend_models import LocationRecord, SceneState, WeatherSnapshot
from outfit_logic import (
    display_location_name,
    get_outfit,
    interpret_weather_for_messaging_and_outfit_selection,
)
from weather_api import WEATHER_CODE_MAP

FRONT_POSE_ID = "front"
BASE_IMAGE_URL = "/static/assets/base/girl-real-pose-front.png"
FALLBACK_FLUX_IMAGE_URL = "/static/generated/flux2/64_to_65_dry_light_layer.png"


def existing_static_image_url(url: str) -> str:
    """Return a usable static image URL, falling back when a generated rerun file is absent."""
    static_root = Path(__file__).resolve().parent / "static"
    path = static_root / url.removeprefix("/static/")
    if path.exists():
        return url
    fallback_path = static_root / FALLBACK_FLUX_IMAGE_URL.removeprefix("/static/")
    if not fallback_path.exists():
        return BASE_IMAGE_URL
    return FALLBACK_FLUX_IMAGE_URL


def existing_static_video_url(image_url: str) -> str | None:
    """Return a sibling MP4 URL for a generated image when one has been supplied."""
    if not image_url.startswith("/static/generated/flux2/"):
        return None
    static_root = Path(__file__).resolve().parent / "static"
    video_url = str(Path(image_url).with_suffix(".mp4"))
    video_path = static_root / video_url.removeprefix("/static/")
    if video_path.exists():
        return video_url
    return None


def build_scene(
    snapshot: WeatherSnapshot,
    previous: SceneState | None,
    mode: str,
    hours_ahead: int,
    resolved_location: LocationRecord | None = None,
) -> SceneState:
    """Build the frontend payload from weather signals and one generated outfit image."""
    outfit_context = interpret_weather_for_messaging_and_outfit_selection(
        snapshot, snapshot.query
    )
    selected, outfit_note = get_outfit(outfit_context)
    generated_image_url = existing_static_image_url(selected["generated_image_url"])
    video_url = existing_static_video_url(generated_image_url)
    selected_layer_keys = [selected["preset_key"]]
    current_signature = (
        mode,
        hours_ahead,
        FRONT_POSE_ID,
        outfit_context.bucket,
        outfit_context.rain_level,
        snapshot.snow,
        snapshot.night,
        generated_image_url,
        video_url,
        "flux_static",
        tuple(selected_layer_keys),
        tuple(),
    )
    version = previous.version if previous else 0
    changed = not previous or current_signature != previous.signature()
    if changed:
        version += 1
    wind = snapshot.wind_speed_mph or 0
    gust = snapshot.wind_gust_mph or 0
    wind_label = None
    if gust >= 35 or wind >= 25:
        wind_label = WEATHER_CODE_MAP[3002]
    elif gust >= 24 or wind >= 20:
        wind_label = WEATHER_CODE_MAP[3001]
    elif gust >= 18 or wind >= 12:
        wind_label = WEATHER_CODE_MAP[3000]
    return SceneState(
        version=version,
        location_name=display_location_name(
            snapshot.location_name,
            resolved_location.query if resolved_location else snapshot.query,
        ),
        query=snapshot.query,
        weather_latitude=resolved_location.latitude if resolved_location else None,
        weather_longitude=resolved_location.longitude if resolved_location else None,
        mode=mode,
        hours_ahead=hours_ahead,
        target_time=snapshot.observed_at.isoformat(),
        temperature_f=round(snapshot.temperature_f, 1),
        feels_like_f=round(outfit_context.effective_temp_f, 1),
        precip_probability_pct=snapshot.precip_probability_pct,
        description=snapshot.description,
        wind_label=wind_label,
        bucket=outfit_context.bucket,
        rain_level=outfit_context.rain_level,
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
        video_url=video_url,
    )
