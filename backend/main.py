"""FastAPI entrypoint and thin scene orchestration for Comfyday."""

from __future__ import annotations

import json
from hashlib import sha256
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware

from weather_service import WeatherSceneService, request_country_hint

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
MAX_FORECAST_HOURS = 168


load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Comfyday")
app.add_middleware(GZipMiddleware, minimum_size=500)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
scene_service = WeatherSceneService()


def static_asset_version() -> str:
    """Return a deploy-stable content version for static app shell assets."""
    digest = sha256()
    for path in (STATIC_DIR / "app.js", STATIC_DIR / "styles.css"):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def initial_scene_payload() -> dict[str, object]:
    """Provide non-media weather copy while the live weather scene loads."""
    last_updated = datetime.now(UTC).isoformat()
    return {
        "version": 0,
        "location_name": "San Francisco",
        "query": scene_service.default_query,
        "hours_ahead": 0,
        "temperature_f": 62.0,
        "feels_like_f": 62.0,
        "precip_probability_pct": 0,
        "description": "clear, sunny",
        "wind_label": "calm",
        "night": False,
        "outfit_note": "Classic SF layering weather.",
        "last_updated": last_updated,
        "base_image_url": None,
        "generated_image_url": None,
        "video_url": None,
        "layers": [],
    }


@app.middleware("http")
async def add_static_cache_headers(request: Request, call_next):
    """Give versioned static assets a cache lifetime for Lighthouse and repeat loads."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers.setdefault(
            "Cache-Control", "public, max-age=31536000, immutable"
        )
    return response


@app.get("/")
async def index(request: Request):
    """Render the frontend shell; weather is fetched before displaying an outfit."""
    initial_scene = initial_scene_payload()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "initial_scene": json.dumps(initial_scene),
            "inline_styles": (STATIC_DIR / "styles.css").read_text(encoding="utf-8"),
            "static_version": static_asset_version(),
        },
    )


@app.get("/api/scene")
async def get_scene(
    request: Request,
    hours_ahead: int = Query(default=0, ge=0, le=MAX_FORECAST_HOURS),
    query: str | None = Query(
        default=None, min_length=5, max_length=5, pattern=r"^\d{5}$"
    ),
):
    """Return the current or forecast scene payload."""
    try:
        return JSONResponse(
            (
                await scene_service.get_scene(
                    hours_ahead,
                    query=query,
                    country_hint=request_country_hint(dict(request.headers)),
                )
            ).to_dict()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
