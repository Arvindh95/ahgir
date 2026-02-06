"""Shared thumbnail generation utility."""

from io import BytesIO
from PIL import Image as PILImage


def generate_thumbnail(file_data: bytes, target_width: int = 512) -> bytes:
    """Generate thumbnail with specified width, maintaining aspect ratio"""
    img = PILImage.open(BytesIO(file_data))

    # Convert to RGB if necessary (handles PNG with transparency)
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')

    # Calculate new height maintaining aspect ratio
    width, height = img.size
    aspect_ratio = height / width
    new_height = int(target_width * aspect_ratio)

    # Resize image
    img_resized = img.resize((target_width, new_height), PILImage.Resampling.LANCZOS)

    # Save to bytes
    buffer = BytesIO()
    img_resized.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)
    return buffer.getvalue()
