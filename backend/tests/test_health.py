"""Unit tests for health check endpoints."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.exc import OperationalError
from minio.error import S3Error
import redis

from fastapi.testclient import TestClient
from app.main import app
from app.routers.admin import get_superadmin_user

client = TestClient(app)
client.headers.update({"X-Requested-With": "XMLHttpRequest"})

# /health/deep now requires a superadmin user. Tests verify the deep-probe
# logic, not the auth boundary, so override the dependency for the whole
# module with a stub user. The real superadmin gate is covered separately
# in test_security_regressions.py.
class _StubSuperadmin:
    id = "test-superadmin"
    is_superadmin = True

app.dependency_overrides[get_superadmin_user] = lambda: _StubSuperadmin()


@pytest.fixture(autouse=True)
def _clear_module_client_cookies():
    """Reset cookies between tests so a stale picur_session/picur_event
    from a prior test does not poison auth on the next test."""
    client.cookies.clear()
    yield


def _build_s3_error() -> S3Error:
    return S3Error(
        code="ServiceUnavailable",
        message="Service unavailable",
        resource="",
        request_id="",
        host_id="",
        response="",
    )


@pytest.fixture
def health_mocks():
    """Patch every external dependency the /health endpoint touches.

    Yields a dict so each test can override individual mocks (e.g. flip a
    side_effect) without re-declaring all four patch lines.

    settings.environment is forced to 'test' so the production error-string
    stripper in health.py does not remove the fields tests assert on.
    """
    # Build a fake RQ worker that reports a fresh heartbeat. Conftest
    # now flushes the app Redis (DB 0) at session start, so any
    # leftover real worker heartbeat from prior runs is gone — without
    # the worker mock, /health reports worker=unhealthy (alive_count=0)
    # and the test's overall "healthy" assertion flips.
    from datetime import datetime as _dt, timezone as _tz

    _fake_worker = MagicMock()
    _fake_worker.last_heartbeat = _dt.now(_tz.utc)

    with patch('app.routers.health.engine.connect') as mock_db, \
         patch('app.routers.health.storage_service.client.bucket_exists') as mock_minio, \
         patch('app.routers.health.redis_client.ping') as mock_redis, \
         patch('app.routers.health.CompreFaceClient') as mock_cf_cls, \
         patch('rq.Worker.all', return_value=[_fake_worker]), \
         patch('app.routers.health.settings.environment', 'test'):
        # Default: every service healthy.
        mock_db.return_value.__enter__ = MagicMock()
        mock_db.return_value.__exit__ = MagicMock()
        mock_minio.return_value = True
        mock_redis.return_value = True
        cf_instance = mock_cf_cls.return_value
        cf_instance.health_check = AsyncMock(return_value=True)
        yield {
            "db": mock_db,
            "minio": mock_minio,
            "redis": mock_redis,
            "compreface": cf_instance,
        }


def test_liveness_probe_is_cheap_and_public():
    """/health is the public liveness probe: returns {"status": "healthy"}
    and must NOT poll DB / MinIO / Redis / CompreFace. Test confirms a hit
    works even when those dependencies are NOT mocked — proof that the
    handler never touches them. "healthy" string preserves wire-compat
    with scripts/picur-monitor.sh."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_check_all_services_healthy(health_mocks):
    response = client.get("/health/deep")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["services"]["database"]["status"] == "healthy"
    assert data["services"]["minio"]["status"] == "healthy"
    assert data["services"]["redis"]["status"] == "healthy"
    assert data["services"]["compreface"]["status"] == "healthy"


def test_health_check_database_unhealthy(health_mocks):
    health_mocks["db"].side_effect = OperationalError("Connection failed", None, None)

    response = client.get("/health/deep")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "unhealthy"
    assert data["services"]["database"]["status"] == "unhealthy"
    assert "error" in data["services"]["database"]
    assert data["services"]["minio"]["status"] == "healthy"
    assert data["services"]["redis"]["status"] == "healthy"


def test_health_check_minio_unhealthy(health_mocks):
    health_mocks["minio"].side_effect = _build_s3_error()

    response = client.get("/health/deep")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "unhealthy"
    assert data["services"]["database"]["status"] == "healthy"
    assert data["services"]["minio"]["status"] == "unhealthy"
    assert "error" in data["services"]["minio"]
    assert data["services"]["redis"]["status"] == "healthy"


def test_health_check_redis_unhealthy(health_mocks):
    health_mocks["redis"].side_effect = redis.RedisError("Connection refused")

    response = client.get("/health/deep")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "unhealthy"
    assert data["services"]["database"]["status"] == "healthy"
    assert data["services"]["minio"]["status"] == "healthy"
    assert data["services"]["redis"]["status"] == "unhealthy"
    assert "error" in data["services"]["redis"]


def test_health_check_multiple_services_unhealthy(health_mocks):
    health_mocks["db"].side_effect = OperationalError("DB Connection failed", None, None)
    health_mocks["minio"].side_effect = _build_s3_error()
    health_mocks["redis"].side_effect = redis.RedisError("Connection refused")

    response = client.get("/health/deep")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "unhealthy"
    assert data["services"]["database"]["status"] == "unhealthy"
    assert data["services"]["minio"]["status"] == "unhealthy"
    assert data["services"]["redis"]["status"] == "unhealthy"
    assert "error" in data["services"]["database"]
    assert "error" in data["services"]["minio"]
    assert "error" in data["services"]["redis"]


def test_health_check_generic_exception_handling(health_mocks):
    health_mocks["minio"].side_effect = Exception("Unexpected error")
    health_mocks["redis"].side_effect = Exception("Unexpected error")

    response = client.get("/health/deep")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "unhealthy"
    assert data["services"]["database"]["status"] == "healthy"
    assert data["services"]["minio"]["status"] == "unhealthy"
    assert data["services"]["redis"]["status"] == "unhealthy"
    assert "Unexpected error" in data["services"]["minio"]["error"]
    assert "Unexpected error" in data["services"]["redis"]["error"]
