import pytest
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from hypothesis import settings, Verbosity, HealthCheck
import redis
from app.main import app
from app.database import Base, get_db
from app.models import User, Event, Image, Face, GuestSession, AuditLog, RateLimit
from app.rate_limiter import RateLimiter

# Configure Hypothesis for faster test runs
settings.register_profile("ci", max_examples=20, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
settings.register_profile("dev", max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "ci"))

# Test database URL - use environment variable for host (defaults to localhost for local testing)
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
TEST_DATABASE_URL = f"postgresql://picur:picur@{DB_HOST}:{DB_PORT}/picur_test"

# Test Redis URL
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
TEST_REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"  # Use DB 1 for tests

@pytest.fixture(scope="session")
def engine():
    """Create test database engine"""
    return create_engine(TEST_DATABASE_URL)

@pytest.fixture(scope="session")
def tables(engine):
    """Create all tables for testing"""
    Base.metadata.create_all(bind=engine)
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
    """FastAPI test client with database dependency override"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture(scope="session")
def redis_client():
    """Redis client for testing"""
    client = redis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    # Cleanup: flush test database
    client.flushdb()
    client.close()

@pytest.fixture
def rate_limiter(redis_client):
    """Rate limiter instance for testing"""
    limiter = RateLimiter(redis_client, limit=10, window_hours=1)
    yield limiter
    # Cleanup: flush between tests
    redis_client.flushdb()
