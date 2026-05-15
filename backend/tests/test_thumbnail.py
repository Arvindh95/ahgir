"""Thumbnail generator regression tests.

P2 fix (P2 finding 2026-05-15): the old generator derived height from
``target_width * aspect_ratio`` without capping the second dimension.
A very tall image under the 50MP cap could still allocate enormous
output (e.g. 512 × 9000 → ~14 MB just for one thumbnail). The new
``generate_thumbnail`` uses ``img.thumbnail((N, N))`` which bounds
BOTH sides. These tests prove every extreme aspect ratio stays inside
the box.
"""
from io import BytesIO

import pytest
from PIL import Image as PILImage

from app.utils.thumbnail import generate_thumbnail


def _jpeg_bytes(width: int, height: int) -> bytes:
    img = PILImage.new("RGB", (width, height), (128, 128, 128))
    out = BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


@pytest.mark.parametrize(
    "src_w,src_h",
    [
        (8000, 200),    # extreme wide panorama
        (200, 8000),    # extreme tall strip
        (4000, 4000),   # square within MP cap
        (200, 200),     # small (must not upscale)
        (1024, 768),    # standard 4:3
    ],
)
def test_thumbnail_stays_within_bounding_box(src_w, src_h):
    """Every output dimension <= 512 regardless of source aspect ratio."""
    src = _jpeg_bytes(src_w, src_h)
    thumb_bytes = generate_thumbnail(src, target_size=512)

    thumb = PILImage.open(BytesIO(thumb_bytes))
    assert thumb.width <= 512
    assert thumb.height <= 512


def test_thumbnail_never_upscales_small_images():
    """A 200x200 source stays 200x200 — Pillow.thumbnail() refuses to
    upscale and we rely on that for the never-upscale guarantee."""
    src = _jpeg_bytes(200, 200)
    thumb_bytes = generate_thumbnail(src, target_size=512)

    thumb = PILImage.open(BytesIO(thumb_bytes))
    assert thumb.size == (200, 200)


def test_thumbnail_preserves_aspect_ratio_for_panorama():
    """8000x200 source should produce a 512x?? thumb where the smaller
    side is proportional, not crushed."""
    src = _jpeg_bytes(8000, 200)
    thumb_bytes = generate_thumbnail(src, target_size=512)

    thumb = PILImage.open(BytesIO(thumb_bytes))
    # 8000:200 = 40:1, so a 512-wide thumb should be ~12-13 tall.
    assert thumb.width == 512
    assert 10 <= thumb.height <= 15


def test_thumbnail_output_is_jpeg():
    """Output is always JPEG regardless of input format."""
    # Make a PNG with transparency.
    img = PILImage.new("RGBA", (400, 300), (0, 0, 0, 0))
    src = BytesIO()
    img.save(src, format="PNG")
    thumb_bytes = generate_thumbnail(src.getvalue(), target_size=512)

    thumb = PILImage.open(BytesIO(thumb_bytes))
    assert thumb.format == "JPEG"
