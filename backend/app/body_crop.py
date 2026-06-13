"""Upper-body bbox derivation.

Single source of truth for the body crop geometry used by both the indexer
(when computing per-face Re-ID embeddings) and the scan endpoint (when
computing the probe's body embedding from the live video frame).

Both sides MUST share this function — a mismatch in extents or clipping
behaviour between index time and scan time would push the two embeddings
into different regions of the Re-ID manifold and silently destroy recall.
"""
from __future__ import annotations

# Face-bbox-derived upper-body extents. Tunable per-event experience
# suggests these defaults work for both seated and standing event photos:
#   * EXTEND_UP            — keep some headroom above the face for context.
#   * EXTEND_DOWN          — torso reaches ~4x face height down for an
#                            adult standing photo before clipping kicks in.
#   * EXTEND_SIDES         — capture shoulders / upper arms without
#                            grabbing neighbours' bodies.
EXTEND_UP = 0.5      # × face_height
EXTEND_DOWN = 4.0    # × face_height
EXTEND_SIDES = 0.5   # × face_width


def derive_upper_body_bbox(
    face_bbox: tuple[float, float, float, float] | list[float],
    img_w: int,
    img_h: int,
) -> tuple[int, int, int, int]:
    """Expand a face bbox into an upper-body crop, clipped to the image.

    Args:
        face_bbox: (x_min, y_min, x_max, y_max) of the detected face. Floats
            allowed (CompreFace returns ints; PIL accepts both).
        img_w: full image width in pixels.
        img_h: full image height in pixels.

    Returns:
        (x_min, y_min, x_max, y_max) ints suitable for PIL.Image.crop. Always
        a positive-area box: if the input face_bbox is degenerate or already
        outside the frame, the result collapses to a 1x1 box at the origin
        rather than raising — callers can treat that as "no crop available"
        and skip Re-ID for the face.
    """
    if len(face_bbox) != 4:
        return (0, 0, 1, 1)
    x_min, y_min, x_max, y_max = (float(v) for v in face_bbox)
    face_w = x_max - x_min
    face_h = y_max - y_min
    if face_w <= 0 or face_h <= 0:
        return (0, 0, 1, 1)

    bx_min = int(round(x_min - EXTEND_SIDES * face_w))
    by_min = int(round(y_min - EXTEND_UP * face_h))
    bx_max = int(round(x_max + EXTEND_SIDES * face_w))
    by_max = int(round(y_max + EXTEND_DOWN * face_h))

    bx_min = max(0, bx_min)
    by_min = max(0, by_min)
    bx_max = min(img_w, bx_max)
    by_max = min(img_h, by_max)

    if bx_max <= bx_min or by_max <= by_min:
        return (0, 0, 1, 1)

    return (bx_min, by_min, bx_max, by_max)
