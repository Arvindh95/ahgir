"""Face quality helpers used by indexing and matching.

The functions are dependency-light and safe to call from workers. They avoid
identity/demographic inference and only score image technical quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PIL import Image as PILImage


@dataclass(frozen=True)
class FaceQualityMetrics:
    face_min_side_px: float
    blur_score: float
    brightness_score: float
    crop_clipped: bool


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    avg = sum(values) / len(values)
    return sum((v - avg) ** 2 for v in values) / len(values)


def estimate_blur_score(image: PILImage.Image) -> float:
    """Return a simple sharpness score from grayscale neighbor differences.

    Higher is sharper. It is intentionally not a perfect CV metric; it is a
    cheap, deterministic quality signal that helps avoid over-trusting blurry
    indexed faces.
    """
    gray = image.convert("L").resize((64, 64))
    pixels = list(gray.getdata())
    diffs: list[float] = []
    width = 64
    for y in range(64):
        row = y * width
        for x in range(63):
            diffs.append(abs(float(pixels[row + x + 1]) - float(pixels[row + x])))
    for y in range(63):
        row = y * width
        next_row = (y + 1) * width
        for x in range(64):
            diffs.append(abs(float(pixels[next_row + x]) - float(pixels[row + x])))
    return _variance(diffs)


def estimate_brightness_score(image: PILImage.Image) -> float:
    gray = image.convert("L").resize((64, 64))
    pixels = list(gray.getdata())
    return float(sum(pixels) / max(1, len(pixels)))


def compute_face_quality_metrics(
    image: PILImage.Image,
    bbox: Sequence[float],
    crop_bbox: Sequence[float],
) -> FaceQualityMetrics:
    x_min, y_min, x_max, y_max = [float(v) for v in bbox[:4]]
    cx1, cy1, cx2, cy2 = [float(v) for v in crop_bbox[:4]]
    face_min_side_px = max(0.0, min(x_max - x_min, y_max - y_min))
    crop_clipped = cx1 <= 0 or cy1 <= 0 or cx2 >= image.width or cy2 >= image.height
    crop = image.crop((int(cx1), int(cy1), int(cx2), int(cy2)))
    return FaceQualityMetrics(
        face_min_side_px=face_min_side_px,
        blur_score=estimate_blur_score(crop),
        brightness_score=estimate_brightness_score(crop),
        crop_clipped=crop_clipped,
    )
