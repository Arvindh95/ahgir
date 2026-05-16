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

from dataclasses import dataclass
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


def aggregate_face_matches(
    candidates: Iterable[CandidateMatch],
    faces_by_subject: Mapping[str, Any],
    config: MatchScoringConfig = MatchScoringConfig(),
) -> list[ScoredMatch]:
    grouped: dict[str, list[tuple[CandidateMatch, Any, float, float]]] = {}
    cluster_hits: dict[str, set[str]] = {}

    for candidate in candidates:
        face = faces_by_subject.get(candidate.subject_id)
        min_side = face_min_side(face)
        quality = face_quality(face)
        threshold = quality_adjusted_threshold(required_threshold(min_side, config), quality, config)
        if candidate.similarity < threshold:
            continue
        grouped.setdefault(candidate.image_id, []).append((candidate, face, min_side, quality))
        cluster = face_cluster_id(face)
        if cluster:
            cluster_hits.setdefault(cluster, set()).add(candidate.image_id)

    if not grouped:
        return []

    raw_scored: list[dict[str, Any]] = []
    for image_id, entries in grouped.items():
        best_candidate, best_face, _min_side, best_quality = max(
            entries, key=lambda item: item[0].similarity
        )
        similarities = [item[0].similarity for item in entries]
        frame_count = len({item[0].frame_index for item in entries})
        cluster = face_cluster_id(best_face)

        multi_frame_bonus = min(config.max_multi_frame_bonus, config.multi_frame_bonus * max(0, frame_count - 1))
        consistency_bonus = mean(similarities) * config.consistency_bonus_weight
        cluster_bonus = 0.0
        if cluster:
            cluster_bonus = min(config.max_cluster_bonus, config.cluster_bonus * max(0, len(cluster_hits.get(cluster, set())) - 1))
        final_similarity = min(1.0, max(similarities) + multi_frame_bonus + consistency_bonus + cluster_bonus)

        raw_scored.append({
            "image_id": image_id,
            "subject_id": best_candidate.subject_id,
            "similarity": final_similarity,
            "raw_similarity": max(similarities),
            "frame_count": frame_count,
            "bbox": face_bbox(best_face),
            "cluster_id": cluster,
            "quality_score": best_quality,
        })

    raw_scored.sort(key=lambda item: item["similarity"], reverse=True)

    scored: list[ScoredMatch] = []
    for index, item in enumerate(raw_scored):
        next_score = raw_scored[index + 1]["similarity"] if index + 1 < len(raw_scored) else None
        gap = None if next_score is None else item["similarity"] - next_score
        similarity = item["similarity"]

        if gap is not None and gap < config.ambiguous_gap and item["frame_count"] == 1:
            similarity = max(0.0, similarity - config.ambiguous_penalty)

        scored.append(ScoredMatch(
            image_id=item["image_id"],
            subject_id=item["subject_id"],
            similarity=similarity,
            raw_similarity=item["raw_similarity"],
            frame_count=item["frame_count"],
            score_gap=gap,
            bbox=item["bbox"],
            cluster_id=item["cluster_id"],
            quality_score=item["quality_score"],
        ))

    scored.sort(key=lambda item: item.similarity, reverse=True)
    return scored
