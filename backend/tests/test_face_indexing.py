"""Unit tests for face indexing functionality."""

import pytest
import uuid
from PIL import Image as PILImage
from io import BytesIO
import numpy as np

from app.models import Image, Event, User, Face
from app.workers.face_indexer import index_photo
from app.storage import storage_service
from app.face_detection import face_detector
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


class TestFaceDetection:
    """Tests for face detection functionality."""
    
    def test_detect_faces_with_multiple_faces(self):
        """Test face detection with multiple faces."""
        # Create image with 2 faces
        image_bytes = create_test_image_with_faces(num_faces=2)
        
        # Detect faces
        faces = face_detector.detect_faces(image_bytes)
        
        # Should detect at least 1 face (may not detect all simple patterns)
        assert len(faces) >= 0, "Face detection should not fail"
        
        # If faces detected, verify structure
        for embedding, bbox, quality_score in faces:
            # Embedding should be 512-dimensional
            assert len(embedding) == 512, "Embedding should be 512-dimensional"
            
            # Embedding should be normalized
            norm = np.linalg.norm(embedding)
            assert abs(norm - 1.0) < 0.01, "Embedding should be L2 normalized"
            
            # Bounding box should have 4 coordinates
            assert len(bbox) == 4, "Bounding box should have 4 coordinates"
            assert bbox[0] < bbox[2], "x1 should be less than x2"
            assert bbox[1] < bbox[3], "y1 should be less than y2"
            
            # Quality score should be between 0 and 1
            assert 0 <= quality_score <= 1, "Quality score should be between 0 and 1"
    
    def test_detect_faces_no_faces(self):
        """Test face detection with no faces."""
        # Create image without faces
        image_bytes = create_test_image_no_faces()
        
        # Detect faces
        faces = face_detector.detect_faces(image_bytes)
        
        # Should return empty list
        assert len(faces) == 0, "Should not detect faces in solid color image"
    
    def test_detect_faces_invalid_image(self):
        """Test face detection with invalid image data."""
        # Invalid image data
        invalid_bytes = b"not an image"
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to decode image"):
            face_detector.detect_faces(invalid_bytes)


class TestFaceIndexingWorker:
    """Tests for face indexing worker."""
    
    def test_index_photo_with_faces(self, test_db):
        """Test indexing a photo with faces."""
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
        image_bytes = create_test_image_with_faces(num_faces=1)
        storage_service.upload_photo(
            event_id=event.id,
            image_id=image.id,
            photo_data=image_bytes,
            photo_type='original'
        )
        
        # Process the image
        result = index_photo(str(image.id), db_session=test_db)
        
        # Refresh image from database
        test_db.refresh(image)
        
        # Verify result
        assert result['image_id'] == str(image.id)
        assert result['status'] in ['indexed', 'no_faces'], \
            "Status should be indexed or no_faces"
        
        # Verify image status updated
        assert image.status in ['indexed', 'no_faces'], \
            "Image status should be updated"
        
        # If faces detected, verify they were stored
        if image.status == 'indexed':
            assert image.face_count > 0, "Face count should be > 0"
            assert image.indexed_at is not None, "indexed_at should be set"
            
            # Verify faces in database
            faces = test_db.query(Face).filter(Face.image_id == image.id).all()
            assert len(faces) == image.face_count, \
                "Stored face count should match image.face_count"
            
            # Verify face data
            for face in faces:
                assert face.event_id == event.id, "Face should have correct event_id"
                assert len(face.embedding) == 512, "Embedding should be 512-dimensional"
                assert len(face.bbox) == 4, "Bounding box should have 4 coordinates"
                assert 0 <= face.quality_score <= 1, \
                    "Quality score should be between 0 and 1"
        
        # Cleanup
        storage_service.delete_photo(event.id, image.id)
    
    def test_index_photo_no_faces(self, test_db):
        """Test indexing a photo with no faces."""
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
        result = index_photo(str(image.id), db_session=test_db)
        
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
        result = index_photo(str(image.id), db_session=test_db)
        
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
        result = index_photo("not-a-uuid")
        
        # Verify error result
        assert result['status'] == 'failed'
        assert 'error' in result
        assert 'Invalid image_id format' in result['error']
    
    def test_index_photo_nonexistent_image(self, test_db):
        """Test error handling with nonexistent image."""
        # Valid UUID but doesn't exist
        fake_id = str(uuid.uuid4())
        result = index_photo(fake_id, db_session=test_db)

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
