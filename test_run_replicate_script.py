"""No-network checks for the optional FLUX generation helper."""

from __future__ import annotations

from scripts.run_replicate import BASE_DIR, MODEL_VERSION, OUTPUT_DIR, RERUN_KEYS, build_jobs, get_prompt
import pytest


def test_replicate_jobs_are_local_file_safe() -> None:
    """Generation jobs should be valid before any paid Replicate call happens."""
    if not (BASE_DIR / "static/assets/base/girl-real-pose-front-left.png").exists():
        pytest.skip("private base/outfit assets are not included in the public-safe repo")
    jobs = build_jobs()
    if not RERUN_KEYS:
        assert jobs == []
        return
    assert len(jobs) == len(RERUN_KEYS)
    for job in jobs:
        assert str(job["weather_conditions"]) in RERUN_KEYS
        assert str(job["prompt"]).startswith("Image 1 is the ONLY human identity reference")
        assert job["output_path"].parent == OUTPUT_DIR
        for image_path in job["input_images"]:
            assert image_path.is_absolute()
            assert image_path.exists(), f"missing input image: {image_path.relative_to(BASE_DIR)}"
            assert image_path.stat().st_size > 0


def test_flux_prompt_and_model_keep_identity_guardrails() -> None:
    """The helper should keep using FLUX.2 Pro with strict identity-preservation wording."""
    prompt = get_prompt("48_to_50_dry_cold")
    assert MODEL_VERSION == "black-forest-labs/flux-2-pro"
    assert "same apparent age as Image 1" in prompt
    assert "NOT a child" in prompt
    assert "48 to 50 dry cold" in prompt
