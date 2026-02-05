"""Unit tests for health check endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import OperationalError
from minio.error import S3Error
import redis

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_all_services_healthy():
    """Test health check when all services are healthy."""
    with patch('app.routers.health.engine.connect') as mock_db, \
         patch('app.routers.health.storage_service.client.bucket_exists') as mock_minio, \
         patch('app.routers.health.redis_client.ping') as mock_redis:
        
        # Mock successful connections
        mock_db.return_value.__enter__ = MagicMock()
        mock_db.return_value.__exit__ = MagicMock()
        mock_minio.return_value = True
        mock_redis.return_value = True
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["services"]["database"]["status"] == "healthy"
        assert data["services"]["minio"]["status"] == "healthy"
        assert data["services"]["redis"]["status"] == "healthy"


def test_health_check_database_unhealthy():
    """Test health check when database is unhealthy."""
    with patch('app.routers.health.engine.connect') as mock_db, \
         patch('app.routers.health.storage_service.client.bucket_exists') as mock_minio, \
         patch('app.routers.health.redis_client.ping') as mock_redis:
        
        # Mock database failure
        mock_db.side_effect = OperationalError("Connection failed", None, None)
        mock_minio.return_value = True
        mock_redis.return_value = True
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert data["services"]["database"]["status"] == "unhealthy"
        assert "error" in data["services"]["database"]
        assert data["services"]["minio"]["status"] == "healthy"
        assert data["services"]["redis"]["status"] == "healthy"


def test_health_check_minio_unhealthy():
    """Test health check when MinIO is unhealthy."""
    with patch('app.routers.health.engine.connect') as mock_db, \
         patch('app.routers.health.storage_service.client.bucket_exists') as mock_minio, \
         patch('app.routers.health.redis_client.ping') as mock_redis:
        
        # Mock MinIO failure
        mock_db.return_value.__enter__ = MagicMock()
        mock_db.return_value.__exit__ = MagicMock()
        mock_minio.side_effect = S3Error(
            code="ServiceUnavailable",
            message="Service unavailable",
            resource="",
            request_id="",
            host_id="",
            response=""
        )
        mock_redis.return_value = True
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert data["services"]["database"]["status"] == "healthy"
        assert data["services"]["minio"]["status"] == "unhealthy"
        assert "error" in data["services"]["minio"]
        assert data["services"]["redis"]["status"] == "healthy"


def test_health_check_redis_unhealthy():
    """Test health check when Redis is unhealthy."""
    with patch('app.routers.health.engine.connect') as mock_db, \
         patch('app.routers.health.storage_service.client.bucket_exists') as mock_minio, \
         patch('app.routers.health.redis_client.ping') as mock_redis:
        
        # Mock Redis failure
        mock_db.return_value.__enter__ = MagicMock()
        mock_db.return_value.__exit__ = MagicMock()
        mock_minio.return_value = True
        mock_redis.side_effect = redis.RedisError("Connection refused")
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert data["services"]["database"]["status"] == "healthy"
        assert data["services"]["minio"]["status"] == "healthy"
        assert data["services"]["redis"]["status"] == "unhealthy"
        assert "error" in data["services"]["redis"]


def test_health_check_multiple_services_unhealthy():
    """Test health check when multiple services are unhealthy."""
    with patch('app.routers.health.engine.connect') as mock_db, \
         patch('app.routers.health.storage_service.client.bucket_exists') as mock_minio, \
         patch('app.routers.health.redis_client.ping') as mock_redis:
        
        # Mock multiple failures
        mock_db.side_effect = OperationalError("DB Connection failed", None, None)
        mock_minio.side_effect = S3Error(
            code="ServiceUnavailable",
            message="Service unavailable",
            resource="",
            request_id="",
            host_id="",
            response=""
        )
        mock_redis.side_effect = redis.RedisError("Connection refused")
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert data["services"]["database"]["status"] == "unhealthy"
        assert data["services"]["minio"]["status"] == "unhealthy"
        assert data["services"]["redis"]["status"] == "unhealthy"
        assert "error" in data["services"]["database"]
        assert "error" in data["services"]["minio"]
        assert "error" in data["services"]["redis"]


def test_health_check_generic_exception_handling():
    """Test health check handles generic exceptions gracefully."""
    with patch('app.routers.health.engine.connect') as mock_db, \
         patch('app.routers.health.storage_service.client.bucket_exists') as mock_minio, \
         patch('app.routers.health.redis_client.ping') as mock_redis:
        
        # Mock generic exceptions
        mock_db.return_value.__enter__ = MagicMock()
        mock_db.return_value.__exit__ = MagicMock()
        mock_minio.side_effect = Exception("Unexpected error")
        mock_redis.side_effect = Exception("Unexpected error")
        
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert data["services"]["database"]["status"] == "healthy"
        assert data["services"]["minio"]["status"] == "unhealthy"
        assert data["services"]["redis"]["status"] == "unhealthy"
        assert "Unexpected error" in data["services"]["minio"]["error"]
        assert "Unexpected error" in data["services"]["redis"]["error"]
