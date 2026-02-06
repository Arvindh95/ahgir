"""Unit tests for face indexing functionality with CompreFace."""

import pytest
import uuid
from PIL import Image as PILImage
from io import BytesIO
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock

from app.models import Image, Event, User, Face
from app.workers.face_indexer_compreface import index_photo_compreface
from app.storage import storage_service
from app.auth import hash_password
from app.queue import enqueue_face_indexing


def create_test_image_with_faces(num_faces: int = 1) -> bytes:
    """Create a test image with face-like patterns."""
    img = PILImage.new('RGB', (400, 400), color='white')

    import PIL.ImageDraw as ImageDraw
    draw = ImageDraw.Draw(img)

    # Draw multiple faces
    for i in range(num_faces):
        x_offset = (i % 2) * 200
        y_offset = (i // 2) * 200

        # Face circle
        draw.ellipse([50 + x_offset, 50 + y_offset, 150 + x_offset, 150 + y_offset],
                     fill='beige', outline='black')
        # Eyes
        draw.ellipse([70 + x_offset, 80 + y_offset, 85 + x_offset, 95 + y_offset],
                     fill='black')
        draw.ellipse([115 + x_offset, 80 + y_offset, 130 + x_offset, 95 + y_offset],
                     fill='black')
        # Mouth
        draw.arc([75 + x_offset, 110 + y_offset, 125 + x_offset, 130 + y_offset],
                 0, 180, fill='black', width=2)

    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    buffer.seek(0)
    return buffer.getvalue()


def create_test_image_no_faces() -> bytes:
    """Create a test image without faces (solid color)."""
    img = PILImage.new('RGB', (200, 200), color='blue')
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    buffer.seek(0)
    return buffer.getvalue()


def create_mock_compreface_detect_response(num_faces: int = 1):
    """Create a mock CompreFace detection response."""
    faces = []
    for i in range(num_faces):
        faces.append({
            "box": {
                "x_min": 50 + (i * 100),
                "y_min": 50 + (i * 100),
                "x_max": 150 + (i * 100),
                "y_max": 150 + (i * 100)
            },
            "probability": 0.95
        })
    return faces


def create_mock_compreface_add_response():
    """Create a mock CompreFace add face response."""
    return {
        "image_id": str(uuid.uuid4()),
        "subject": "test_subject"
    }


class TestFaceIndexingWorker:
    """Tests for face indexing worker with CompreFace."""

    @patch('app.workers.face_indexer_compreface._run_async')
    def test_index_photo_with_faces(self, mock_run_async, test_db):
        """Test indexing a photo with faces using CompreFace."""
        # Setup mocks
        mock_detect = create_mock_compreface_detect_response(num_faces=2)
        mock_add = create_mock_compreface_add_response()

        # Mock async calls - detect returns faces, add returns success
        mock_run_async.side_effect = [
            mock_detect,  # First call: detect faces
            mock_add,     # Second call: add first face
            mock_add,     # Third call: add second face
        ]

        # Create test user
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        test_db.add(user)
        test_db.commit()

        # Create test event
        event = Event(
            owner_user_id=user.id,
            slug=f"test-event-{uuid.uuid4()}",
            name="Test Event",
            allow_downloads=True,
            retention_days=90
        )
        test_db.add(event)
        test_db.commit()

        # Create test image
        image = Image(
            event_id=event.id,
            filename="test.jpg",
            file_hash=f"hash_{uuid.uuid4()}",
            size_bytes=1024,
            width=400,
            height=400,
            status='pending',
            face_count=0
        )
        test_db.add(image)
        test_db.commit()

        # Upload test image to MinIO
        image_bytes = create_test_image_with_faces(num_faces=2)
        storage_service.upload_photo(
            event_id=event.id,
            image_id=image.id,
            photo_data=image_bytes,
            photo_type='original'
        )

        # Process the image
        result = index_photo_compreface(str(image.id), "test-api-key", db_session=test_db)

        # Refresh image from database
        test_db.refresh(image)

        # Verify result
        assert result['image_id'] == str(image.id)
        assert result['status'] == 'indexed', "Status should be indexed"
        assert result['face_count'] == 2, "Should have detected 2 faces"

        # Verify image status updated
        assert image.status == 'indexed', "Image status should be indexed"
        assert image.face_count == 2, "Face count should be 2"
        assert image.indexed_at is not None, "indexed_at should be set"

        # Verify faces in database
        faces = test_db.query(Face).filter(Face.image_id == image.id).all()
        assert len(faces) == 2, "Should have 2 faces stored"

        # Verify face data
        for face in faces:
            assert face.event_id == event.id, "Face should have correct event_id"
            assert len(face.bbox) == 4, "Bounding box should have 4 coordinates"
            assert 0 <= face.quality_score <= 1, "Quality score should be between 0 and 1"
            assert face.compreface_subject_id is not None, "Should have CompreFace subject ID"

        # Cleanup
        storage_service.delete_photo(event.id, image.id)

    @patch('app.workers.face_indexer_compreface._run_async')
    def test_index_photo_no_faces(self, mock_run_async, test_db):
        """Test indexing a photo with no faces."""
        # Setup mocks - empty face list
        mock_run_async.return_value = []

        # Create test user
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        test_db.add(user)
        test_db.commit()

        # Create test event
        event = Event(
            owner_user_id=user.id,
            slug=f"test-event-{uuid.uuid4()}",
            name="Test Event",
            allow_downloads=True,
            retention_days=90
        )
        test_db.add(event)
        test_db.commit()

        # Create test image
        image = Image(
            event_id=event.id,
            filename="test.jpg",
            file_hash=f"hash_{uuid.uuid4()}",
            size_bytes=1024,
            width=200,
            height=200,
            status='pending',
            face_count=0
        )
        test_db.add(image)
        test_db.commit()

        # Upload test image without faces to MinIO
        image_bytes = create_test_image_no_faces()
        storage_service.upload_photo(
            event_id=event.id,
            image_id=image.id,
            photo_data=image_bytes,
            photo_type='original'
        )

        # Process the image
        result = index_photo_compreface(str(image.id), "test-api-key", db_session=test_db)

        # Refresh image from database
        test_db.refresh(image)

        # Verify result
        assert result['image_id'] == str(image.id)
        assert result['status'] == 'no_faces', "Status should be no_faces"
        assert result['face_count'] == 0, "Face count should be 0"

        # Verify image status updated
        assert image.status == 'no_faces', "Image status should be no_faces"
        assert image.face_count == 0, "Face count should be 0"
        assert image.indexed_at is not None, "indexed_at should be set"

        # Verify no faces in database
        faces = test_db.query(Face).filter(Face.image_id == image.id).all()
        assert len(faces) == 0, "No faces should be stored"

        # Cleanup
        storage_service.delete_photo(event.id, image.id)

    def test_index_photo_error_handling(self, test_db):
        """Test error handling when photo download fails."""
        # Create test user
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        test_db.add(user)
        test_db.commit()

        # Create test event
        event = Event(
            owner_user_id=user.id,
            slug=f"test-event-{uuid.uuid4()}",
            name="Test Event",
            allow_downloads=True,
            retention_days=90
        )
        test_db.add(event)
        test_db.commit()

        # Create test image
        image = Image(
            event_id=event.id,
            filename="test.jpg",
            file_hash=f"hash_{uuid.uuid4()}",
            size_bytes=1024,
            width=200,
            height=200,
            status='pending',
            face_count=0
        )
        test_db.add(image)
        test_db.commit()

        # Don't upload image to MinIO - this will cause download to fail

        # Process the image
        result = index_photo_compreface(str(image.id), "test-api-key", db_session=test_db)

        # Refresh image from database
        test_db.refresh(image)

        # Verify result
        assert result['image_id'] == str(image.id)
        assert result['status'] == 'failed', "Status should be failed"
        assert 'error' in result, "Result should contain error message"

        # Verify image status updated to failed
        assert image.status == 'failed', "Image status should be failed"
        assert image.face_count == 0, "Face count should be 0"

    def test_index_photo_invalid_image_id(self):
        """Test error handling with invalid image ID."""
        # Invalid image ID
        result = index_photo_compreface("not-a-uuid", "test-api-key")

        # Verify error result
        assert result['status'] == 'failed'
        assert 'error' in result
        assert 'Invalid image_id format' in result['error']

    def test_index_photo_nonexistent_image(self, test_db):
        """Test error handling with nonexistent image."""
        # Valid UUID but doesn't exist
        fake_id = str(uuid.uuid4())
        result = index_photo_compreface(fake_id, "test-api-key", db_session=test_db)

        # Verify error result
        assert result['status'] == 'failed'
        assert 'error' in result
        assert 'Image not found' in result['error']


class TestQueueIntegration:
    """Tests for RQ queue integration."""

    def test_enqueue_face_indexing(self):
        """Test enqueueing a face indexing job."""
        # Create a fake image ID
        image_id = str(uuid.uuid4())

        # Enqueue job
        job_id = enqueue_face_indexing(image_id)

        # Verify job was created
        assert job_id is not None, "Job ID should be returned"
        assert isinstance(job_id, str), "Job ID should be a string"
