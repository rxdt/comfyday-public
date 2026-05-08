"""Weather/geocoding orchestration and scene caching for the Comfyday backend."""

from __future__ import annotations

import logging
import math
import os
import re
from datetime import timedelta
from typing import Any

import httpx

from backend_models import ForecastBundle, LocationRecord, SceneState, WeatherSnapshot
from scene_builder import build_scene
from weather_api import explain_weather_provider_failure, fetch_tomorrow_bundle, fetch_weatherstack_bundle

logger = logging.getLogger("comfyday")

MAX_FORECAST_HOURS = 24
LAT_LON_PAIR_RE = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")

SF_NEIGHBORHOOD_ALIASES: dict[str, tuple[str, ...]] = {
    "outer sunset": ("Outer Sunset, San Francisco, California", "Sunset District, San Francisco, California"),
    "inner sunset": ("Inner Sunset, San Francisco, California", "Sunset District, San Francisco, California"),
    "outer richmond": ("Outer Richmond, San Francisco, California", "Richmond District, San Francisco, California"),
    "inner richmond": ("Inner Richmond, San Francisco, California", "Richmond District, San Francisco, California"),
    "fidi": ("Financial District, San Francisco, California",),
    "soma": ("South of Market, San Francisco, California",),
    "mission bay": ("Mission Bay, San Francisco, California",),
    "mission district": ("Mission District, San Francisco, California",),
    "outer mission": ("Outer Mission, San Francisco, California",),
    "haight": ("Haight-Ashbury, San Francisco, California",),
    "lower haight": ("Lower Haight, San Francisco, California",),
    "pac heights": ("Pacific Heights, San Francisco, California",),
    "nopa": ("NoPa, San Francisco, California", "North of the Panhandle, San Francisco, California"),
    "noe valley": ("Noe Valley, San Francisco, California",),
    "cow hollow": ("Cow Hollow, San Francisco, California",),
    "dogpatch": ("Dogpatch, San Francisco, California",),
    "potrero": ("Potrero Hill, San Francisco, California",),
    "marina": ("Marina District, San Francisco, California",),
    "presidio": ("Presidio, San Francisco, California",),
}

SF_NEIGHBORHOOD_CENTROIDS: dict[str, tuple[str, float, float]] = {
    "outer sunset": ("Outer Sunset, San Francisco, California", 37.7542, -122.4943),
    "inner sunset": ("Inner Sunset, San Francisco, California", 37.7627, -122.4662),
    "outer richmond": ("Outer Richmond, San Francisco, California", 37.7790, -122.4948),
    "inner richmond": ("Inner Richmond, San Francisco, California", 37.7808, -122.4729),
    "fidi": ("Financial District, San Francisco, California", 37.7946, -122.3999),
    "soma": ("South of Market, San Francisco, California", 37.7786, -122.4056),
    "nopa": ("NoPa, San Francisco, California", 37.7749, -122.4375),
    "mission bay": ("Mission Bay, San Francisco, California", 37.7702, -122.3916),
    "mission district": ("Mission District, San Francisco, California", 37.7599, -122.4148),
    "outer mission": ("Outer Mission, San Francisco, California", 37.7244, -122.4420),
    "haight": ("Haight-Ashbury, San Francisco, California", 37.7691, -122.4481),
    "lower haight": ("Lower Haight, San Francisco, California", 37.7725, -122.4308),
    "pac heights": ("Pacific Heights, San Francisco, California", 37.7924, -122.4382),
    "noe valley": ("Noe Valley, San Francisco, California", 37.7502, -122.4337),
    "cow hollow": ("Cow Hollow, San Francisco, California", 37.7987, -122.4360),
    "dogpatch": ("Dogpatch, San Francisco, California", 37.7596, -122.3880),
    "potrero": ("Potrero Hill, San Francisco, California", 37.7595, -122.3977),
    "marina": ("Marina District, San Francisco, California", 37.8037, -122.4368),
    "presidio": ("Presidio, San Francisco, California", 37.7989, -122.4662),
}


def parse_lat_lon_pair(raw: str) -> tuple[float, float] | None:
    """Parse a `lat,lon` string if the query is coordinate-based."""
    match = LAT_LON_PAIR_RE.match(raw.strip())
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    return (lat, lon) if (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0) else None


def _in_sf_microclimate_bbox(lat: float, lon: float) -> bool:
    """Return whether a coordinate falls in the SF peninsula microclimate box."""
    return 37.70 <= lat <= 37.84 and -122.53 <= lon <= -122.35


def looks_like_sf_neighborhood(query: str) -> bool:
    """Return whether a query looks like a specific SF neighborhood."""
    lowered = query.strip().lower()
    return any(
        token in lowered
        for token in ("sunset", "richmond", "mission", "marina", "noe", "castro", "haight", "soma", "dogpatch", "potrero", "presidio", "outer ", "inner ")
    )


def score_geocode_candidate(user_query: str, result: dict[str, Any]) -> float:
    """Prefer exact-name, local, and SF-bbox geocode candidates."""
    normalized = user_query.strip().lower()
    tokens = [token for token in re.split(r"[\s,]+", normalized) if len(token) >= 3]
    score = math.log(max(int(result.get("population") or 0), 1)) * 2.5
    name = str(result.get("name") or "").lower()
    admin1 = str(result.get("admin1") or "").lower()
    admin2 = str(result.get("admin2") or "").lower()
    admin3 = str(result.get("admin3") or "").lower()
    country = str(result.get("country") or "").lower()
    if normalized == name:
        score += 500
    elif name and normalized in name:
        score += 280
    elif name and name in normalized:
        score += 160
    name_words = set(name.split()) if name else set()
    for token in tokens:
        if token in name_words:
            score += 100
        if token in admin3:
            score += 110
        if token in admin2:
            score += 95
        if token in admin1:
            score += 40
    lat = float(result["latitude"])
    lon = float(result["longitude"])
    if _in_sf_microclimate_bbox(lat, lon):
        if any(hint in normalized for hint in ("san francisco", "941", "sunset", "mission", "marina", "richmond", "presidio", "haight", "potrero", "dogpatch")):
            score += 130
        score += 28
    if "california" in admin1:
        score += 22
    if country in {"united states", "usa", "us"}:
        score += 12
    return score


def pick_best_geocode_result(user_query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the highest-confidence geocode row from a candidate list."""
    if not results:
        raise RuntimeError(f"Could not find a location for '{user_query}'.")
    return max(results, key=lambda row: score_geocode_candidate(user_query, row))


def sf_query_candidates(query: str) -> list[str]:
    """Expand likely SF-neighborhood queries into better geocoder attempts."""
    cleaned = " ".join(query.strip().split())
    lowered = cleaned.casefold()
    candidates: list[str] = []
    seen: set[str] = set()
    for alias, expansions in SF_NEIGHBORHOOD_ALIASES.items():
        if alias in lowered:
            for expanded in expansions:
                if expanded.casefold() not in seen:
                    seen.add(expanded.casefold())
                    candidates.append(expanded)
    if lowered not in seen:
        seen.add(lowered)
        candidates.append(cleaned)
    if looks_like_sf_neighborhood(cleaned):
        for suffix in (
            f"{cleaned}, San Francisco, California",
            f"{cleaned}, SF, CA",
            f"{cleaned}, San Francisco County, California",
        ):
            if suffix.casefold() not in seen:
                seen.add(suffix.casefold())
                candidates.append(suffix)
    return candidates


def sf_centroid_record(query: str) -> LocationRecord | None:
    """Return a hardcoded SF centroid when public geocoders collapse a neighborhood away."""
    lowered = " ".join(query.strip().split()).casefold()
    for alias, (display_name, lat, lon) in SF_NEIGHBORHOOD_CENTROIDS.items():
        if alias in lowered:
            return LocationRecord(
                query=query,
                display_name=display_name,
                latitude=lat,
                longitude=lon,
                timezone="America/Los_Angeles",
                country="United States",
                country_code="US",
                admin1="California",
                admin2="San Francisco County",
                geocoder="sf-centroid-fallback",
                tomorrow_location=f"{lat},{lon}",
            )
    return None


def concise_location_label(
    primary: str | None,
    *,
    admin2: str | None = None,
    admin1: str | None = None,
    country: str | None = None,
    query: str | None = None,
) -> str:
    """Reduce verbose provider/geocoder labels into concise frontend labels."""
    primary_clean = (primary or "").strip()
    query_clean = (query or "").strip()
    if not primary_clean:
        return query_clean
    parts = [part.strip() for part in primary_clean.split(",") if part.strip()]
    first = parts[0] if parts else primary_clean
    in_sf = "san francisco" in first.casefold() or "san francisco" in (admin2 or "").casefold()
    if in_sf and query_clean and looks_like_sf_neighborhood(query_clean):
        return f"{query_clean.title()}, San Francisco"
    if in_sf and query_clean and query_clean.casefold() != "san francisco":
        return f"{query_clean}, San Francisco"
    if in_sf and "san francisco" not in first.casefold():
        return f"{first}, San Francisco"
    if in_sf:
        return "San Francisco"
    if len(parts) >= 2 and parts[1].casefold() not in {"california", "united states"}:
        return f"{first}, {parts[1]}"
    if admin1 and admin1.casefold() != "california":
        return f"{first}, {admin1}"
    if country and country.casefold() != "united states":
        return f"{first}, {country}"
    return first


def nominatim_payload_to_geo(lat: float, lon: float, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Nominatim payload into the internal geocode row shape."""
    addr = payload.get("address") or {}
    name = (
        addr.get("neighbourhood")
        or addr.get("suburb")
        or addr.get("quarter")
        or addr.get("city_district")
        or addr.get("town")
        or addr.get("city")
        or addr.get("village")
        or addr.get("hamlet")
        or (payload.get("display_name") or "").split(",")[0].strip()
        or f"{lat:.4f}, {lon:.4f}"
    )
    cc = addr.get("country_code")
    return {
        "latitude": lat,
        "longitude": lon,
        "name": name,
        "admin3": addr.get("borough") or addr.get("city_district"),
        "admin2": addr.get("county"),
        "admin1": addr.get("state"),
        "country": addr.get("country"),
        "country_code": cc.upper() if isinstance(cc, str) else None,
        "timezone": None,
    }


def nominatim_search_payload_to_geo(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a Nominatim search result row when it includes coordinates."""
    try:
        return nominatim_payload_to_geo(float(payload["lat"]), float(payload["lon"]), payload)
    except (KeyError, TypeError, ValueError):
        return None


class WeatherSceneService:
    """Fetch weather, cache normalized scenes, and build FLUX-static outfit payloads."""

    def __init__(self) -> None:
        """Initialize provider credentials and in-memory scene caches."""
        self.default_query = os.getenv("WEATHER_QUERY", os.getenv("TOMORROW_LOCATION", os.getenv("WEATHERSTACK_QUERY", "94110")))
        self.tomorrow_api_key = os.getenv("TOMORROW_API_KEY", "").strip()
        self.weatherstack_api_key = os.getenv("WEATHERSTACK_API_KEY", "").strip()
        self.current_scene_cache: dict[str, SceneState] = {}
        self.weather_bundle_cache: dict[str, ForecastBundle] = {}

    async def geocode_search_many(self, client: httpx.AsyncClient, query: str, *, count: int = 20) -> list[dict[str, Any]]:
        """Query Open-Meteo geocoding for multiple structured candidate rows."""
        response = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": count, "language": "en", "format": "json"},
        )
        response.raise_for_status()
        return list((response.json() or {}).get("results") or [])

    async def reverse_geocode_nominatim(self, client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any] | None:
        """Reverse-geocode coordinates into a label-rich place row."""
        response = await client.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": "Comfyday/1.0 (local weather UI; +https://openstreetmap.org/copyright)", "Accept-Language": "en"},
        )
        response.raise_for_status()
        payload = response.json()
        return None if not isinstance(payload, dict) or payload.get("error") else nominatim_payload_to_geo(lat, lon, payload)

    async def search_nominatim(self, client: httpx.AsyncClient, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        """Search Nominatim when Open-Meteo geocoding misses a neighborhood."""
        response = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "jsonv2", "addressdetails": 1, "limit": limit},
            headers={"User-Agent": "Comfyday/1.0 (local weather UI; +https://openstreetmap.org/copyright)", "Accept-Language": "en"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return [geo for row in payload if isinstance(row, dict) and (geo := nominatim_search_payload_to_geo(row))]

    def location_from_geo(self, query: str, geo: dict[str, Any]) -> LocationRecord:
        """Convert a normalized geocode row into the backend location record."""
        ordered: list[str] = []
        seen: set[str] = set()
        for key in ("name", "admin3", "admin2", "admin1", "country"):
            value = str(geo.get(key) or "").strip()
            if value and value not in seen:
                seen.add(value)
                ordered.append(value)
        return LocationRecord(
            query=query,
            display_name=concise_location_label(", ".join(ordered) if ordered else query, admin2=str(geo.get("admin2") or ""), admin1=str(geo.get("admin1") or ""), country=str(geo.get("country") or ""), query=query),
            latitude=float(geo["latitude"]),
            longitude=float(geo["longitude"]),
            timezone=geo.get("timezone"),
            country=geo.get("country"),
            country_code=geo.get("country_code"),
            admin1=geo.get("admin1"),
            admin2=geo.get("admin2"),
            geocoder="open-meteo-search-v1",
            tomorrow_location=f"{float(geo['latitude'])},{float(geo['longitude'])}",
        )

    async def resolve_weather_location(self, client: httpx.AsyncClient, query: str) -> LocationRecord:
        """Resolve one freeform place string into provider-ready weather coordinates."""
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("Empty location query.")
        coords = parse_lat_lon_pair(cleaned)
        if coords is not None:
            lat, lon = coords
            reverse = await self.reverse_geocode_nominatim(client, lat, lon)
            if reverse:
                meta = self.location_from_geo(cleaned, reverse)
                return LocationRecord(query=cleaned, display_name=meta.display_name, latitude=lat, longitude=lon, timezone=meta.timezone, country=meta.country, country_code=meta.country_code, admin1=meta.admin1, admin2=meta.admin2, geocoder="nominatim-reverse", tomorrow_location=f"{lat},{lon}")
            return LocationRecord(query=cleaned, display_name=f"{lat:.4f}, {lon:.4f}", latitude=lat, longitude=lon, timezone=None, country=None, country_code=None, admin1=None, admin2=None, geocoder="coordinates-only", tomorrow_location=f"{lat},{lon}")
        attempts = sf_query_candidates(cleaned)
        aggregated: list[dict[str, Any]] = []
        for attempt in attempts:
            aggregated.extend(await self.geocode_search_many(client, attempt))
        if not aggregated:
            for attempt in attempts:
                aggregated.extend(await self.search_nominatim(client, attempt))
        if not aggregated:
            centroid = sf_centroid_record(cleaned)
            if centroid:
                return centroid
            raise RuntimeError(f"Could not find a location for '{cleaned}'.")
        sf_rows = [row for row in aggregated if _in_sf_microclimate_bbox(float(row["latitude"]), float(row["longitude"]))]
        if looks_like_sf_neighborhood(cleaned) and sf_rows:
            aggregated = sf_rows
        return self.location_from_geo(cleaned, pick_best_geocode_result(cleaned, aggregated))

    async def resolve_location(self, query: str) -> LocationRecord:
        """Resolve one location query without fetching weather."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await self.resolve_weather_location(client, query.strip())

    async def fetch_weather_bundle(self, query: str, *, hours_ahead: int) -> ForecastBundle:
        """Fetch weather using Tomorrow.io first, then Weatherstack fallback."""
        tomorrow_exc: BaseException | None = None
        async with httpx.AsyncClient(timeout=12.0) as client:
            loc = await self.resolve_weather_location(client, query.strip())
            if self.tomorrow_api_key:
                try:
                    return await fetch_tomorrow_bundle(client, loc, api_key=self.tomorrow_api_key, hours_ahead=hours_ahead)
                except Exception as exc:
                    tomorrow_exc = exc
                    logger.warning("Tomorrow.io failed (%s); trying Weatherstack.", explain_weather_provider_failure(exc))
            if self.weatherstack_api_key:
                try:
                    return await fetch_weatherstack_bundle(
                        client,
                        loc,
                        api_key=self.weatherstack_api_key,
                        concise_location_label=concise_location_label,
                        max_forecast_hours=MAX_FORECAST_HOURS,
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

    async def get_scene(self, hours_ahead: int = 0, query: str | None = None) -> SceneState:
        """Return the current or forecast scene for one location query."""
        cleaned_query = (query or "").strip() or self.default_query
        cache_key = cleaned_query.casefold()
        try:
            bundle = await self.fetch_weather_bundle(cleaned_query, hours_ahead=hours_ahead)
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
            logger.warning("Using cached or demo scene after weather error: %s", exc)
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
            raise RuntimeError(f"Live weather unavailable and no cached weather exists for {cleaned_query}.") from exc
