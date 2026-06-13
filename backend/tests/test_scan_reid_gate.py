"""Phase 2/2.1 Re-ID scan tests — cosine, adaptive gate, telemetry, probe.

Exercises the per-scan adaptive gate and the telemetry write without
standing up CompreFace. The probe-embedding helper is tested with the
detection + sidecar calls mocked.
"""
import asyncio
import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image as PILImage

from app.face_match_scoring import CandidateMatch, MatchScoringConfig, ScoredMatch
from app.models import Event, Face, Image, ScanMatchMetric, User
from app.auth import hash_password
from app.routers import guest_accuracy as ga


# 512-d helpers: probe=[1,0,...]; a candidate [v,0,...] gives cosine == v
# under the dot-product _reid_cosine (both treated as already-normalised).
def _vec(v: float) -> list[float]:
    return [v] + [0.0] * 511


PROBE = _vec(1.0)


def _scored(image_id: str, subject_id: str, sim: float) -> ScoredMatch:
    return ScoredMatch(
        image_id=image_id, subject_id=subject_id, similarity=sim,
        raw_similarity=sim, frame_count=1, score_gap=None,
        bbox=[0, 0, 200, 200], cluster_id=None, quality_score=0.95,
    )


def _faces(**subject_to_vec):
    """subject_id -> face-like with .reid_embedding (vec or None)."""
    return {s: SimpleNamespace(reid_embedding=v) for s, v in subject_to_vec.items()}


@pytest.fixture
def enable_scan_gate():
    from app.config import settings
    o_i, o_s = settings.reid_enabled_indexing, settings.reid_enabled_scan
    settings.reid_enabled_indexing = True
    settings.reid_enabled_scan = True
    try:
        yield
    finally:
        settings.reid_enabled_indexing, settings.reid_enabled_scan = o_i, o_s


# --------------------------------------------------------------------------- #
# _reid_cosine
# --------------------------------------------------------------------------- #

class TestCosine:
    def test_none_inputs(self):
        assert ga._reid_cosine(None, _vec(0.5)) is None
        assert ga._reid_cosine(PROBE, None) is None

    def test_shape_mismatch(self):
        assert ga._reid_cosine(PROBE, [0.5, 0.5, 0.5]) is None

    def test_dot_product(self):
        assert ga._reid_cosine([1.0, 0.0, 0.0], [0.5, 0.0, 0.0]) == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# _reid_adaptive_gate — relative per-scan decision
# --------------------------------------------------------------------------- #

class TestAdaptiveGate:
    def test_drops_sibling_far_below_top(self):
        """Two face-confident; sibling body sits far below the guest's top."""
        scored = [_scored("A", "sA", 0.95), _scored("B", "sB", 0.95)]
        faces = _faces(sA=_vec(0.80), sB=_vec(0.40))
        reid_sims, kept, surviving = ga._reid_adaptive_gate(scored, faces, PROBE)
        assert reid_sims == {"sA": pytest.approx(0.80), "sB": pytest.approx(0.40)}
        assert kept == {"sA": True, "sB": False}
        assert [m.subject_id for m in surviving] == ["sA"]

    def test_keeps_when_all_cluster_high(self):
        """All real photos cluster within the margin → none dropped."""
        scored = [_scored("A", "sA", 0.95), _scored("B", "sB", 0.95)]
        faces = _faces(sA=_vec(0.80), sB=_vec(0.75))
        _, kept, surviving = ga._reid_adaptive_gate(scored, faces, PROBE)
        assert all(kept.values())
        assert len(surviving) == 2

    def test_lone_confident_high_kept(self):
        scored = [_scored("A", "sA", 0.95)]
        faces = _faces(sA=_vec(0.80))
        _, kept, surviving = ga._reid_adaptive_gate(scored, faces, PROBE)
        assert kept == {"sA": True}
        assert len(surviving) == 1

    def test_lone_confident_low_dropped(self):
        """No peers to compare → fall back to the absolute floor (0.65)."""
        scored = [_scored("A", "sA", 0.95)]
        faces = _faces(sA=_vec(0.50))
        _, kept, surviving = ga._reid_adaptive_gate(scored, faces, PROBE)
        assert kept == {"sA": False}
        assert surviving == []

    def test_weak_top_falls_back_to_face_only(self):
        """Even the best body match is weak → signal uninformative, keep all."""
        scored = [_scored("A", "sA", 0.95), _scored("B", "sB", 0.95)]
        faces = _faces(sA=_vec(0.55), sB=_vec(0.50))
        _, kept, surviving = ga._reid_adaptive_gate(scored, faces, PROBE)
        assert kept == {}
        assert len(surviving) == 2

    def test_null_candidate_not_judged(self):
        """Candidate mid-backfill (NULL) is never judged and always kept."""
        scored = [_scored("A", "sA", 0.95), _scored("B", "sB", 0.95)]
        faces = _faces(sA=_vec(0.80), sB=None)
        reid_sims, kept, surviving = ga._reid_adaptive_gate(scored, faces, PROBE)
        assert "sB" not in reid_sims
        assert "sB" not in kept  # never judged
        assert len(surviving) == 2  # lone judged sA is high → all kept

    def test_subfloor_match_not_gated(self):
        """A match below the face floor is left alone even with a low body."""
        scored = [_scored("A", "sA", 0.95), _scored("B", "sB", 0.80)]
        faces = _faces(sA=_vec(0.80), sB=_vec(0.10))
        _, kept, surviving = ga._reid_adaptive_gate(scored, faces, PROBE)
        assert "sB" not in kept  # sub-face-floor → not judged
        assert len(surviving) == 2


# --------------------------------------------------------------------------- #
# Telemetry — reid columns written from the precomputed maps
# --------------------------------------------------------------------------- #

class TestTelemetry:
    def _seed(self, db):
        user = User(email=f"u_{uuid.uuid4()}@e.com", password_hash=hash_password("pw"))
        db.add(user); db.commit()
        event = Event(owner_user_id=user.id, slug=f"ev-{uuid.uuid4()}", name="E",
                      allow_downloads=True, retention_days=90)
        db.add(event); db.commit()
        image = Image(event_id=event.id, filename=f"{uuid.uuid4()}.jpg",
                      file_hash=f"h_{uuid.uuid4()}", size_bytes=1024,
                      width=400, height=500, status="indexed", face_count=1)
        db.add(image); db.commit()
        subject_id = f"{event.id}/{image.id}/0"
        face = Face(image_id=image.id, event_id=event.id, embedding=[0.1] * 512,
                    bbox=[0.0, 0.0, 200.0, 200.0], quality_score=0.95,
                    compreface_subject_id=subject_id, reid_embedding=_vec(0.70))
        db.add(face); db.commit()
        return event, image, subject_id

    def _run(self, db, event, image, subject_id, *, reid_sims, gate_kept):
        scan_uuid = uuid.uuid4()
        candidates = [CandidateMatch(subject_id=subject_id, image_id=str(image.id),
                                     similarity=0.95, frame_index=0)]
        faces_by_subject = {subject_id: db.query(Face).filter(
            Face.compreface_subject_id == subject_id).first()}
        ga._record_scan_telemetry(
            db, scan_uuid=scan_uuid, session_id=uuid.uuid4(), event_id=event.id,
            candidates=candidates, faces_by_subject=faces_by_subject,
            config=MatchScoringConfig(), reid_sims=reid_sims, gate_kept=gate_kept,
        )
        return db.query(ScanMatchMetric).filter(ScanMatchMetric.scan_id == scan_uuid).all()

    def test_writes_sim_and_decision_kept(self, test_db):
        event, image, sid = self._seed(test_db)
        rows = self._run(test_db, event, image, sid,
                         reid_sims={sid: 0.70}, gate_kept={sid: True})
        assert len(rows) == 1
        assert rows[0].reid_similarity == pytest.approx(0.70)
        assert rows[0].reid_would_pass is True

    def test_writes_decision_dropped(self, test_db):
        event, image, sid = self._seed(test_db)
        rows = self._run(test_db, event, image, sid,
                         reid_sims={sid: 0.40}, gate_kept={sid: False})
        assert rows[0].reid_similarity == pytest.approx(0.40)
        assert rows[0].reid_would_pass is False

    def test_null_when_no_signal(self, test_db):
        event, image, sid = self._seed(test_db)
        rows = self._run(test_db, event, image, sid, reid_sims={}, gate_kept={})
        assert rows[0].reid_similarity is None
        assert rows[0].reid_would_pass is None


# --------------------------------------------------------------------------- #
# _compute_probe_reid — fail-soft
# --------------------------------------------------------------------------- #

class TestProbeReid:
    def _jpeg(self):
        buf = io.BytesIO()
        PILImage.new("RGB", (400, 500), (120, 120, 120)).save(buf, format="JPEG")
        return buf.getvalue()

    def test_empty_frames_none(self):
        assert asyncio.run(ga._compute_probe_reid([])) is None

    def test_disabled_returns_none(self):
        with patch.object(ga, "_detect_faces_compreface", new=AsyncMock()) as det:
            assert asyncio.run(ga._compute_probe_reid([self._jpeg()])) is None
        det.assert_not_called()

    def test_happy_path(self, enable_scan_gate):
        faces = [{"box": {"x_min": 100, "y_min": 100, "x_max": 200, "y_max": 200}}]
        with patch.object(ga, "_detect_faces_compreface", new=AsyncMock(return_value=faces)), \
             patch.object(ga, "compute_reid_embedding", new=AsyncMock(return_value=_vec(0.5))):
            out = asyncio.run(ga._compute_probe_reid([self._jpeg()]))
        assert out == _vec(0.5)

    def test_detection_failure_soft(self, enable_scan_gate):
        with patch.object(ga, "_detect_faces_compreface", new=AsyncMock(side_effect=RuntimeError("down"))), \
             patch.object(ga, "compute_reid_embedding", new=AsyncMock(return_value=_vec(0.5))):
            assert asyncio.run(ga._compute_probe_reid([self._jpeg()])) is None

    def test_no_face_detected_soft(self, enable_scan_gate):
        with patch.object(ga, "_detect_faces_compreface", new=AsyncMock(return_value=[])), \
             patch.object(ga, "compute_reid_embedding", new=AsyncMock(return_value=_vec(0.5))) as embed:
            assert asyncio.run(ga._compute_probe_reid([self._jpeg()])) is None
        embed.assert_not_called()
