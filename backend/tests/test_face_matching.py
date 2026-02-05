"""
Unit tests for face matching service
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid
import base64
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image as PILImage
from unittest.mock import patch, MagicMock

from app.main import app
from app.database import get_db
from app.models import User, Event, Image, Face, GuestSession
from app.auth import hash_password, create_event_token
from app.storage import storage_service

client = TestClient(app)


def create_dummy_image_bytes() -> bytes:
    """Create a simple dummy image for testing."""
    img = PILImage.new('RGB', (100, 100), color='white')
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    return buffer.getvalue()


def create_test_embedding() -> np.ndarray:
    """Create a normalized test embedding."""
    embedding = np.random.randn(512)
    return embedding / np.linalg.norm(embedding)


@pytest.fixture
def setup_event_with_faces(db_session: Session):
    """Setup an event with images and faces for testing."""
    # Create admin user
    admin = User(
        email=f"admin_{uuid.uuid4()}@example.com",
        password_hash=hash_password("password")
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    
    # Create event
    event = Event(
        owner_user_id=admin.id,
        slug=f"event-{uuid.uuid4().hex[:8]}",
        name="Test Event",
        allow_downloads=True,
        retention_days=90
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    
    # Create query embedding
    query_embedding = create_test_embedding()
    
    # Create images and faces
    images = []
    faces = []
    
    for i in range(3):
        image = Image(
            event_id=event.id,
            filename=f"image_{i}.jpg",
            file_hash=f"hash_{uuid.uuid4().hex}",
            size_bytes=1024,
            status="indexed",
            face_count=1
        )
        db_session.add(image)
        images.append(image)
    
    db_session.commit()
    
    # Create faces with high similarity to query
    for i, image in enumerate(images):
        db_session.refresh(image)
        
        # Create embedding close to query
        face_embedding = query_embedding + np.random.randn(512) * 0.05
        face_embedding = face_embedding / np.linalg.norm(face_embedding)
        
        face = Face(
            image_id=image.id,
            event_id=event.id,
            embedding=face_embedding.tolist(),
            bbox=[10.0 + i * 10, 10.0 + i * 10, 50.0 + i * 10, 50.0 + i * 10],
            quality_score=0.9
        )
        db_session.add(face)
        faces.append(face)
    
    db_session.commit()
    
    # Generate Event_Token
    session_id = uuid.uuid4()
    event_token = create_event_token(event.id, session_id)
    
    # Store session
    guest_session = GuestSession(
        id=session_id,
        event_id=event.id,
        session_token=event_token,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db_session.add(guest_session)
    db_session.commit()
    
    return {
        "admin": admin,
        "event": event,
        "images": images,
        "faces": faces,
        "event_token": event_token,
        "query_embedding": query_embedding
    }


def test_successful_face_scan_with_matches(db_session: Session, setup_event_with_faces):
    """
    Test successful face scan with matches
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 8.1, 8.3
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        data = setup_event_with_faces
        event_token = data["event_token"]
        query_embedding = data["query_embedding"]
        
        # Create a dummy face image
        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Mock face detection to return our query embedding
        with patch('app.routers.guest.face_detector.detect_faces') as mock_detect:
            mock_detect.return_value = [(query_embedding, [10, 10, 50, 50], 0.9)]
            
            # Mock storage service to avoid MinIO calls
            with patch.object(storage_service, 'generate_presigned_url') as mock_presigned:
                mock_presigned.return_value = "https://minio.example.com/presigned-url"
                
                # Perform face scan
                response = client.post(
                    "/scan",
                    json={"image": image_b64},
                    headers={"Authorization": f"Bearer {event_token}"}
                )
        
        assert response.status_code == 200
        scan_result = response.json()
        
        # Verify response structure
        assert "matches" in scan_result
        assert "scan_id" in scan_result
        assert "total_matches" in scan_result
        
        # Verify matches
        matches = scan_result["matches"]
        assert len(matches) > 0, "Should have at least one match"
        
        # Verify match structure
        for match in matches:
            assert "image_id" in match
            assert "similarity" in match
            assert "thumbnail_url" in match
            assert "original_url" in match
            assert "download_url" in match  # Event has allow_downloads=True
            assert "face_bbox" in match
            
            # Verify similarity is above threshold
            assert match["similarity"] > 0.6, "Similarity should be above default threshold"
            
            # Verify URLs are present
            assert match["thumbnail_url"] is not None
            assert match["original_url"] is not None
            assert match["download_url"] is not None
    
    finally:
        app.dependency_overrides.clear()


def test_face_scan_with_no_matches(db_session: Session, setup_event_with_faces):
    """
    Test face scan with no matches
    
    Requirements: 6.7
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        data = setup_event_with_faces
        event_token = data["event_token"]
        
        # Create a completely different embedding that won't match
        different_embedding = create_test_embedding()
        
        # Create a dummy face image
        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Mock face detection to return a very different embedding
        with patch('app.routers.guest.face_detector.detect_faces') as mock_detect:
            mock_detect.return_value = [(different_embedding, [10, 10, 50, 50], 0.9)]
            
            # Perform face scan
            response = client.post(
                "/scan",
                json={"image": image_b64},
                headers={"Authorization": f"Bearer {event_token}"}
            )
        
        assert response.status_code == 200
        scan_result = response.json()
        
        # Verify response structure
        assert "matches" in scan_result
        assert "scan_id" in scan_result
        assert "total_matches" in scan_result
        
        # Verify no matches or very few matches
        matches = scan_result["matches"]
        assert scan_result["total_matches"] == len(matches)
    
    finally:
        app.dependency_overrides.clear()


def test_face_scan_with_no_face_detected(db_session: Session, setup_event_with_faces):
    """
    Test face scan with no face detected in the scan image
    
    Requirements: 6.1, 6.2
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        data = setup_event_with_faces
        event_token = data["event_token"]
        
        # Create a dummy face image
        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Mock face detection to return no faces
        with patch('app.routers.guest.face_detector.detect_faces') as mock_detect:
            mock_detect.return_value = []  # No faces detected
            
            # Perform face scan
            response = client.post(
                "/scan",
                json={"image": image_b64},
                headers={"Authorization": f"Bearer {event_token}"}
            )
        
        assert response.status_code == 200
        scan_result = response.json()
        
        # Verify response structure
        assert "matches" in scan_result
        assert "scan_id" in scan_result
        assert "total_matches" in scan_result
        
        # Verify no matches when no face is detected
        assert len(scan_result["matches"]) == 0
        assert scan_result["total_matches"] == 0
    
    finally:
        app.dependency_overrides.clear()


def test_download_url_generation_based_on_allow_downloads(db_session: Session):
    """
    Test download URL generation based on allow_downloads setting
    
    Requirements: 8.4
    """
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Test with allow_downloads=False
        admin = User(
            email=f"admin_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
        
        # Create event with downloads disabled
        event = Event(
            owner_user_id=admin.id,
            slug=f"event-{uuid.uuid4().hex[:8]}",
            name="Test Event",
            allow_downloads=False,  # Downloads disabled
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        
        # Create image and face
        image = Image(
            event_id=event.id,
            filename="test.jpg",
            file_hash=f"hash_{uuid.uuid4().hex}",
            size_bytes=1024,
            status="indexed",
            face_count=1
        )
        db_session.add(image)
        db_session.commit()
        db_session.refresh(image)
        
        query_embedding = create_test_embedding()
        face_embedding = query_embedding + np.random.randn(512) * 0.05
        face_embedding = face_embedding / np.linalg.norm(face_embedding)
        
        face = Face(
            image_id=image.id,
            event_id=event.id,
            embedding=face_embedding.tolist(),
            bbox=[10.0, 10.0, 50.0, 50.0],
            quality_score=0.9
        )
        db_session.add(face)
        db_session.commit()
        
        # Generate Event_Token
        session_id = uuid.uuid4()
        event_token = create_event_token(event.id, session_id)
        
        guest_session = GuestSession(
            id=session_id,
            event_id=event.id,
            session_token=event_token,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db_session.add(guest_session)
        db_session.commit()
        
        # Create a dummy face image
        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Mock face detection
        with patch('app.routers.guest.face_detector.detect_faces') as mock_detect:
            mock_detect.return_value = [(query_embedding, [10, 10, 50, 50], 0.9)]
            
            # Mock storage service
            with patch.object(storage_service, 'generate_presigned_url') as mock_presigned:
                mock_presigned.return_value = "https://minio.example.com/presigned-url"
                
                # Perform face scan
                response = client.post(
                    "/scan",
                    json={"image": image_b64},
                    headers={"Authorization": f"Bearer {event_token}"}
                )
        
        assert response.status_code == 200
        scan_result = response.json()
        
        # Verify matches
        matches = scan_result["matches"]
        if len(matches) > 0:
            for match in matches:
                # When downloads are disabled, download_url should be None
                assert match.get("download_url") is None, \
                    "download_url should be None when allow_downloads is False"
                
                # But thumbnail and original URLs should still be present for viewing
                assert match.get("thumbnail_url") is not None
                assert match.get("original_url") is not None
    
    finally:
        app.dependency_overrides.clear()


def test_face_scan_with_invalid_token(db_session: Session):
    """Test face scan with invalid or missing token"""
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        image_bytes = create_dummy_image_bytes()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Test without token
        response = client.post(
            "/scan",
            json={"image": image_b64}
        )
        assert response.status_code == 403  # Forbidden without auth
        
        # Test with invalid token
        response = client.post(
            "/scan",
            json={"image": image_b64},
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401  # Unauthorized
    
    finally:
        app.dependency_overrides.clear()


def test_face_scan_with_invalid_base64(db_session: Session, setup_event_with_faces):
    """Test face scan with invalid base64 image data"""
    # Override the get_db dependency
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        data = setup_event_with_faces
        event_token = data["event_token"]
        
        # Test with invalid base64
        response = client.post(
            "/scan",
            json={"image": "not_valid_base64!!!"},
            headers={"Authorization": f"Bearer {event_token}"}
        )
        assert response.status_code == 400  # Bad request
        assert "invalid" in response.json()["detail"].lower()
    
    finally:
        app.dependency_overrides.clear()
