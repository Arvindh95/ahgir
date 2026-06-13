import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from hypothesis import settings, Verbosity, HealthCheck
import redis
from app.main import app
from app.database import Base, get_db
from app.models import User, Event, Image, Face, GuestSession, AuditLog, RateLimit
from app.rate_limiter import (
    RateLimiter,
    auth_rate_limiter,
    download_ip_rate_limiter,
    event_passcode_ip_rate_limiter,
    event_passcode_rate_limiter,
    scan_ip_rate_limiter,
    share_rate_limiter,
)

# Configure Hypothesis for faster test runs
settings.register_profile("ci", max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
settings.register_profile("dev", max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "ci"))

# Test database URL — accept full TEST_DATABASE_URL override, else compose
# from parts. Default DB host is `postgres` (the docker-compose service
# name) so a `docker exec picur-backend pytest ...` run works without
# extra env. Outside the docker network — bare-metal local dev or CI on
# a runner with a localhost Postgres — set POSTGRES_HOST=localhost.
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_USER = os.getenv("POSTGRES_USER", "picur")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "picur")
DB_NAME = os.getenv("POSTGRES_TEST_DB", "picur_test")
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

# If POSTGRES_HOST defaulted to 'postgres' and we can't resolve it,
# fall back to localhost — this lets `pytest -q` work on a bare host
# with `docker compose up postgres redis` instead of requiring a full
# in-container test run. The fallback is silent because either DNS
# answer is valid in the right context; we don't want to noise up the
# CI logs when 'postgres' is the docker service and resolves fine.
if DB_HOST == "postgres":
    import socket
    try:
        socket.gethostbyname("postgres")
    except socket.gaierror:
        TEST_DATABASE_URL = TEST_DATABASE_URL.replace("@postgres:", "@localhost:")
        REDIS_FALLBACK_HOST = "localhost"
    else:
        REDIS_FALLBACK_HOST = None
else:
    REDIS_FALLBACK_HOST = None

# Test Redis URL
REDIS_HOST = os.getenv("REDIS_HOST", REDIS_FALLBACK_HOST or "redis")
if REDIS_HOST == "redis" and REDIS_FALLBACK_HOST == "localhost":
    REDIS_HOST = "localhost"
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
TEST_REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"  # Use DB 1 for tests

@pytest.fixture(scope="session")
def engine():
    """Create test database engine"""
    return create_engine(TEST_DATABASE_URL)

@pytest.fixture(scope="session")
def tables(engine):
    """Build the test schema by running alembic upgrade head.

    Previously this used Base.metadata.create_all(), which generates
    tables straight from the ORM models. That's faster but lets the
    migration history drift from the model — a broken or missing
    migration could pass tests AND fail production deploy. Running
    alembic against the test DB closes that gap: the schema tests
    exercise is the exact same one alembic upgrade head produces in
    prod, so a regression in any migration surfaces immediately.

    On teardown we drop the schema and recreate the pgvector extension
    so the next pytest session starts clean.
    """
    from alembic import command
    from alembic.config import Config

    # Wipe any leftover schema from a prior session so the alembic
    # upgrade starts from a clean slate (re-runs are idempotent only if
    # the prior migration succeeded; flushing avoids half-applied
    # states from blocking a clean run).
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    yield

    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="session")
def session_factory(engine, tables):
    """Session factory for property-based tests"""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session(engine, tables):
    """Database session for tests"""
    connection = engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

@pytest.fixture
def test_db(db_session):
    """Alias for db_session to match test expectations"""
    return db_session

@pytest.fixture
def client(db_session):
    """FastAPI test client with database dependency override.

    Always sends `X-Requested-With: XMLHttpRequest`. The production
    CsrfMiddleware requires this header on any state-changing request
    that carries an auth cookie; the real browser axios client sets it
    automatically. Doing the same here means the existing test suite
    doesn't have to add it on every client.post() call.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    tc = TestClient(app)
    tc.headers.update({"X-Requested-With": "XMLHttpRequest"})
    yield tc
    app.dependency_overrides.clear()

@pytest.fixture(scope="session")
def redis_client():
    """Redis client for testing"""
    client = redis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    # Cleanup: flush test database
    client.flushdb()
    client.close()


@pytest.fixture(scope="session", autouse=True)
def _flush_app_cache_at_session_start():
    """Flush the application's redis cache (DB 0) once at session start
    so cached fixtures from a prior pytest invocation don't poison the
    current run.

    Symptom that motivated this: test_get_event_by_valid_slug seeds an
    Event with hardcoded slug 'test-wedding-2024'; the /e/{slug}
    endpoint caches the response in DB 0; the db_session fixture rolls
    back the seed; the next pytest invocation creates a NEW event with
    the same slug but the cache hit returns the prior run's event_id.

    The standard `redis_client` fixture only flushes DB 1 (the rate-
    limiter test DB). DB 0 holds the app's own cache.
    """
    from app.cache import get_redis

    try:
        get_redis().flushdb()
    except Exception:
        # Test redis may be unreachable in pure-unit runs; not fatal.
        pass
    yield

@pytest.fixture
def rate_limiter(redis_client):
    """Rate limiter instance for testing"""
    limiter = RateLimiter(redis_client, limit=10, window_hours=1)
    yield limiter
    # Cleanup: flush between tests
    redis_client.flushdb()


@pytest.fixture(autouse=True)
def _disable_reid_in_tests():
    """Default-off in tests so existing indexer / scan tests that mock
    `_run_async` (face_indexer_compreface) don't have to know about Re-ID.
    Production defaults to ON; the env-driven setting in app/config.py wins
    at startup, this fixture flips it locally for the test run only.

    Tests that exercise the Re-ID path explicitly (e.g. test_reid_client)
    re-enable it via their own fixture before assertions.
    """
    from app.config import settings as app_settings
    original_index = app_settings.reid_enabled_indexing
    original_scan = app_settings.reid_enabled_scan
    app_settings.reid_enabled_indexing = False
    app_settings.reid_enabled_scan = False
    try:
        yield
    finally:
        app_settings.reid_enabled_indexing = original_index
        app_settings.reid_enabled_scan = original_scan


@pytest.fixture(autouse=True)
def _lift_auth_rate_limits():
    """The TestClient always sources requests from a single 'testclient' IP and
    we share the production Redis bucket. Without this, sequential auth /
    guest_auth / passcode calls within a single test (and across tests) trip
    the per-IP limiter. The scan rate limiter is intentionally NOT touched so
    test_rate_limiting_integration can still exercise the scan budget.
    """
    # scan_ip_rate_limiter / download_ip_rate_limiter / event_passcode_ip
    # _rate_limiter are included so the corresponding per-session /
    # per-slug rate tests aren't tripped by a parallel per-IP budget —
    # those tests deliberately exercise one tier. The dedicated abuse-
    # control tests dial individual limits DOWN locally to assert the
    # per-IP budget survives session / IP rotation.
    affected = (
        auth_rate_limiter,
        event_passcode_rate_limiter,
        event_passcode_ip_rate_limiter,
        share_rate_limiter,
        scan_ip_rate_limiter,
        download_ip_rate_limiter,
    )
    originals = [(lim, lim.limit) for lim in affected]
    for lim in affected:
        lim.limit = 10_000
        for action in (
            "guest_auth", "register", "login", "passcode", "share",
            "forgot_password", "resend_verify",
        ):
            try:
                lim.reset_limit("testclient", action)
            except Exception:
                # Redis may be unavailable in some unit-only test runs; the
                # bumped limit alone is enough to keep tests passing.
                pass
    try:
        yield
    finally:
        for lim, original_limit in originals:
            lim.limit = original_limit
