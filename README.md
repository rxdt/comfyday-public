# 🌈 Comfyday 🌦️

**[TRY IT ON HERE](https://comfyday.vercel.app/)**

### 💜💛💙💚❤️ For Saoirse 💜💛💙💚❤️

> **A tiny weather-to-outfit app for “what do I wear right now?” days**

![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-weather_API-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Vanilla JS](https://img.shields.io/badge/Vanilla_JS-frontend-F7DF1E?style=for-the-badge&logo=javascript&logoColor=111)
![FLUX](https://img.shields.io/badge/FLUX-static_outfits-ff69b4?style=for-the-badge)
![Status](https://img.shields.io/badge/status-public_demo-8A2BE2?style=for-the-badge)

Comfyday checks the weather for a 5-digit ZIP code, interprets the weather, maps it to a pre-generated FLUX outfit image, and renders one fixed model responsively.

## ✨ What It Does ✨

| Feature                              | Why It Matters                                                                 |
| ------------------------------------ | ------------------------------------------------------------------------------ |
| 🌦️ Kid-created weather-aware outfits | Uses current/forecast weather instead of a fixed outfit.                       |
| 📍 ZIP code input                    | Enter a 5-digit ZIP and check weather up to 24 hours ahead.                    |
| 🌍 Country-aware ZIP tie-breaks      | Ambiguous postal codes will infer the request country from deployment headers. |
| 🧊 Tight SF-style temp buckets       | Most logic is tuned around the common `50s-70s°F` range.                       |
| 💨 Provider-based wind/fog/rain      | No fake weather guesses; provider data drives outfit changes.                  |
| 🖼️ Static generated looks            | Runtime is fast because it only selects pre-rendered images.                   |
| 📱 Responsive frontend               | Built to fit the model + text on desktop and mobile.                           |

## Example 📸

<div align="center">

https://github.com/user-attachments/assets/3569cfbf-7bab-47b1-952c-5ed838b03bcb

</div>

## 🐸 Kid and Parent Friendly Instructions

## 🧃 Recreate This Website 🧥 _**stop reminding your kid to wear a jacket**_

1. Open Terminal 💻
2. Get the code:

```bash
git clone https://github.com/YOUR_USERNAME/comfyday.git
cd comfyday
```

3. Install the app:
   `uv sync`
4. Get weather API keys:

- Make a (Tomorrow.io)[https://www.tomorrow.io/] account and copy an API key.
- Fallback: make a (Weatherstack)[https://docs.apilayer.com/weatherstack/docs/quickstart-guide#step-1-get-your-api-access-key] account and copy an API key.

5. Create `.env` file in codebase with your keys:

```bash
TOMORROW_API_KEY="WEATHERSTACK_API_KEY_value"
WEATHERSTACK_API_KEY="WEATHERSTACK_API_KEY_value"
COMFY_REPLICATE_API_KEY="how-to-get instructions below"
```

6. Run it on your laptop `uv run fastapi dev main.py`
7. Open in the browser `http://localhost:8000`
8. 🖼️ Now - Image generation 🖌️:
   - Go to [Replicate FLUX.2 Pro](https://replicate.com/black-forest-labs/flux-2-pro)
   - Create a Replicate API key in the developer dashboard
   - Add the value of `COMFY_REPLICATE_API_KEY=...` to your new file `.env` in your codebase
   - upload yourself as the first image, 6-7 as the other images (clothes)
   - Run `uv run --group generate python scripts/run_replicate.py`.

- Repeat until yu have enough images for the `TEMPERATURE_BUCKETS` you want in (outfit_logic.py)[outfit_logic.py]

## 🛠️ Run on your laptop 🖥️

```bash
uv sync
uv run fastapi dev main.py
```

Open:

```text
http://localhost:8000
```

## 🔁 Runtime Flow

```text
ZIP code + hours ahead
  -> weather_api.py
  -> outfit_logic.py outfit preset selection [ ADD YOUR OUTFIT REFERENCES HERE ]
  -> frontend renders
```

## 🌁 SF Outfit Logic

San Francisco usually lives in the `52-72°F` band, with `63°F` as the classic “bring a layer” center. Comfyday uses provider truth first, then chooses a generated outfit:

1. Blend real temp and feels-like temp
2. Adjust for real provider signals: sun, clouds, fog, rain, and wind 🌧️
3. Pick a dry outfit from temp buckets that are tightest around `62-64°F` 🌤️
4. If rain/snow/active precip is present, route to a wet-safe outfit by temp. 💧

## 🧪 Tests

```bash
uv sync --group dev
PYTHONPATH=. uv run pytest -q
```

🎨 Record live integration fixtures once:

```bash
COMFY_RECORD_INTEGRATION=1 PYTHONPATH=. uv run pytest -q tests/test_integration_weather.py -s
```

## 💅 Why Static Images?

Runtime clothing overlays are brittle, expensive, and look fake. The current version pre-generates complete outfits and lets the app pick the right render for the weather.
