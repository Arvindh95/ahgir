"""Centralized PIL image opener with decompression-bomb protections.

Pillow happily opens highly compressed images (e.g., a 50KB PNG that
decompresses to 100MP) and only checks dimensions when pixels are read.
By that point we've already burned CPU/RAM on EXIF transpose, mode
conversion, or thumbnailing. Wrap every Image.open call with this helper
to enforce a pixel cap up-front and reject decompression bombs.
"""

from io import BytesIO

from PIL import Image as PILImage
from fastapi import HTTPException, status

# Reject images larger than this many total pixels. 50 megapixels covers
# any reasonable phone or DSLR shot (medium-format pro cameras max around
# 100MP — adjust upward if those become a real use case).
MAX_PIXELS = 50_000_000

# Tell Pillow to raise DecompressionBombError above this threshold rather
# than just warning. We add our own explicit check too as belt-and-braces.
PILImage.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageTooLarge(HTTPException):
    def __init__(self, message: str):
        super().__init__(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=message)


def safe_open(data: bytes, *, max_pixels: int = MAX_PIXELS) -> PILImage.Image:
    """Open image bytes with bomb protection.

    Raises HTTPException 413 if the image exceeds max_pixels OR Pillow's
    DecompressionBombError. Caller is responsible for closing / discarding
    the returned image when done.
    """
    try:
        img = PILImage.open(BytesIO(data))
        # Force Pillow to read the header so width/height are populated.
        img.load()
    except PILImage.DecompressionBombError:
        raise ImageTooLarge("Image too large (decompression bomb protection)")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image: {e}",
        )

    pixels = (img.width or 0) * (img.height or 0)
    if pixels > max_pixels:
        raise ImageTooLarge(
            f"Image is {img.width}x{img.height} ({pixels:,} pixels); max is {max_pixels:,}"
        )
    return img
