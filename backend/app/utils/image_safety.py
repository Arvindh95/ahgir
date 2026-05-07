"""Centralized PIL image opener with decompression-bomb protections.

Pillow happily opens highly compressed images (e.g., a 50KB PNG that
decompresses to 100MP) and only checks dimensions when pixels are read.
By that point we've already burned CPU/RAM on EXIF transpose, mode
conversion, or thumbnailing. Wrap every Image.open call with this helper
to enforce a pixel cap up-front and reject decompression bombs.
"""

import warnings
from io import BytesIO

from PIL import Image as PILImage
from fastapi import HTTPException, status

# Reject images larger than this many total pixels. 50 megapixels covers
# any reasonable phone or DSLR shot (medium-format pro cameras max around
# 100MP — adjust upward if those become a real use case).
MAX_PIXELS = 50_000_000

# Tell Pillow to raise DecompressionBombError above 2*threshold and
# DecompressionBombWarning above the threshold itself. We promote the
# warning to an exception so even images in the 1x..2x range are caught
# without us calling .load() first.
PILImage.MAX_IMAGE_PIXELS = MAX_PIXELS
warnings.simplefilter("error", PILImage.DecompressionBombWarning)


class ImageTooLarge(HTTPException):
    def __init__(self, message: str):
        super().__init__(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=message)


def safe_open(data: bytes, *, max_pixels: int = MAX_PIXELS) -> PILImage.Image:
    """Open image bytes with bomb protection.

    Order matters: we read width/height from the file header first, reject
    if the implied pixel count exceeds max_pixels, and only then call
    .load() to actually decode. This means a 100MP bomb gets rejected
    after parsing a few bytes of the header, never decoded into RAM.
    """
    try:
        img = PILImage.open(BytesIO(data))
        # Header parsing populates width/height without decoding pixel data.
        # Check the pixel cap NOW, before .load() forces a full decode.
        pixels = (img.width or 0) * (img.height or 0)
        if pixels > max_pixels:
            raise ImageTooLarge(
                f"Image is {img.width}x{img.height} ({pixels:,} pixels); max is {max_pixels:,}"
            )
        # Now safe to fully decode.
        img.load()
    except PILImage.DecompressionBombError:
        raise ImageTooLarge("Image too large (decompression bomb protection)")
    except PILImage.DecompressionBombWarning:
        # Promoted to exception via warnings.simplefilter("error", ...)
        raise ImageTooLarge("Image too large (decompression bomb protection)")
    except ImageTooLarge:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image: {e}",
        )

    return img
