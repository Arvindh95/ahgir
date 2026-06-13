"""Tests for the upper-body bbox derivation used by Re-ID.

Both index time and scan time MUST agree on this geometry — a mismatch
silently destroys recall by pushing the two embeddings into different
regions of the Re-ID manifold. These tests pin the math.
"""
from __future__ import annotations

from app.body_crop import (
    EXTEND_DOWN,
    EXTEND_SIDES,
    EXTEND_UP,
    derive_upper_body_bbox,
)


def test_central_face_extends_correctly():
    # 100x100 face centered in a 1000x1000 image: well away from edges,
    # extents should match the configured constants exactly.
    face = (450, 400, 550, 500)
    face_w = face[2] - face[0]
    face_h = face[3] - face[1]
    expected = (
        int(round(face[0] - EXTEND_SIDES * face_w)),
        int(round(face[1] - EXTEND_UP * face_h)),
        int(round(face[2] + EXTEND_SIDES * face_w)),
        int(round(face[3] + EXTEND_DOWN * face_h)),
    )
    assert derive_upper_body_bbox(face, 1000, 1000) == expected


def test_clipping_at_top_edge():
    # Face at the top — upward extension hits the boundary and clamps to 0.
    face = (100, 0, 200, 100)
    bbox = derive_upper_body_bbox(face, 1000, 1000)
    assert bbox[1] == 0  # y_min clamped
    assert bbox[3] == int(round(100 + EXTEND_DOWN * 100))


def test_clipping_at_bottom_edge():
    # Face near the bottom — downward extension hits image height and clamps.
    face = (100, 900, 200, 1000)
    bbox = derive_upper_body_bbox(face, 1000, 1000)
    assert bbox[3] == 1000  # y_max clamped to image height


def test_clipping_at_left_edge():
    face = (0, 100, 100, 200)
    bbox = derive_upper_body_bbox(face, 1000, 1000)
    assert bbox[0] == 0


def test_clipping_at_right_edge():
    face = (900, 100, 1000, 200)
    bbox = derive_upper_body_bbox(face, 1000, 1000)
    assert bbox[2] == 1000


def test_degenerate_face_returns_safe_default():
    # Zero-area / inverted bbox should not raise; we return a 1x1 marker so
    # the caller can detect it and skip Re-ID for this face.
    assert derive_upper_body_bbox((100, 100, 100, 100), 1000, 1000) == (0, 0, 1, 1)
    assert derive_upper_body_bbox((100, 100, 50, 50), 1000, 1000) == (0, 0, 1, 1)


def test_too_few_values_returns_safe_default():
    assert derive_upper_body_bbox((1, 2, 3), 1000, 1000) == (0, 0, 1, 1)  # type: ignore[arg-type]
    assert derive_upper_body_bbox([], 1000, 1000) == (0, 0, 1, 1)  # type: ignore[arg-type]


def test_face_outside_image_collapses_safely():
    # Face entirely to the right of the image — body extent would clip to a
    # zero-width box, return the safe-default marker instead of raising.
    bbox = derive_upper_body_bbox((1100, 100, 1200, 200), 1000, 1000)
    assert bbox == (0, 0, 1, 1)


def test_output_is_always_positive_area():
    # Property check across a variety of placements: result must always
    # have x_max > x_min and y_max > y_min.
    placements = [
        (10, 10, 60, 60),
        (200, 50, 400, 250),
        (5, 800, 95, 990),
        (0, 0, 50, 50),
    ]
    for face in placements:
        b = derive_upper_body_bbox(face, 1000, 1000)
        assert b[2] > b[0], face
        assert b[3] > b[1], face


def test_integer_output_types():
    # PIL.Image.crop is strict about ints in some versions — make sure we
    # never hand it a float that triggers a deprecation warning.
    bbox = derive_upper_body_bbox((100.5, 200.7, 300.3, 400.9), 1000, 1000)
    for v in bbox:
        assert isinstance(v, int)
