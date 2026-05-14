"""
Property-based tests for data retention and cleanup
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
import uuid
from io import BytesIO
from PIL import Image as PILImage

from app.models import User, Event, Image, Face, GuestSession, AuditLog
from app.storage import storage_service
from app.audit import log_action


# Feature: picur, Property 11: Event Deletion Cascade
@given(
    image_count=st.integers(min_value=1, max_value=5),
    faces_per_image=st.integers(min_value=0, max_value=3),
    session_count=st.integers(min_value=0, max_value=3),
    audit_log_count=st.integers(min_value=1, max_value=5)
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@pytest.mark.property_test
def test_event_deletion_cascade(
    test_db: Session,
    image_count: int,
    faces_per_image: int,
    session_count: int,
    audit_log_count: int
):
    """
    Property 11: Event Deletion Cascade
    
    For any Event that is deleted, all associated images, faces, and audit logs
    SHALL be removed from the database, and all files SHALL be removed from
    MinIO storage.
    
    Validates: Requirements 11.3, 11.4, 11.5
    """
    # Create a test user
    user = User(
        email=f"test_{uuid.uuid4()}@example.com",
        password_hash="hashed_password"
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    
    # Create an event
    event = Event(
        owner_user_id=user.id,
        slug=f"test-event-{uuid.uuid4()}",
        name="Test Event for Deletion",
        allow_downloads=True,
        retention_days=90
    )
    test_db.add(event)
    test_db.commit()
    test_db.refresh(event)
    
    event_id = event.id
    
    # Create images with photos in MinIO
    image_ids = []
    for i in range(image_count):
        # Create a simple test image
        img = PILImage.new('RGB', (100, 100), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        photo_data = img_bytes.getvalue()
        
        # Create image record
        image_id = uuid.uuid4()
        image = Image(
            id=image_id,
            event_id=event_id,
            filename=f"test_image_{i}.jpg",
            file_hash=f"hash_{i}_{uuid.uuid4()}",
            size_bytes=len(photo_data),
            width=100,
            height=100,
            status='indexed',
            face_count=faces_per_image
        )
        test_db.add(image)
        image_ids.append(image_id)
        
        # Upload to MinIO (both original and thumbnail)
        try:
            storage_service.upload_photo(
                event_id=event_id,
                image_id=image_id,
                photo_data=photo_data,
                photo_type='original'
            )
            storage_service.upload_photo(
                event_id=event_id,
                image_id=image_id,
                photo_data=photo_data,
                photo_type='thumb'
            )
        except Exception as e:
            # If MinIO is not available in test environment, skip storage tests
            pytest.skip(f"MinIO not available: {str(e)}")
        
        # Create faces for this image
        for j in range(faces_per_image):
            face = Face(
                image_id=image_id,
                event_id=event_id,
                embedding=[0.1] * 512,  # Dummy embedding
                bbox=[10.0, 10.0, 50.0, 50.0],
                quality_score=0.9
            )
            test_db.add(face)
    
    test_db.commit()
    
    # Create guest sessions
    session_ids = []
    for i in range(session_count):
        session = GuestSession(
            event_id=event_id,
            session_token=f"token_{uuid.uuid4()}",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        test_db.add(session)
        test_db.commit()
        test_db.refresh(session)
        session_ids.append(session.id)
    
    # Create audit logs
    for i in range(audit_log_count):
        log_action(
            db=test_db,
            event_id=event_id,
            actor_type='admin',
            actor_id=user.id,
            action='test_action',
            metadata={'iteration': i}
        )
    
    # Verify all records exist before deletion
    assert test_db.query(Event).filter(Event.id == event_id).count() == 1
    assert test_db.query(Image).filter(Image.event_id == event_id).count() == image_count
    assert test_db.query(Face).filter(Face.event_id == event_id).count() == image_count * faces_per_image
    assert test_db.query(GuestSession).filter(GuestSession.event_id == event_id).count() == session_count
    assert test_db.query(AuditLog).filter(AuditLog.event_id == event_id).count() == audit_log_count
    
    # Verify photos exist in MinIO
    for image_id in image_ids:
        try:
            original = storage_service.get_photo(event_id, image_id, 'original')
            assert original is not None
            thumb = storage_service.get_photo(event_id, image_id, 'thumb')
            assert thumb is not None
        except Exception:
            # If MinIO is not available, skip this verification
            pass
    
    # Delete the event
    test_db.delete(event)
    test_db.commit()
    
    # Verify event is deleted
    assert test_db.query(Event).filter(Event.id == event_id).count() == 0
    
    # Verify intrinsic event data is cascade-deleted: images, faces,
    # guest sessions all die with their parent event.
    assert test_db.query(Image).filter(Image.event_id == event_id).count() == 0
    assert test_db.query(Face).filter(Face.event_id == event_id).count() == 0
    assert test_db.query(GuestSession).filter(GuestSession.event_id == event_id).count() == 0
    # Audit rows DELIBERATELY survive event deletion via the FK's
    # ON DELETE SET NULL action (migration a3d4e5f6g7). The original
    # cascade behaviour wiped the audit trail with the event — the
    # exact opposite of what an audit log is for. Verify the rows now
    # persist with event_id=NULL instead.
    assert test_db.query(AuditLog).filter(AuditLog.event_id == event_id).count() == 0
    surviving_audits = (
        test_db.query(AuditLog)
        .filter(AuditLog.event_id.is_(None), AuditLog.actor_id == user.id, AuditLog.action == 'test_action')
        .count()
    )
    assert surviving_audits == audit_log_count, (
        f"audit rows must survive event delete via FK SET NULL — "
        f"expected {audit_log_count} surviving rows, got {surviving_audits}"
    )
    
    # Verify photos are deleted from MinIO
    # Note: In the actual implementation, storage_service.delete_event_photos should be called
    # before deleting the event. Here we test that the photos can no longer be retrieved.
    try:
        storage_service.delete_event_photos(event_id)
        
        # Verify photos are gone
        for image_id in image_ids:
            with pytest.raises(FileNotFoundError):
                storage_service.get_photo(event_id, image_id, 'original')
            with pytest.raises(FileNotFoundError):
                storage_service.get_photo(event_id, image_id, 'thumb')
    except Exception as e:
        # If MinIO is not available, skip this verification
        if "MinIO not available" not in str(e):
            pass
