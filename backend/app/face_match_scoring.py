"""Face match scoring helpers for guest scan results.

These helpers keep accuracy-tuning logic separate from the FastAPI route so
thresholds and ranking behaviour can be tested without calling CompreFace.

The scoring deliberately avoids demographic attributes. It only uses:
- recognition similarity
- indexed face size
- indexed face quality
- agreement across multiple scan frames
- separation from the next-best candidate
- optional same-person cluster ids when available
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import mean
from typing import Any, Iterable, Mapping, Optional


@dataclass(frozen=True)
class CandidateMatch:
    """Raw match candidate returned by the recognizer for one scan frame."""

    subject_id: str
    image_id: str
    similarity: float
    frame_index: int


@dataclass(frozen=True)
class ScoredMatch:
    """Final image-level match after multi-frame aggregation."""

    image_id: str
    subject_id: str
    similarity: float
    raw_similarity: float
    frame_count: int
    score_gap: Optional[float]
    bbox: list[float]
    cluster_id: Optional[str] = None
    quality_score: float = 0.0


@dataclass(frozen=True)
class MatchDiagnostic:
    """Per-image scoring diagnostic — includes BOTH passing matches and
    filtered candidates.

    Used by the telemetry pipeline so post-event analytics can see
    where threshold cuts happened, not just what made it to the guest.
    """

    image_id: str
    subject_id: str
    raw_similarity: float
    scored_similarity: float
    score_gap: Optional[float]
    frame_count: int
    threshold_used: float
    passed: bool
    face_min_side_px: float
    quality_score: float
    blur_score: Optional[float]
    brightness_score: Optional[float]
    cluster_id: Optional[str]


@dataclass(frozen=True)
class MatchScoringConfig:
    """Tunable matching parameters."""

    large_threshold: float = 0.87
    medium_threshold: float = 0.90
    small_threshold: float = 0.93
    medium_face_px: int = 60
    large_face_px: int = 150
    multi_frame_bonus: float = 0.015
    max_multi_frame_bonus: float = 0.04
    consistency_bonus_weight: float = 0.01
    ambiguous_gap: float = 0.015
    ambiguous_penalty: float = 0.02
    low_quality_probability: float = 0.45
    low_quality_penalty: float = 0.025
    high_quality_probability: float = 0.80
    high_quality_bonus: float = 0.006
    cluster_bonus: float = 0.012
    max_cluster_bonus: float = 0.036


@dataclass(frozen=True)
class _GroupedCandidateScore:
    image_id: str
    subject_id: str
    raw_similarity: float
    scored_similarity: float
    score_gap: Optional[float]
    frame_count: int
    threshold_used: float
    passed: bool
    bbox: list[float]
    face_min_side_px: float
    quality_score: float
    blur_score: Optional[float]
    brightness_score: Optional[float]
    cluster_id: Optional[str]


def _get(face: Any, key: str, default: Any = None) -> Any:
    if isinstance(face, Mapping):
        return face.get(key, default)
    return getattr(face, key, default)


def face_min_side(face: Any) -> float:
    bbox = _get(face, "bbox")
    if not bbox or len(bbox) < 4:
        return 0.0
    return max(0.0, min(float(bbox[2]) - float(bbox[0]), float(bbox[3]) - float(bbox[1])))


def face_bbox(face: Any) -> list[float]:
    bbox = _get(face, "bbox")
    if not bbox or len(bbox) < 4:
        return [0, 0, 0, 0]
    return [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]


def face_quality(face: Any) -> float:
    """Return normalized quality for a Face-like object.

    Existing rows only have quality_score from detection probability. Newer rows
    may also include blur_score, brightness_score, and crop_clipped.
    """
    try:
        quality = float(_get(face, "quality_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        quality = 0.0

    blur_score = _get(face, "blur_score")
    brightness_score = _get(face, "brightness_score")
    crop_clipped = bool(_get(face, "crop_clipped", False))

    if blur_score is not None:
        try:
            if float(blur_score) < 80.0:
                quality -= 0.08
        except (TypeError, ValueError):
            pass
    if brightness_score is not None:
        try:
            brightness = float(brightness_score)
            if brightness < 35.0 or brightness > 225.0:
                quality -= 0.05
        except (TypeError, ValueError):
            pass
    if crop_clipped:
        quality -= 0.05

    return max(0.0, min(1.0, quality))


def face_cluster_id(face: Any) -> Optional[str]:
    cluster = _get(face, "face_cluster_id") or _get(face, "cluster_id")
    return str(cluster) if cluster else None


def required_threshold(min_side_px: float, config: MatchScoringConfig) -> float:
    if min_side_px >= config.large_face_px:
        return config.large_threshold
    if min_side_px >= config.medium_face_px:
        return config.medium_threshold
    return config.small_threshold


def quality_adjusted_threshold(base_threshold: float, quality: float, config: MatchScoringConfig) -> float:
    if quality < config.low_quality_probability:
        return min(0.99, base_threshold + config.low_quality_penalty)
    if quality >= config.high_quality_probability:
        return max(0.0, base_threshold - config.high_quality_bonus)
    return base_threshold


def _score_candidate_groups(
    candidates: Iterable[CandidateMatch],
    faces_by_subject: Mapping[str, Any],
    config: MatchScoringConfig = MatchScoringConfig(),
) -> list[_GroupedCandidateScore]:
    grouped: dict[str, list[tuple[CandidateMatch, Any, float, float, float]]] = {}
    cluster_hits: dict[str, set[str]] = {}

    for candidate in candidates:
        face = faces_by_subject.get(candidate.subject_id)
        min_side = face_min_side(face)
        quality = face_quality(face)
        threshold = quality_adjusted_threshold(required_threshold(min_side, config), quality, config)
        grouped.setdefault(candidate.image_id, []).append(
            (candidate, face, min_side, quality, threshold)
        )
        if candidate.similarity >= threshold:
            # Deliberately conservative: only raw-threshold hits contribute
            # cluster evidence. Bonus-rescued candidates can be returned, but
            # they do not amplify sibling images in the same cluster.
            cluster = face_cluster_id(face)
            if cluster:
                cluster_hits.setdefault(cluster, set()).add(candidate.image_id)

    grouped_scores: list[_GroupedCandidateScore] = []
    for image_id, entries in grouped.items():
        best_candidate, best_face, min_side, best_quality, threshold = max(
            entries, key=lambda item: item[0].similarity
        )
        raw_similarity = best_candidate.similarity
        frame_count = len({e[0].frame_index for e in entries})
        similarities = [e[0].similarity for e in entries]
        raw_multi_frame_bonus = min(
            config.max_multi_frame_bonus,
            config.multi_frame_bonus * max(0, frame_count - 1),
        )
        raw_consistency_bonus = mean(similarities) * config.consistency_bonus_weight
        cluster = face_cluster_id(best_face)
        raw_cluster_bonus = 0.0
        if cluster:
            raw_cluster_bonus = min(
                config.max_cluster_bonus,
                config.cluster_bonus * max(0, len(cluster_hits.get(cluster, set())) - 1),
            )
        scored_before_filter = min(
            1.0,
            raw_similarity + raw_multi_frame_bonus + raw_consistency_bonus + raw_cluster_bonus,
        )
        passed = raw_similarity >= threshold or (
            frame_count > 1 and scored_before_filter >= threshold
        )

        grouped_scores.append(_GroupedCandidateScore(
            image_id=image_id,
            subject_id=best_candidate.subject_id,
            raw_similarity=raw_similarity,
            scored_similarity=scored_before_filter if passed else raw_similarity,
            score_gap=None,
            frame_count=frame_count,
            threshold_used=threshold,
            passed=passed,
            bbox=face_bbox(best_face),
            face_min_side_px=min_side,
            quality_score=best_quality,
            blur_score=_get(best_face, "blur_score"),
            brightness_score=_get(best_face, "brightness_score"),
            cluster_id=cluster,
        ))

    passing = [score for score in grouped_scores if score.passed]
    passing.sort(key=lambda item: item.scored_similarity, reverse=True)

    penalized: list[_GroupedCandidateScore] = []
    for index, item in enumerate(passing):
        next_score = passing[index + 1].scored_similarity if index + 1 < len(passing) else None
        gap = None if next_score is None else item.scored_similarity - next_score
        scored_similarity = item.scored_similarity
        if gap is not None and gap < config.ambiguous_gap and item.frame_count == 1:
            scored_similarity = max(0.0, scored_similarity - config.ambiguous_penalty)
        penalized.append(replace(item, scored_similarity=scored_similarity))

    penalized.sort(key=lambda item: item.scored_similarity, reverse=True)
    with_gaps: list[_GroupedCandidateScore] = []
    for index, item in enumerate(penalized):
        next_score = penalized[index + 1].scored_similarity if index + 1 < len(penalized) else None
        gap = None if next_score is None else item.scored_similarity - next_score
        with_gaps.append(replace(item, score_gap=gap))

    filtered = [score for score in grouped_scores if not score.passed]
    return filtered + with_gaps


def score_candidates_diagnostic(
    candidates: Iterable[CandidateMatch],
    faces_by_subject: Mapping[str, Any],
    config: MatchScoringConfig = MatchScoringConfig(),
) -> list[MatchDiagnostic]:
    """Return all image-level candidates with pass/fail scoring details.

    Filtered candidates use their raw similarity as scored_similarity
    (no bonuses applied) so telemetry reflects what was actually filtered.
    """
    return [
        MatchDiagnostic(
            image_id=score.image_id,
            subject_id=score.subject_id,
            raw_similarity=score.raw_similarity,
            scored_similarity=score.scored_similarity,
            score_gap=score.score_gap,
            frame_count=score.frame_count,
            threshold_used=score.threshold_used,
            passed=score.passed,
            face_min_side_px=score.face_min_side_px,
            quality_score=score.quality_score,
            blur_score=score.blur_score,
            brightness_score=score.brightness_score,
            cluster_id=score.cluster_id,
        )
        for score in _score_candidate_groups(candidates, faces_by_subject, config)
    ]


def aggregate_face_matches(
    candidates: Iterable[CandidateMatch],
    faces_by_subject: Mapping[str, Any],
    config: MatchScoringConfig = MatchScoringConfig(),
) -> list[ScoredMatch]:
    return [
        ScoredMatch(
            image_id=score.image_id,
            subject_id=score.subject_id,
            similarity=score.scored_similarity,
            raw_similarity=score.raw_similarity,
            frame_count=score.frame_count,
            score_gap=score.score_gap,
            bbox=score.bbox,
            cluster_id=score.cluster_id,
            quality_score=score.quality_score,
        )
        for score in _score_candidate_groups(candidates, faces_by_subject, config)
        if score.passed
    ]
