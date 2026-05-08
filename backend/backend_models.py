"""Core backend state models for Comfyday's FLUX-static scene payloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SceneState:
    """Final `/api/scene` payload returned to the frontend."""

    version: int
    location_name: str
    query: str
    weather_latitude: float | None
    weather_longitude: float | None
    mode: str
    hours_ahead: int
    target_time: str
    temperature_f: float
    feels_like_f: float | None
    precip_probability_pct: int
    description: str
    wind_label: str | None
    bucket: str
    rain_level: str
    snow: bool
    night: bool
    outfit_note: str
    stale: bool
    source: str
    changed: bool
    last_updated: str
    base_image_url: str
    subject_pose: str
    render_mode: str
    generated_image_url: str | None
    selected_layer_keys: list[str]
    layers: list[dict[str, Any]]
    video_url: str | None = None
    forecast_temps: dict[str, float] = field(default_factory=dict)

    def signature(self) -> tuple[Any, ...]:
        """Return the stable subset used to detect scene changes."""
        return (
            self.mode,
            self.hours_ahead,
            self.subject_pose,
            self.bucket,
            self.rain_level,
            self.snow,
            self.night,
            self.generated_image_url,
            self.video_url,
            self.render_mode,
            tuple(self.selected_layer_keys),
            tuple(str(layer.get("key") or "") for layer in self.layers),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the scene payload for JSON responses."""
        return asdict(self)


@dataclass(slots=True)
class WeatherSnapshot:
    """Normalized weather reading used by the outfit engine."""

    query: str
    location_name: str
    temperature_f: float
    precip_probability_pct: int
    description: str
    precip_in: float
    weather_code: int
    snow: bool
    night: bool
    observed_at: datetime
    source: str
    feels_like_f: float | None = None
    wind_speed_mph: float | None = None
    wind_gust_mph: float | None = None


@dataclass(slots=True)
class LocationRecord:
    """Resolved location metadata for weather/provider calls."""

    query: str
    display_name: str
    latitude: float
    longitude: float
    timezone: str | None
    country: str | None
    country_code: str | None
    admin1: str | None
    admin2: str | None
    geocoder: str
    tomorrow_location: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the location record for JSON responses."""
        return asdict(self)


@dataclass(slots=True)
class ForecastBundle:
    """Current snapshot plus optional hourly forecast snapshots."""

    current: WeatherSnapshot
    hourly: list[WeatherSnapshot]
    resolved_location: LocationRecord


@dataclass(frozen=True, slots=True)
class OutfitWeatherContext:
    """SF-aware weather interpretation used for clothing selection."""

    effective_temp_f: float
    bucket: str
    rain_level: str
    derived_conditions: frozenset[str]
    derived_microclimate_zone: str | None
    local_hour: int
    outfit_note: str
