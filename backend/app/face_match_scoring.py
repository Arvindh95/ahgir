"""Face match scoring helpers for guest scan results.

These helpers keep accuracy-tuning logic separate from the FastAPI route so
thresholds and ranking behaviour can be tested without calling CompreFace.

The scoring deliberately avoids demographic attributes. It only uses:
- recognition similarity
- indexed face size
- agreement across multiple scan frames
- separation from the next-best candidate
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


@dataclass(frozen=True)
class MatchScoringConfig:
    """Tunable matching parameters.

    large_threshold, medium_threshold, and small_threshold are intentionally
    split so large clear faces can use a slightly lower floor while small event
    faces remain strict.
    """

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


def face_min_side(face: Any) -> float:
    """Return min bbox side for a Face-like object/dict, or 0 if unavailable."""
    bbox = getattr(face, "bbox", None)
    if bbox is None and isinstance(face, Mapping):
        bbox = face.get("bbox")
    if not bbox or len(bbox) < 4:
        return 0.0
    return max(0.0, min(float(bbox[2]) - float(bbox[0]), float(bbox[3]) - float(bbox[1])))


def face_bbox(face: Any) -> list[float]:
    bbox = getattr(face, "bbox", None)
    if bbox is None and isinstance(face, Mapping):
        bbox = face.get("bbox")
    if not bbox or len(bbox) < 4:
        return [0, 0, 0, 0]
    return [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]


def required_threshold(min_side_px: float, config: MatchScoringConfig) -> float:
    """Choose the similarity floor for the indexed face size."""
    if min_side_px >= config.large_face_px:
        return config.large_threshold
    if min_side_px >= config.medium_face_px:
        return config.medium_threshold
    return config.small_threshold


def aggregate_face_matches(
    candidates: Iterable[CandidateMatch],
    faces_by_subject: Mapping[str, Any],
    config: MatchScoringConfig = MatchScoringConfig(),
) -> list[ScoredMatch]:
    """Aggregate raw CompreFace candidates into ranked image matches.

    The key behaviour: a photo that appears across multiple scan frames earns a
    small confidence boost. This makes a stable 3-frame match outrank a one-off
    borderline match without needing gender or other demographic filtering.
    """
    grouped: dict[str, list[tuple[CandidateMatch, Any, float]]] = {}

    for candidate in candidates:
        face = faces_by_subject.get(candidate.subject_id)
        min_side = face_min_side(face)
        if candidate.similarity < required_threshold(min_side, config):
            continue
        grouped.setdefault(candidate.image_id, []).append((candidate, face, min_side))

    if not grouped:
        return []

    raw_scored: list[dict[str, Any]] = []
    for image_id, entries in grouped.items():
        # One image can contain multiple indexed faces; keep the subject with
        # the strongest raw similarity as the representative bbox/subject.
        best_entry = max(entries, key=lambda item: item[0].similarity)
        best_candidate, best_face, _min_side = best_entry
        similarities = [item[0].similarity for item in entries]
        frame_count = len({item[0].frame_index for item in entries})

        multi_frame_bonus = min(
            config.max_multi_frame_bonus,
            config.multi_frame_bonus * max(0, frame_count - 1),
        )
        consistency_bonus = mean(similarities) * config.consistency_bonus_weight
        final_similarity = min(1.0, max(similarities) + multi_frame_bonus + consistency_bonus)

        raw_scored.append({
            "image_id": image_id,
            "subject_id": best_candidate.subject_id,
            "similarity": final_similarity,
            "raw_similarity": max(similarities),
            "frame_count": frame_count,
            "bbox": face_bbox(best_face),
        })

    raw_scored.sort(key=lambda item: item["similarity"], reverse=True)

    scored: list[ScoredMatch] = []
    for index, item in enumerate(raw_scored):
        next_score = raw_scored[index + 1]["similarity"] if index + 1 < len(raw_scored) else None
        gap = None if next_score is None else item["similarity"] - next_score
        similarity = item["similarity"]

        # If the rank is extremely close and the image only matched one frame,
        # down-rank it slightly. Multi-frame agreement is allowed to survive a
        # tight gap because it has stronger evidence.
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
        ))

    scored.sort(key=lambda item: item.similarity, reverse=True)
    return scored
