"""Tests for the Replicate FLUX outfit batch script."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_replicate as script


class ReplicateOneOutfitTests(unittest.TestCase):
    """Keep the FLUX batch script deterministic and import-safe."""

    def test_validate_job_assets_accepts_current_presets(self) -> None:
        """Every preset job should reference existing local input files."""
        script.validate_job_assets()

    def test_build_jobs_uses_base_model_plus_preset_images(self) -> None:
        """Each FLUX job should include the base model followed by outfit refs."""
        jobs = script.build_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(
            {job["weather_conditions"] for job in jobs},
            {"cold_weather_and_dry"},
        )
        first = jobs[0]
        self.assertIn("weather_conditions", first)
        self.assertIn("prompt", first)
        self.assertGreaterEqual(len(first["input_images"]), 2)
        self.assertEqual(first["input_images"][0], script.BASE_DIR / script.BASE_MODEL)
        self.assertTrue(str(first["output_path"]).endswith(".png"))

    def test_load_replicate_token_strips_quotes_from_plain_env_fallback(self) -> None:
        """Quoted fallback env values should be normalized before use."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".env").write_text('COMFY_REPLICATE_API_KEY="r8_test_token"\n', encoding="utf-8")
            with patch.dict("os.environ", {}, clear=True), patch.object(script, "BASE_DIR", Path(tmp)):
                token = script.load_replicate_token()
        self.assertEqual(token, "r8_test_token")

    def test_billing_error_is_raised_as_clear_runtime_error(self) -> None:
        """Billing failures should surface as an actionable runtime error."""

        class FakeReplicateError(Exception):
            pass

        fake_replicate = SimpleNamespace(
            run=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                FakeReplicateError("status: 402\nInsufficient credit")
            )
        )
        fake_exceptions = SimpleNamespace(ReplicateError=FakeReplicateError)

        def fake_import(name: str):
            if name == "replicate":
                return fake_replicate
            if name == "replicate.exceptions":
                return fake_exceptions
            raise ModuleNotFoundError(name)

        with patch.object(script.importlib, "import_module", side_effect=fake_import):
            with self.assertRaisesRegex(RuntimeError, "Replicate billing blocked this FLUX.2 Pro run"):
                script.run_flux2_pro("prompt", [Path(__file__)])


if __name__ == "__main__":
    unittest.main()
