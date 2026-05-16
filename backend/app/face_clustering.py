"""Lightweight event-level face clustering helpers.

CompreFace owns the true embeddings in this project, so clustering here is
built around strong repeated recognition evidence. It is designed to be safe:
clusters boost ranking only when available and never replace the underlying
similarity threshold.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Iterable, Protocol


class FaceLike(Protocol):
    id: uuid.UUID
    event_id: uuid.UUID
    image_id: uuid.UUID
    compreface_subject_id: str | None
    face_cluster_id: uuid.UUID | None


def deterministic_cluster_id(event_id: uuid.UUID, seed_subject_id: str) -> uuid.UUID:
    """Create a stable cluster id for an event and seed subject."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"picur:{event_id}:face-cluster:{seed_subject_id}")


def assign_cluster_ids_from_edges(
    faces: Iterable[FaceLike],
    same_person_edges: Iterable[tuple[str, str]],
) -> dict[str, uuid.UUID]:
    """Assign cluster ids from subject-id edges.

    Args:
        faces: Face rows for one event.
        same_person_edges: pairs of compreface_subject_id values believed to be
            the same person by a high-confidence recognizer comparison.

    Returns:
        subject_id -> cluster_id mapping. Singleton faces are omitted so the DB
        does not need to store meaningless one-face clusters.
    """
    subject_to_face = {
        f.compreface_subject_id: f
        for f in faces
        if f.compreface_subject_id
    }
    parent: dict[str, str] = {subject: subject for subject in subject_to_face}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        if a not in parent or b not in parent:
            return
        ra = find(a)
        rb = find(b)
        if ra == rb:
            return
        parent[max(ra, rb)] = min(ra, rb)

    for left, right in same_person_edges:
        union(left, right)

    groups: dict[str, list[str]] = defaultdict(list)
    for subject in parent:
        groups[find(subject)].append(subject)

    result: dict[str, uuid.UUID] = {}
    for root, subjects in groups.items():
        if len(subjects) < 2:
            continue
        event_id = subject_to_face[root].event_id
        cluster_id = deterministic_cluster_id(event_id, root)
        for subject in subjects:
            result[subject] = cluster_id
    return result
