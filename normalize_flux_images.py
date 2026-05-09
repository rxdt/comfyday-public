"""Normalize generated FLUX outfit PNGs onto one portrait canvas for stable UI scale."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

CANVAS_SIZE = (768, 1415)
TARGET_SUBJECT_HEIGHT = 1372
WHITE = (255, 255, 255)


def subject_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Find the non-white subject bounds in a generated studio PNG."""
    diff = ImageChops.difference(image.convert("RGB"), Image.new("RGB", image.size, WHITE)).convert("L")
    return diff.point(lambda value: 255 if value > 12 else 0).getbbox()


def normalize_image(path: Path) -> bool:
    """Center one image with a consistent subject height and white portrait canvas."""
    image = Image.open(path).convert("RGB")
    bbox = subject_bbox(image)
    if not bbox:
        return False

    subject_width = bbox[2] - bbox[0]
    subject_height = bbox[3] - bbox[1]
    scale = min(TARGET_SUBJECT_HEIGHT / subject_height, (CANVAS_SIZE[0] - 24) / subject_width)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    scaled_bbox = tuple(round(value * scale) for value in bbox)

    canvas = Image.new("RGB", CANVAS_SIZE, WHITE)
    paste_x = (CANVAS_SIZE[0] - (scaled_bbox[2] - scaled_bbox[0])) // 2 - scaled_bbox[0]
    paste_y = 18 - scaled_bbox[1]
    canvas.paste(resized, (paste_x, paste_y))
    canvas.save(path, optimize=True)
    return True


def main() -> None:
    """Normalize every generated outfit image in-place."""
    for path in sorted(Path("static/generated/flux2").glob("*.png")):
        if normalize_image(path):
            print(path)


if __name__ == "__main__":
    main()
