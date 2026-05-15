"""EXIF stripping for stored original photos.

Originals are served back to guests when ``allow_downloads`` is enabled, so we
must remove embedded GPS/device metadata before persisting to MinIO. The
``exif_data`` JSON we keep in the DB is sanitized separately.

All accepted inputs (JPEG / PNG / MPO) are normalized to JPEG on the way out.
Storage paths and HTTP responses serve `.jpg` with `Content-Type: image/jpeg`
unconditionally — keeping the on-disk format aligned with that contract
avoids guests downloading "image.jpg" that's actually PNG bytes (browsers
mostly cope, but it breaks anything that trusts the extension/header pair,
including some EXIF strippers, virus scanners, and our own thumbnail
codepath that re-opens the file).
"""
from io import BytesIO

from PIL import Image as PILImage, ImageOps

from app.utils.image_safety import safe_open as safe_open_image


def strip_exif_bytes(file_data: bytes) -> bytes:
    """Return ``file_data`` re-encoded as JPEG without EXIF/XMP/GPS metadata.

    PNG and MPO inputs are converted to JPEG. Transparent pixels (RGBA / LA /
    palette-with-transparency) are flattened against a white background since
    JPEG has no alpha channel; this matches the existing thumbnail behaviour.

    The caller is responsible for upstream format/bomb validation; this helper
    assumes ``safe_open_image`` will succeed. On encode failure the exception
    propagates so the upload fails closed rather than leaking GPS.
    """
    img = safe_open_image(file_data)

    # Bake EXIF orientation into pixels before we drop the tag.
    img = ImageOps.exif_transpose(img)

    # JPEG has no alpha. Flatten transparency against white so we don't
    # end up with black bars where the PNG was transparent.
    if img.mode in ("RGBA", "LA"):
        background = PILImage.new("RGB", img.size, (255, 255, 255))
        # Use the alpha channel as a paste mask so transparent pixels show white.
        alpha = img.split()[-1]
        background.paste(img.convert("RGB"), mask=alpha)
        img = background
    elif img.mode not in ("RGB", "L", "CMYK"):
        # Palette images, BW, etc. — straight convert.
        img = img.convert("RGB")

    out = BytesIO()
    img.save(out, format="JPEG", quality=95, optimize=True, progressive=True)
    return out.getvalue()
