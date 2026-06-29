"""Weather provider fetch/parsing helpers for Tomorrow.io and Weatherstack."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

import httpx

from backend_models import ForecastBundle, LocationRecord, WeatherSnapshot


WEATHER_CODE_MAP = {
    1000: "Clear, sunny",
    1001: "Cloudy",
    1100: "Mostly clear",
    1101: "Partly cloudy",
    1102: "Mostly cloudy",
    2000: "Fog",
    2100: "Light fog",
    3000: "Light wind",
    3001: "Windy",
    3002: "Strong wind",
    4000: "Drizzle",
    4001: "Rain",
    4200: "Light rain",
    4201: "Heavy rain",
    5000: "Snow",
    5001: "Flurries",
    5100: "Light snow",
    5101: "Heavy snow",
    6000: "Freezing drizzle",
    6001: "Freezing rain",
    6200: "Light freezing rain",
    6201: "Heavy freezing rain",
    7000: "Ice pellets",
    7101: "Heavy ice pellets",
    7102: "Light ice pellets",
    8000: "Thunderstorm",
}


def is_snow_code(code: int) -> bool:
    """Return whether the normalized weather code represents snow or flurries."""
    return code in {5000, 5001, 5100, 5101}


def infer_night(observed_at: datetime, timezone_name: str | None) -> bool:
    """Infer day/night from the local wall clock hour."""
    if timezone_name:
        try:
            observed_at = observed_at.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            pass
    return observed_at.hour < 5 or observed_at.hour >= 21


def explain_weather_provider_failure(exc: BaseException) -> str:
    """Summarize a provider/network failure into a short log-friendly string."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            tag = "rate limited"
        elif status in (402, 403):
            tag = "quota or plan denied"
        elif 500 <= status < 600:
            tag = "upstream server error"
        else:
            tag = "HTTP error"
        return f"{tag} ({status})"
    if isinstance(exc, httpx.TimeoutException):
        return "request timeout"
    if isinstance(exc, httpx.RequestError):
        return f"network error ({type(exc).__name__})"
    return str(exc) or type(exc).__name__


def tomorrow_raise_if_error_payload(payload: dict[str, Any], *, phase: str) -> None:
    """Raise on Tomorrow.io JSON error payloads that still returned HTTP 200."""
    if phase == "realtime" and isinstance(payload.get("data"), dict):
        return
    if phase == "forecast" and isinstance(payload.get("timelines"), dict):
        return
    if payload.get("code") is None and payload.get("type") is None:
        return
    raise RuntimeError(
        f"Tomorrow.io {phase} API error [{payload.get('code', '?')}]: {payload.get('message') or payload.get('type') or 'unknown error'}"
    )


def parse_utc_timestamp(value: str) -> datetime:
    """Parse an ISO timestamp and normalize it into UTC."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def total_precip_intensity_in(values: dict[str, Any]) -> float:
    """Combine all precipitation components into one inches-per-hour intensity."""
    return float(
        (values.get("rainIntensity") or 0)
        + (values.get("snowIntensity") or 0)
        + (values.get("sleetIntensity") or 0)
        + (values.get("freezingRainIntensity") or 0)
    )


def required_float(values: dict[str, Any], field: str) -> float:
    """Return a required numeric provider field or fail closed."""
    if values.get(field) is None:
        raise RuntimeError(f"Weather provider missing required field: {field}")
    return float(values[field])


def required_int(values: dict[str, Any], field: str) -> int:
    """Return a required integer provider field or fail closed."""
    if values.get(field) is None:
        raise RuntimeError(f"Weather provider missing required field: {field}")
    return int(values[field])


def build_snapshot(
    *,
    query: str,
    location_name: str,
    temperature_f: float,
    feels_like_f: float | None,
    precip_probability_pct: int,
    precip_in: float,
    weather_code: int,
    observed_at: datetime,
    timezone_name: str | None,
    source: str,
    wind_speed_mph: float | None = None,
    wind_gust_mph: float | None = None,
    description_override: str | None = None,
    snow_override: bool | None = None,
) -> WeatherSnapshot:
    """Build a normalized snapshot from provider-specific weather fields."""
    return WeatherSnapshot(
        query=query,
        location_name=location_name,
        temperature_f=temperature_f,
        precip_probability_pct=max(0, min(100, precip_probability_pct)),
        description=description_override
        if description_override is not None
        else WEATHER_CODE_MAP.get(weather_code, "Weather unavailable"),
        precip_in=precip_in,
        weather_code=weather_code,
        snow=snow_override if snow_override is not None else is_snow_code(weather_code),
        night=infer_night(observed_at, timezone_name),
        observed_at=observed_at,
        source=source,
        feels_like_f=feels_like_f,
        wind_speed_mph=wind_speed_mph,
        wind_gust_mph=wind_gust_mph,
    )


async def fetch_tomorrow_bundle(
    client: httpx.AsyncClient, loc: LocationRecord, *, api_key: str, hours_ahead: int
) -> ForecastBundle:
    """Fetch current and hourly weather from Tomorrow.io for one resolved location."""
    realtime_response = await client.get(
        "https://api.tomorrow.io/v4/weather/realtime",
        params={
            "location": loc.tomorrow_location,
            "units": "imperial",
            "apikey": api_key,
        },
    )
    realtime_response.raise_for_status()
    realtime_payload = realtime_response.json()
    tomorrow_raise_if_error_payload(realtime_payload, phase="realtime")
    current = realtime_payload.get("data") or {}
    current_values = current.get("values") or {}
    current_snapshot = build_snapshot(
        query=loc.query,
        location_name=loc.display_name,
        temperature_f=required_float(current_values, "temperature"),
        feels_like_f=float(current_values["temperatureApparent"])
        if current_values.get("temperatureApparent") is not None
        else None,
        wind_speed_mph=float(current_values["windSpeed"])
        if current_values.get("windSpeed") is not None
        else None,
        wind_gust_mph=float(current_values["windGust"])
        if current_values.get("windGust") is not None
        else None,
        precip_probability_pct=int(current_values.get("precipitationProbability") or 0),
        precip_in=total_precip_intensity_in(current_values),
        weather_code=required_int(current_values, "weatherCode"),
        observed_at=parse_utc_timestamp(
            current.get("time") or datetime.now(UTC).isoformat()
        ),
        timezone_name=loc.timezone,
        source="tomorrow-realtime",
    )
    hourly: list[WeatherSnapshot] = []
    if hours_ahead > 0:
        forecast_response = await client.get(
            "https://api.tomorrow.io/v4/weather/forecast",
            params={
                "location": loc.tomorrow_location,
                "timesteps": "1h",
                "units": "imperial",
                "apikey": api_key,
            },
        )
        forecast_response.raise_for_status()
        forecast_payload = forecast_response.json()
        tomorrow_raise_if_error_payload(forecast_payload, phase="forecast")
        for entry in (forecast_payload.get("timelines") or {}).get("hourly") or []:
            if not entry.get("time"):
                continue
            values = entry.get("values") or {}
            hourly.append(
                build_snapshot(
                    query=loc.query,
                    location_name=loc.display_name,
                    temperature_f=required_float(values, "temperature"),
                    feels_like_f=float(values["temperatureApparent"])
                    if values.get("temperatureApparent") is not None
                    else None,
                    wind_speed_mph=float(values["windSpeed"])
                    if values.get("windSpeed") is not None
                    else None,
                    wind_gust_mph=float(values["windGust"])
                    if values.get("windGust") is not None
                    else None,
                    precip_probability_pct=int(
                        values.get("precipitationProbability") or 0
                    ),
                    precip_in=total_precip_intensity_in(values),
                    weather_code=required_int(values, "weatherCode"),
                    observed_at=parse_utc_timestamp(entry["time"]),
                    timezone_name=loc.timezone,
                    source="tomorrow-forecast",
                )
            )
    return ForecastBundle(
        current=current_snapshot, hourly=hourly, resolved_location=loc
    )


def _weatherstack_join_descriptions(row: dict[str, Any]) -> str:
    """Join Weatherstack description fragments into one readable string."""
    return (
        ", ".join(
            str(part) for part in (row.get("weather_descriptions") or []) if part
        ).strip()
        or "Weather unavailable"
    )


def _weatherstack_precip_probability_pct(row: dict[str, Any]) -> int:
    """Reduce Weatherstack rain/snow chances to one percentage."""
    return max(
        0,
        min(
            100,
            max(int(row.get("chanceofrain") or 0), int(row.get("chanceofsnow") or 0)),
        ),
    )


def _weatherstack_infer_snow(row: dict[str, Any]) -> bool:
    """Infer snowy conditions from Weatherstack text plus chance-of-snow."""
    desc = _weatherstack_join_descriptions(row).lower()
    return (
        any(token in desc for token in ("snow", "blizzard", "sleet", "ice pellets"))
        or int(row.get("chanceofsnow") or 0) >= 45
    )


def _parse_weatherstack_local_observed_at(
    location_payload: dict[str, Any], *, timezone_name: str | None
) -> datetime:
    """Parse Weatherstack localtime into a UTC datetime."""
    local_raw = (location_payload.get("localtime") or "").strip()
    if not local_raw:
        return datetime.now(UTC)
    naive = datetime.strptime(local_raw, "%Y-%m-%d %H:%M")
    if timezone_name:
        try:
            return naive.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(UTC)
        except ZoneInfoNotFoundError:
            pass
    return naive.replace(tzinfo=UTC)


def _parse_weatherstack_hour_observed_at(
    date_key: str, minutes_from_midnight_raw: str, *, timezone_name: str | None
) -> datetime:
    """Convert a Weatherstack hourly row into a UTC datetime."""
    local_dt = datetime.strptime(date_key, "%Y-%m-%d") + timedelta(
        minutes=int(minutes_from_midnight_raw or 0)
    )
    if timezone_name:
        try:
            return local_dt.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(UTC)
        except ZoneInfoNotFoundError:
            pass
    return local_dt.replace(tzinfo=UTC)


async def fetch_weatherstack_bundle(
    client: httpx.AsyncClient,
    loc: LocationRecord,
    *,
    api_key: str,
    concise_location_label,
    max_forecast_hours: int,
    hours_ahead: int,
) -> ForecastBundle:
    """Fetch Weatherstack current weather, using forecast only when future hours are requested."""
    endpoint = "forecast" if hours_ahead > 0 else "current"
    response = await client.get(
        f"https://api.weatherstack.com/{endpoint}",
        params={
            "access_key": api_key,
            "query": loc.tomorrow_location,
            "units": "f",
            **(
                {
                    "forecast_days": max(3, (max_forecast_hours + 23) // 24 + 1),
                    "hourly": 1,
                    "interval": 1,
                }
                if hours_ahead > 0
                else {}
            ),
        },
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload.get("error"), dict):
        raise RuntimeError(str(payload["error"].get("info") or payload["error"]))
    location_payload = payload.get("location") or {}
    timezone_name = location_payload.get("timezone_id")
    location_name = concise_location_label(
        ", ".join(
            part
            for part in (
                location_payload.get("name"),
                location_payload.get("region"),
                location_payload.get("country"),
            )
            if part
        )
        or loc.display_name,
        query=loc.query,
    )
    current_payload = payload.get("current") or {}
    precip_probability = _weatherstack_precip_probability_pct(current_payload)
    if precip_probability == 0 and float(current_payload.get("precip") or 0) > 0:
        precip_probability = min(100, 35)
    current_snapshot = build_snapshot(
        query=loc.query,
        location_name=location_name,
        temperature_f=required_float(current_payload, "temperature"),
        feels_like_f=float(current_payload["feelslike"])
        if current_payload.get("feelslike") is not None
        else None,
        wind_speed_mph=float(current_payload["wind_speed"])
        if current_payload.get("wind_speed") is not None
        else None,
        wind_gust_mph=float(current_payload["wind_gust"])
        if current_payload.get("wind_gust") is not None
        else None,
        precip_probability_pct=precip_probability,
        precip_in=float(current_payload.get("precip") or 0),
        weather_code=required_int(current_payload, "weather_code"),
        observed_at=_parse_weatherstack_local_observed_at(
            location_payload, timezone_name=timezone_name
        ),
        timezone_name=timezone_name,
        source="weatherstack-current",
        snow_override=_weatherstack_infer_snow(current_payload),
    )
    hourly: list[WeatherSnapshot] = []
    for date_key, day_payload in sorted((payload.get("forecast") or {}).items()):
        if not isinstance(day_payload, dict):
            continue
        for hour_row in day_payload.get("hourly") or []:
            if not isinstance(hour_row, dict) or hour_row.get("time") is None:
                continue
            hourly.append(
                build_snapshot(
                    query=loc.query,
                    location_name=location_name,
                    temperature_f=required_float(hour_row, "temperature"),
                    feels_like_f=float(hour_row["feelslike"])
                    if hour_row.get("feelslike") is not None
                    else None,
                    wind_speed_mph=float(hour_row["wind_speed"])
                    if hour_row.get("wind_speed") is not None
                    else None,
                    wind_gust_mph=float(hour_row["wind_gust"])
                    if hour_row.get("wind_gust") is not None
                    else None,
                    precip_probability_pct=_weatherstack_precip_probability_pct(
                        hour_row
                    ),
                    precip_in=float(hour_row.get("precip") or 0),
                    weather_code=required_int(hour_row, "weather_code"),
                    observed_at=_parse_weatherstack_hour_observed_at(
                        date_key, str(hour_row.get("time")), timezone_name=timezone_name
                    ),
                    timezone_name=timezone_name,
                    source="weatherstack-forecast",
                    snow_override=_weatherstack_infer_snow(hour_row),
                )
            )
    hourly.sort(key=lambda snapshot: snapshot.observed_at)
    return ForecastBundle(
        current=current_snapshot, hourly=hourly, resolved_location=loc
    )
