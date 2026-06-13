"""Phase 2 Re-ID scan tests — cosine, the gate, shadow telemetry, probe.

Exercises the pure gate/cosine logic plus the telemetry write, without
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


def _scored(image_id: str, subject_id: str, sim: float) -> ScoredMatch:
    return ScoredMatch(
        image_id=image_id, subject_id=subject_id, similarity=sim,
        raw_similarity=sim, frame_count=1, score_gap=None,
        bbox=[0, 0, 200, 200], cluster_id=None, quality_score=0.95,
    )


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
# _apply_reid_gate (Phase 3 enforcement)
# --------------------------------------------------------------------------- #

class TestGate:
    def test_drops_face_confident_body_contradicted(self):
        """0.95 face / 0.40 body → the sibling case → dropped."""
        scored = [_scored("imgA", "sA", 0.95)]
        faces = {"sA": SimpleNamespace(reid_embedding=_vec(0.40))}
        assert ga._apply_reid_gate(scored, faces, PROBE) == []

    def test_keeps_face_and_body_agree(self):
        scored = [_scored("imgB", "sB", 0.95)]
        faces = {"sB": SimpleNamespace(reid_embedding=_vec(0.70))}
        assert len(ga._apply_reid_gate(scored, faces, PROBE)) == 1

    def test_null_candidate_embedding_bypasses(self):
        """Candidate still mid-backfill (NULL) is never gated out."""
        scored = [_scored("imgC", "sC", 0.95)]
        faces = {"sC": SimpleNamespace(reid_embedding=None)}
        assert len(ga._apply_reid_gate(scored, faces, PROBE)) == 1

    def test_below_face_floor_not_gated(self):
        """Match under reid_face_min_for_gate is left alone even on low body."""
        scored = [_scored("imgD", "sD", 0.80)]
        faces = {"sD": SimpleNamespace(reid_embedding=_vec(0.10))}
        assert len(ga._apply_reid_gate(scored, faces, PROBE)) == 1


# --------------------------------------------------------------------------- #
# Shadow telemetry — reid columns written, never enforced here
# --------------------------------------------------------------------------- #

class TestShadowTelemetry:
    def _seed(self, db, reid_vec):
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
                    compreface_subject_id=subject_id, reid_embedding=reid_vec)
        db.add(face); db.commit()
        return event, image, subject_id

    def _run(self, db, event, image, subject_id, probe):
        scan_uuid = uuid.uuid4()
        candidates = [CandidateMatch(subject_id=subject_id, image_id=str(image.id),
                                     similarity=0.95, frame_index=0)]
        faces_by_subject = {subject_id: db.query(Face).filter(
            Face.compreface_subject_id == subject_id).first()}
        ga._record_scan_telemetry(
            db, scan_uuid=scan_uuid, session_id=uuid.uuid4(), event_id=event.id,
            candidates=candidates, faces_by_subject=faces_by_subject,
            config=MatchScoringConfig(), probe_reid=probe,
        )
        return db.query(ScanMatchMetric).filter(ScanMatchMetric.scan_id == scan_uuid).all()

    def test_writes_reid_sim_and_would_pass_true(self, test_db):
        event, image, sid = self._seed(test_db, _vec(0.70))
        rows = self._run(test_db, event, image, sid, PROBE)
        assert len(rows) == 1
        assert rows[0].reid_similarity == pytest.approx(0.70, abs=1e-6)
        assert rows[0].reid_would_pass is True

    def test_would_pass_false_on_low_body(self, test_db):
        event, image, sid = self._seed(test_db, _vec(0.40))
        rows = self._run(test_db, event, image, sid, PROBE)
        assert rows[0].reid_similarity == pytest.approx(0.40, abs=1e-6)
        assert rows[0].reid_would_pass is False

    def test_null_when_no_probe(self, test_db):
        """No full frame → probe None → reid columns stay NULL."""
        event, image, sid = self._seed(test_db, _vec(0.70))
        rows = self._run(test_db, event, image, sid, None)
        assert rows[0].reid_similarity is None
        assert rows[0].reid_would_pass is None

    def test_null_when_candidate_unbackfilled(self, test_db):
        event, image, sid = self._seed(test_db, None)
        rows = self._run(test_db, event, image, sid, PROBE)
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
        """conftest leaves both flags off → no detection call, None."""
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
