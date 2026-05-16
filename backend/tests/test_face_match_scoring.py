from app.face_match_scoring import CandidateMatch, MatchScoringConfig, aggregate_face_matches, required_threshold


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
    config = MatchScoringConfig(large_threshold=0.87, cluster_bonus=0.02, consistency_bonus_weight=0.0)
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
