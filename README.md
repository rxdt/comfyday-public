# Comfyday

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-runtime-009688)
![Status](https://img.shields.io/badge/status-demo--ready-brightgreen)

Weather-aware outfit demo for San Francisco microclimates. The app fetches weather for a ZIP/place, maps it to a pre-generated FLUX outfit image, and renders one fixed model responsively.

![Comfyday screenshot](docs/app-screenshot.png)

## What It Uses

| Layer | Elements |
| --- | --- |
| Backend | `FastAPI`, `Jinja2`, static file serving |
| Weather | Tomorrow.io first, Weatherstack fallback, cached/demo fallback |
| Logic | `outfit_logic.py` temperature/rain/night/microclimate mapping |
| Images | pre-generated FLUX renders in `static/generated/flux2/` |
| Frontend | vanilla JS + responsive CSS |
| Generation ops | optional `scripts/run_replicate.py` for rerunning bad FLUX outputs |

## Runtime Flow

```text
ZIP/place + hours ahead
  -> weather_service.py
  -> weather_api.py provider normalization
  -> outfit_logic.py preset selection
  -> scene_builder.py one-image scene
  -> frontend renders /static/generated/flux2/<preset>.png
```

No runtime clothing compositing. No model inference in the app. The shipped app selects from static generated outfit images.

## Run Locally

```bash
uv sync
uv run fastapi dev main.py
```

Open `http://localhost:8000`.

Optional `.env`:

```bash
WEATHER_QUERY=94110
TOMORROW_API_KEY=...
WEATHERSTACK_API_KEY=...
COMFY_REPLICATE_API_KEY=...
```

## Tests

```bash
uv sync --group dev
PYTHONPATH=. uv run pytest -q
```

Current coverage checks API contracts, provider normalization, weather edge cases, generated-image coverage, and FLUX rerun-script safety.

## Regenerate A Bad Outfit

```bash
uv sync --group generate
uv run --group generate python scripts/run_replicate.py
```

Edit `RERUN_KEYS` and `get_prompt()` in `scripts/run_replicate.py` before running. Outputs are written to `static/generated/flux2/`.
