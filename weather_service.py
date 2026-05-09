"""ZIP-only weather orchestration and scene caching for the Comfyday backend."""

from __future__ import annotations

import logging
import os
import re
from datetime import timedelta
from typing import Any

import httpx

from backend_models import ForecastBundle, LocationRecord, SceneState, WeatherSnapshot
from outfit_logic import SF_ZIP_TO_HOOD
from scene_builder import build_scene
from weather_api import explain_weather_provider_failure, fetch_tomorrow_bundle, fetch_weatherstack_bundle

logger = logging.getLogger("comfyday")

MAX_FORECAST_HOURS = 168
ZIP_CODE_RE = re.compile(r"^\d{5}$")


def normalize_zip_code(raw: str | None, default_zip: str) -> str:
    """Return one normalized 5-digit ZIP or raise a stable validation error."""
    cleaned = (raw or "").strip() or default_zip
    if not ZIP_CODE_RE.fullmatch(cleaned):
        raise ValueError("ZIP code must be exactly 5 digits.")
    return cleaned


def concise_location_label(primary: str | None, *, query: str) -> str:
    """Prefer SF neighborhood labels for known ZIPs, otherwise keep provider brevity."""
    if query in SF_ZIP_TO_HOOD:
        return SF_ZIP_TO_HOOD[query][0]
    primary_clean = (primary or "").strip()
    if not primary_clean:
        return query
    parts = [part.strip() for part in primary_clean.split(",") if part.strip()]
    if len(parts) >= 2 and parts[1].casefold() not in {"california", "united states"}:
        return f"{parts[0]}, {parts[1]}"
    return parts[0] if parts else primary_clean


def request_country_hint(headers: dict[str, str] | None) -> str | None:
    """Return one uppercase ISO country code from trusted proxy headers when present."""
    if not headers:
        return None
    for key in ("x-vercel-ip-country", "cf-ipcountry"):
        value = str(headers.get(key, "")).strip().upper()
        if len(value) == 2 and value.isalpha():
            return value
    return None


class WeatherSceneService:
    """Fetch weather by ZIP, cache normalized scenes, and build FLUX-static payloads."""

    def __init__(self) -> None:
        """Initialize provider credentials and in-memory scene caches."""
        self.default_query = "94110"
        self.tomorrow_api_key = os.getenv("TOMORROW_API_KEY", "").strip()
        self.weatherstack_api_key = os.getenv("WEATHERSTACK_API_KEY", "").strip()
        self.current_scene_cache: dict[str, SceneState] = {}
        self.weather_bundle_cache: dict[str, ForecastBundle] = {}

    async def resolve_weather_location(
        self, client: httpx.AsyncClient, zip_code: str, *, country_hint: str | None = None
    ) -> LocationRecord:
        """Resolve one 5-digit ZIP into provider-ready coordinates."""
        normalized = normalize_zip_code(zip_code, self.default_query)
        
        async def search(search_term: str) -> list[dict[str, Any]]:
            response = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": search_term, "count": 10, "language": "en", "format": "json"},
            )
            response.raise_for_status()
            return list((response.json() or {}).get("results") or [])

        async def search_nominatim(search_term: str) -> dict[str, Any] | None:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": search_term, "format": "jsonv2", "limit": 1, "accept-language": "en"},
                headers={"User-Agent": "comfyday-weather/1.0"},
            )
            response.raise_for_status()
            rows = list(response.json() or [])
            return rows[0] if rows else None

        results = await search(normalized)
        if not results:
            raise RuntimeError(f"Could not find a location for ZIP {normalized}.")

        def postcodes(row: dict[str, Any]) -> set[str]:
            return {str(code).strip() for code in row.get("postcodes") or [] if str(code).strip()}

        exact_row = next((row for row in results if normalized in postcodes(row)), None)
        hinted_rows = [
            row for row in results if str(row.get("country_code") or "").upper() == str(country_hint or "").upper()
        ]
        exact_hinted_row = next((row for row in hinted_rows if normalized in postcodes(row)), None)
        us_rows = [row for row in results if str(row.get("country_code") or "").upper() == "US"]
        exact_us_row = next((row for row in us_rows if normalized in postcodes(row)), None)
        if exact_us_row is None and normalized in SF_ZIP_TO_HOOD:
            # Some SF ZIPs like 94113 are not resolvable by ZIP alone in Open-Meteo.
            results = await search("San Francisco, California") or results
            exact_row = next((row for row in results if normalized in postcodes(row)), None)
            hinted_rows = [
                row for row in results if str(row.get("country_code") or "").upper() == str(country_hint or "").upper()
            ]
            exact_hinted_row = next((row for row in hinted_rows if normalized in postcodes(row)), None)
            us_rows = [row for row in results if str(row.get("country_code") or "").upper() == "US"]
            exact_us_row = next((row for row in us_rows if normalized in postcodes(row)), None)

        if exact_hinted_row is None and country_hint:
            hinted_geo = await search_nominatim(f"{normalized} {country_hint}")
            if hinted_geo:
                latitude = float(hinted_geo["lat"])
                longitude = float(hinted_geo["lon"])
                primary = str(hinted_geo.get("display_name") or hinted_geo.get("name") or f"{normalized} {country_hint}")
                return LocationRecord(
                    query=normalized,
                    display_name=concise_location_label(primary, query=normalized),
                    latitude=latitude,
                    longitude=longitude,
                    timezone=None,
                    country=None,
                    country_code=country_hint.upper(),
                    admin1=None,
                    admin2=None,
                    geocoder="nominatim-search-v1",
                    tomorrow_location=f"{latitude},{longitude}",
                )

        geo = exact_hinted_row or exact_us_row or exact_row or (hinted_rows[0] if hinted_rows else us_rows[0] if us_rows else results[0])

        latitude = float(geo["latitude"])
        longitude = float(geo["longitude"])
        primary = ", ".join(
            part for part in (geo.get("name"), geo.get("admin2"), geo.get("admin1"), geo.get("country")) if part
        )
        return LocationRecord(
            query=normalized,
            display_name=concise_location_label(primary, query=normalized),
            latitude=latitude,
            longitude=longitude,
            timezone=geo.get("timezone"),
            country=geo.get("country"),
            country_code=geo.get("country_code"),
            admin1=geo.get("admin1"),
            admin2=geo.get("admin2"),
            geocoder="open-meteo-search-v1",
            tomorrow_location=f"{latitude},{longitude}",
        )

    async def fetch_weather_bundle(
        self, query: str, *, hours_ahead: int, country_hint: str | None = None
    ) -> ForecastBundle:
        """Fetch weather using Tomorrow.io first, then Weatherstack fallback."""
        tomorrow_exc: BaseException | None = None
        zip_code = normalize_zip_code(query, self.default_query)
        async with httpx.AsyncClient(timeout=12.0) as client:
            loc = await self.resolve_weather_location(client, zip_code, country_hint=country_hint)
            if self.tomorrow_api_key:
                try:
                    return await fetch_tomorrow_bundle(
                        client, loc, api_key=self.tomorrow_api_key, hours_ahead=hours_ahead
                    )
                except Exception as exc:
                    tomorrow_exc = exc
                    logger.warning(
                        "Tomorrow.io failed (%s); trying Weatherstack.", explain_weather_provider_failure(exc)
                    )
            if self.weatherstack_api_key:
                try:
                    return await fetch_weatherstack_bundle(
                        client,
                        loc,
                        api_key=self.weatherstack_api_key,
                        concise_location_label=concise_location_label,
                        max_forecast_hours=MAX_FORECAST_HOURS,
                        hours_ahead=hours_ahead,
                    )
                except Exception as exc:
                    logger.warning("Weatherstack failed (%s).", explain_weather_provider_failure(exc))
                    if tomorrow_exc:
                        raise RuntimeError(
                            "Both weather providers failed: "
                            f"Tomorrow.io: {explain_weather_provider_failure(tomorrow_exc)}; "
                            f"Weatherstack: {explain_weather_provider_failure(exc)}."
                        ) from exc
                    raise
            if tomorrow_exc:
                raise RuntimeError(
                    "Tomorrow.io failed "
                    f"({explain_weather_provider_failure(tomorrow_exc)}) "
                    "and WEATHERSTACK_API_KEY is not configured."
                ) from tomorrow_exc
        raise RuntimeError("No weather provider succeeded. Set TOMORROW_API_KEY and/or WEATHERSTACK_API_KEY.")

    def select_hourly_snapshot(self, bundle: ForecastBundle, hours_ahead: int) -> WeatherSnapshot:
        """Pick the nearest hourly forecast snapshot to the requested offset."""
        if hours_ahead == 0 or not bundle.hourly:
            return bundle.current
        target_time = bundle.current.observed_at + timedelta(hours=hours_ahead)
        return min(bundle.hourly, key=lambda snapshot: abs(snapshot.observed_at - target_time))

    async def get_scene(
        self, hours_ahead: int = 0, query: str | None = None, *, country_hint: str | None = None
    ) -> SceneState:
        """Return the current or forecast scene for one ZIP code."""
        zip_code = normalize_zip_code(query, self.default_query)
        cache_key = zip_code
        try:
            bundle = await self.fetch_weather_bundle(zip_code, hours_ahead=hours_ahead, country_hint=country_hint)
            self.weather_bundle_cache[cache_key] = bundle
            snapshot = bundle.current if hours_ahead == 0 else self.select_hourly_snapshot(bundle, hours_ahead)
            scene = build_scene(
                snapshot,
                self.current_scene_cache.get(cache_key) if hours_ahead == 0 else None,
                mode="forecast" if hours_ahead > 0 else "current",
                hours_ahead=hours_ahead,
                resolved_location=bundle.resolved_location,
            )
            if hours_ahead == 0:
                self.current_scene_cache[cache_key] = scene
            return scene
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning("Using cached scene after weather error: %s", exc)
            cached_bundle = self.weather_bundle_cache.get(cache_key)
            if cached_bundle and (hours_ahead == 0 or cached_bundle.hourly):
                snapshot = self.select_hourly_snapshot(cached_bundle, hours_ahead)
                scene = build_scene(
                    snapshot,
                    self.current_scene_cache.get(cache_key) if hours_ahead == 0 else None,
                    mode="forecast" if hours_ahead > 0 else "current",
                    hours_ahead=hours_ahead,
                    resolved_location=cached_bundle.resolved_location,
                )
                scene.stale = True
                scene.source = f"{snapshot.source}-cache"
                if hours_ahead == 0:
                    self.current_scene_cache[cache_key] = scene
                return scene
            raise RuntimeError(f"Live weather unavailable and no cached weather exists for ZIP {zip_code}.") from exc
