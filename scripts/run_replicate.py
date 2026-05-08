"""Run one fixed outfit through Replicate FLUX.2 Pro using simple image paths.

FLUX only receives:
    - prompt
    - input_images: list of image files

Required:
    uv sync --group generate

Env:
    REPLICATE_API_TOKEN=...
"""

from __future__ import annotations

import importlib
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import BinaryIO

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from outfit_logic import WEATHER_OUTFIT_PRESETS

RERUN_KEYS = ("cold_weather_and_dry",)
BASE_MODEL = Path("static/assets/base/girl-real-pose-front-left.png")
MODEL_VERSION = "black-forest-labs/flux-2-pro"

STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = STATIC_DIR / "generated" / "flux2"


def run_flux2_pro(prompt: str, image_paths: list[Path]) -> str:
    """Call Replicate FLUX.2 Pro and return the generated image URL."""
    replicate = importlib.import_module("replicate")
    replicate_error = importlib.import_module("replicate.exceptions").ReplicateError
    try:
        with ExitStack() as stack:
            image_files: list[BinaryIO] = [stack.enter_context(path.open("rb")) for path in image_paths]

            output = replicate.run(
                MODEL_VERSION,
                input={
                    "prompt": prompt,
                    "input_images": image_files,
                    "aspect_ratio": "2:3",
                    "resolution": "2 MP",
                    "output_format": "png",
                    "output_quality": 95,
                    "safety_tolerance": 2,
                },
            )
    except replicate_error as exc:
        detail = str(exc).strip()
        if "Insufficient credit" in detail or "status: 402" in detail:
            raise RuntimeError("Replicate billing blocked this FLUX.2 Pro run.") from exc
        raise
    return output[0] if isinstance(output, list) else str(output)


def get_prompt(weather_conditions: str) -> str:
    """Build the FLUX prompt for one weather-labeled outfit preset."""
    return f"""Image 1 is the ONLY human identity reference and must be preserved exactly. She is the model to dress and the person and image to preserve NO MATTER WHAT. This is the most important.

    This is an identity-preserving wardrobe edit, not a character redesign.
    The output person must look like the exact same full-height model from Image 1.

    You MUST preserve:
    - same face
    - same facial expression
    - same apparent age as Image 1: older teen / young adult, NOT a child
    - same hair
    - same body proportions
    - same height
    - same realistic full-body photography style
    - same identical pose
    - same identical camera angle
    - same identical facial features

    Do NOT, no matter what:
    - change her age
    - make her look like a kid
    - make her look younger or childlike
    - make her look older
    - change her face
    - change her body
    - change her height
    - make her shorter
    - shrink her limbs, torso, head-to-body ratio, or full-body proportions
    - stylize her into a different person

    Images 2 and onward are outfit and accessory references.

    Dress the older teen / young adult woman from Image 1 using the referenced outfit pieces.
    Layer garments naturally and appropriately for these San Francisco weather conditions:
    {weather_conditions.replace("_", " ")}

    Maintain accurate garment proportions:
    - oversized garments should remain proportionally oversized
    - baggy pants should remain baggy and floor length
    - garment silhouettes should match the referenced clothing images

    Some later images may be accessories to place naturally and realistically on the model.

    No changes should be made to how the human looks. Any other changes MUST:
    - be subtle, barely noticeable, and realistic
    - fit fashionable San Francisco streetwear styling
    - fit the weather conditions
    - NOT change the girl's identifying features, looks, age, facial structure, body, or height!!

    Generate:
    - one realistic full-body editorial fashion image
    - centered subject
    - natural hands
    - exact full-body proportions from Image 1
    - coherent layered outfit styling
    - no floating garments
    - no visible text labels
    - no collage layout
    - no additional or duplicate people

    Background:
    plain white seamless studio background.

    Output:
    clean full-body PNG-style cutout render suitable for later background removal or compositing."""


def load_replicate_token() -> str:
    """Load the Replicate token from env or the local `.env` fallback."""
    token = os.environ.get("REPLICATE_API_TOKEN") or os.environ.get("COMFY_REPLICATE_API_KEY")
    if not token and (BASE_DIR / ".env").exists():
        for line in (BASE_DIR / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("COMFY_REPLICATE_API_KEY="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not token:
        raise RuntimeError("Set COMFY_REPLICATE_API_KEY or REPLICATE_API_TOKEN before running Replicate.")
    return token


def build_jobs() -> list[dict[str, object]]:
    """Build FLUX rerun jobs from the hardcoded temporary preset subset."""
    return [
        {
            "weather_conditions": weather_conditions,
            "prompt": get_prompt(weather_conditions),
            "input_images": [BASE_DIR / BASE_MODEL, *(BASE_DIR / path for path in image_list)],
            "output_path": OUTPUT_DIR / f"{weather_conditions}.png",
        }
        for weather_conditions, image_list in (
            (weather_conditions, WEATHER_OUTFIT_PRESETS[weather_conditions]) for weather_conditions in RERUN_KEYS
        )
    ]


def validate_job_assets() -> None:
    """Fail before a paid API call if any local input image is missing."""
    jobs = build_jobs()
    if not jobs:
        raise RuntimeError("No failed FLUX outfit presets are hardcoded for rerun.")
    missing = [str(path) for job in jobs for path in job["input_images"] if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing local assets for Replicate job: {', '.join(missing)}")


def main() -> None:
    """Rerun the hardcoded failed FLUX outfit presets and save generated images."""
    os.environ["REPLICATE_API_TOKEN"] = load_replicate_token()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    validate_job_assets()

    for job in build_jobs():
        output_url = run_flux2_pro(str(job["prompt"]), job["input_images"])
        requests = importlib.import_module("requests")
        response = requests.get(output_url, timeout=300)
        response.raise_for_status()
        job["output_path"].write_bytes(response.content)


if __name__ == "__main__":
    main()
