"""EXIF stripping for stored original photos.

Originals are served back to guests when ``allow_downloads`` is enabled, so we
must remove embedded GPS/device metadata before persisting to MinIO. The
``exif_data`` JSON we keep in the DB is sanitized separately.
"""
from io import BytesIO

from PIL import ImageOps

from app.utils.image_safety import safe_open as safe_open_image


_PASSTHROUGH_FORMATS = {"JPEG", "PNG", "MPO"}


def strip_exif_bytes(file_data: bytes) -> bytes:
    """Return ``file_data`` re-encoded without EXIF/XMP/GPS metadata.

    The caller is responsible for upstream format/bomb validation; this helper
    assumes ``safe_open_image`` will succeed. On encode failure the exception
    propagates so the upload fails closed rather than leaking GPS.
    """
    img = safe_open_image(file_data)
    fmt = img.format if img.format in _PASSTHROUGH_FORMATS else "JPEG"

    # Bake EXIF orientation into pixels before we drop the tag.
    img = ImageOps.exif_transpose(img)

    if fmt == "JPEG" and img.mode not in ("RGB", "L", "CMYK"):
        img = img.convert("RGB")
    elif fmt == "MPO":
        # Re-encode the primary frame as standard JPEG; multi-picture container
        # is unnecessary once originals are stored.
        fmt = "JPEG"
        if img.mode not in ("RGB", "L", "CMYK"):
            img = img.convert("RGB")

    out = BytesIO()
    save_kwargs: dict = {}
    if fmt == "JPEG":
        save_kwargs.update(quality=95, optimize=True, progressive=True)
    img.save(out, format=fmt, **save_kwargs)
    return out.getvalue()
