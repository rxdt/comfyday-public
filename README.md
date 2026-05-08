# 🌈 Comfyday

> **A tiny weather-to-outfit app for “what do I wear right now?” days.**

![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-weather_API-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Vanilla JS](https://img.shields.io/badge/Vanilla_JS-frontend-F7DF1E?style=for-the-badge&logo=javascript&logoColor=111)
![FLUX](https://img.shields.io/badge/FLUX-static_outfits-ff69b4?style=for-the-badge)
![Status](https://img.shields.io/badge/status-public_demo-8A2BE2?style=for-the-badge)

Comfyday checks the weather for a ZIP/place, interprets the conditions, and chooses a pre-generated outfit image that fits the moment.

```text
weather now + hours ahead
        ↓
temperature / feels-like / rain / fog / wind
        ↓
outfit preset key
        ↓
static FLUX image
```

## ✨ What It Does

| Feature | Why It Matters |
| --- | --- |
| 🌦️ Weather-aware outfits | Uses current/forecast weather instead of a fixed outfit. |
| 🧊 Tight SF-style temp buckets | Most logic is tuned around the common `50s-70s°F` range. |
| 💨 Provider-based wind/fog/rain | No fake weather guesses; provider data drives outfit changes. |
| 🖼️ Static generated looks | Runtime is fast because it only selects pre-rendered images. |
| 📱 Responsive frontend | Built to fit the model + text on desktop and mobile. |

## 📸 Screenshot

This public repo intentionally excludes private generated model images. In the private deploy repo, this section shows a real app screenshot.

```text
┌─────────────────────────────────────┐
│              outfit image           │
│                                     │
│         Current weather in 94110     │
│       53° · 0% rain · night · windy  │
│       Low 50s; use a real layer      │
└─────────────────────────────────────┘
```

## 🧠 Architecture

```text
main.py
  FastAPI routes + static frontend

weather_service.py
  geocoding, provider selection, caching

weather_api.py
  Tomorrow.io / Weatherstack normalization

outfit_logic.py
  weather → preset key

scene_builder.py
  final scene payload for the browser

static/app.js + static/styles.css
  tiny frontend renderer
```

## 🚫 What This Public Demo Excludes

The real deployment uses private generated images in:

```text
static/generated/flux2/
```

Those files are excluded here because they are private personal images. This public repo is for reviewing the app structure, weather logic, tests, and deployment shape.

## 🛠️ Run Locally

```bash
uv sync
uv run fastapi dev main.py
```

Open:

```text
http://localhost:8000
```

Create a local `.env`:

```bash
TOMORROW_API_KEY=...
WEATHERSTACK_API_KEY=...
```

## 🧪 Tests

```bash
uv sync --group dev
PYTHONPATH=. uv run pytest -q
```

Note: image-coverage tests expect private generated images. For the public repo, either add safe placeholder images or skip those private-asset checks.

## 🎨 Regenerating Outfit Images

The private workflow uses Replicate/FLUX to regenerate static outfit images:

```bash
uv sync --group generate
uv run --group generate python scripts/run_replicate.py
```

Runtime does **not** call FLUX. The app only serves static outfit renders.

## 💅 Why Static Images?

Early versions tried runtime clothing overlays. That was brittle: scale, pose, hands, hair, and occlusion made outfits look fake. The current version pre-generates complete outfits and lets the app pick the right render for the weather.

```text
less magic at runtime
more reliable outfit results
faster page loads
```
