from app.face_match_scoring import (
    CandidateMatch,
    MatchScoringConfig,
    aggregate_face_matches,
    required_threshold,
    score_candidates_diagnostic,
)


class FaceRow:
    def __init__(self, bbox, quality_score=0.9, face_cluster_id=None, blur_score=None, brightness_score=None, crop_clipped=False):
        self.bbox = bbox
        self.quality_score = quality_score
        self.face_cluster_id = face_cluster_id
        self.blur_score = blur_score
        self.brightness_score = brightness_score
        self.crop_clipped = crop_clipped


def test_thresholds_vary_by_face_size():
    config = MatchScoringConfig(large_threshold=0.87, medium_threshold=0.90, small_threshold=0.93)
    assert required_threshold(200, config) == 0.87
    assert required_threshold(80, config) == 0.90
    assert required_threshold(40, config) == 0.93


def test_repeated_frame_evidence_ranks_higher_than_one_frame_evidence():
    config = MatchScoringConfig(large_threshold=0.87, consistency_bonus_weight=0.01)
    rows = {
        "s/a/0": FaceRow([0, 0, 200, 200]),
        "s/b/0": FaceRow([0, 0, 200, 200]),
    }
    candidates = [
        CandidateMatch("s/a/0", "a", 0.91, 0),
        CandidateMatch("s/b/0", "b", 0.88, 0),
        CandidateMatch("s/b/0", "b", 0.89, 1),
        CandidateMatch("s/b/0", "b", 0.88, 2),
    ]
    scored = aggregate_face_matches(candidates, rows, config)
    assert [item.image_id for item in scored] == ["b", "a"]
    assert scored[0].frame_count == 3


def test_small_faces_need_the_small_face_floor():
    config = MatchScoringConfig(small_threshold=0.93)
    rows = {
        "s/a/0": FaceRow([0, 0, 40, 40]),
        "s/b/0": FaceRow([0, 0, 40, 40]),
    }
    candidates = [
        CandidateMatch("s/a/0", "a", 0.91, 0),
        CandidateMatch("s/b/0", "b", 0.94, 0),
    ]
    scored = aggregate_face_matches(candidates, rows, config)
    assert [item.image_id for item in scored] == ["b"]


def test_low_quality_face_requires_stronger_similarity():
    config = MatchScoringConfig(large_threshold=0.87, low_quality_probability=0.45, low_quality_penalty=0.03)
    rows = {
        "s/a/0": FaceRow([0, 0, 200, 200], quality_score=0.40),
        "s/b/0": FaceRow([0, 0, 200, 200], quality_score=0.90),
    }
    candidates = [
        CandidateMatch("s/a/0", "a", 0.89, 0),
        CandidateMatch("s/b/0", "b", 0.89, 0),
    ]
    scored = aggregate_face_matches(candidates, rows, config)
    assert [item.image_id for item in scored] == ["b"]


def test_cluster_evidence_boosts_related_images():
    # ambiguous_gap=0.0 disables the close-runner-up penalty so this test
    # isolates cluster-boost behavior. With the default 0.015 gap, the two
    # cluster-1 hits tie at 0.90 and get docked by ambiguous_penalty —
    # correct system behavior but unrelated to cluster scoring.
    config = MatchScoringConfig(
        large_threshold=0.87,
        cluster_bonus=0.02,
        consistency_bonus_weight=0.0,
        ambiguous_gap=0.0,
    )
    rows = {
        "s/a/0": FaceRow([0, 0, 200, 200], face_cluster_id="cluster-1"),
        "s/b/0": FaceRow([0, 0, 200, 200], face_cluster_id="cluster-1"),
        "s/c/0": FaceRow([0, 0, 200, 200], face_cluster_id="cluster-2"),
    }
    candidates = [
        CandidateMatch("s/a/0", "a", 0.88, 0),
        CandidateMatch("s/b/0", "b", 0.88, 1),
        CandidateMatch("s/c/0", "c", 0.89, 0),
    ]
    scored = aggregate_face_matches(candidates, rows, config)
    assert scored[0].cluster_id == "cluster-1"
    assert scored[0].similarity > 0.89


def test_score_candidates_diagnostic_includes_filtered():
    """Telemetry helper must return BOTH passing and filtered candidates
    so tuning analytics can see near-misses, not just successful matches."""
    config = MatchScoringConfig(
        large_threshold=0.87,
        medium_threshold=0.90,
        small_threshold=0.93,
    )
    rows = {
        "s/a/0": FaceRow([0, 0, 200, 200]),  # large face → 0.87 threshold
        "s/b/0": FaceRow([0, 0, 40, 40]),    # small face → 0.93 threshold
    }
    candidates = [
        CandidateMatch("s/a/0", "a", 0.91, 0),   # passes 0.87
        CandidateMatch("s/b/0", "b", 0.85, 0),   # fails 0.93 — filtered
    ]
    diagnostics = score_candidates_diagnostic(candidates, rows, config)
    by_image = {d.image_id: d for d in diagnostics}
    assert set(by_image.keys()) == {"a", "b"}
    assert by_image["a"].passed is True
    assert by_image["a"].threshold_used == 0.87
    assert by_image["b"].passed is False
    assert by_image["b"].threshold_used == 0.93
    assert by_image["b"].raw_similarity == 0.85
    # Filtered candidates surface scored_similarity = raw, no bonuses applied.
    assert by_image["b"].scored_similarity == 0.85
