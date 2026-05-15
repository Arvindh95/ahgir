"""Shared thumbnail generation utility."""

from io import BytesIO
from PIL import Image as PILImage, ImageOps

from app.utils.image_safety import safe_open


def generate_thumbnail(file_data: bytes, target_size: int = 512) -> bytes:
    """Generate thumbnail within a target_size × target_size bounding box,
    maintaining aspect ratio. Never upscales.

    Bounded-box (vs width-fixed) matters for extreme aspect ratios. A
    9000×512 panorama under the 50MP cap would, with the old width-fixed
    formula, produce a 512 × ~28 thumb — but a 512 × 9000 vertical strip
    under the same cap would produce a 512 × 9000 thumb, allocating
    ~14 MB just for one thumbnail. Bounding both dimensions caps every
    thumbnail at target_size² pixels regardless of orientation.
    """
    img = safe_open(file_data)

    # Apply EXIF orientation (phone cameras store rotation in metadata)
    img = ImageOps.exif_transpose(img)

    # Convert to RGB if necessary (handles PNG with transparency)
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')

    # thumbnail() resizes in-place, preserves aspect ratio, and refuses
    # to upscale — a 200×200 source stays 200×200.
    img.thumbnail((target_size, target_size), PILImage.Resampling.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)
    return buffer.getvalue()
