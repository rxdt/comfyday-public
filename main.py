"""FastAPI entrypoint and thin scene orchestration for Comfyday."""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from weather_service import WeatherSceneService

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
MAX_FORECAST_HOURS = 24


load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Comfyday")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
scene_service = WeatherSceneService()


@app.get("/")
async def index(request: Request):
    """Render the frontend shell; weather is fetched before displaying an outfit."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "initial_scene": json.dumps({"hours_ahead": 0, "query": scene_service.default_query}),
            "max_forecast_hours": MAX_FORECAST_HOURS,
        },
    )


@app.get("/api/scene")
async def get_scene(
    hours_ahead: int = Query(default=0, ge=0, le=MAX_FORECAST_HOURS),
    query: str | None = Query(default=None, min_length=1, max_length=120),
):
    """Return the current or forecast scene payload."""
    try:
        return JSONResponse((await scene_service.get_scene(hours_ahead, query=query)).to_dict())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/locations")
async def resolve_locations(q: str = Query(..., min_length=1, max_length=200)):
    """Resolve a freeform place string to coordinates and concise labels."""
    try:
        return JSONResponse((await scene_service.resolve_location(q)).to_dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
