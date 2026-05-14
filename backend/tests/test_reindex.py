"""Unit tests for reindex endpoint."""

import pytest
import uuid
from fastapi.testclient import TestClient

from app.models import Image, Event, User, Face
from app.auth import hash_password, create_access_token


class TestReindexEndpoint:
    """Tests for the reindex endpoint."""
    
    def test_reindex_event_success(self, client, test_db):
        """Test successful event reindexing."""
        # Create test user
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        test_db.add(user)
        test_db.commit()
        
        # Create JWT token
        token = create_access_token({"sub": str(user.id), "email": user.email})
        
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
        
        # Create test images with various statuses
        images = []
        for status in ['indexed', 'no_faces', 'failed']:
            image = Image(
                event_id=event.id,
                filename=f"test_{status}.jpg",
                file_hash=f"hash_{uuid.uuid4()}",
                size_bytes=1024,
                width=200,
                height=200,
                status=status,
                face_count=1 if status == 'indexed' else 0
            )
            test_db.add(image)
            images.append(image)
        
        test_db.commit()
        
        # Create some face records for indexed images
        for image in images:
            if image.status == 'indexed':
                face = Face(
                    image_id=image.id,
                    event_id=event.id,
                    embedding=[0.1] * 512,
                    bbox=[10.0, 20.0, 30.0, 40.0],
                    quality_score=0.95
                )
                test_db.add(face)
        
        test_db.commit()
        
        # Call reindex endpoint. The endpoint now enqueues an async
        # task instead of doing the work inline; manually run the task
        # body so the assertions below can verify the end-state.
        from unittest.mock import patch
        from app.workers.reindex_event import reindex_event_task

        with patch("app.queue.enqueue_event_reindex") as fake_enqueue:
            fake_enqueue.return_value = "fake-reindex-job-id"
            response = client.post(
                f"/events/{event.id}/reindex",
                headers={"Authorization": f"Bearer {token}"}
            )

        # Endpoint replied as soon as the task was enqueued.
        assert response.status_code == 200
        data = response.json()
        assert "Reindex" in data['message']
        assert data['queued_count'] == 3, "Should report 3 images at request time"
        fake_enqueue.assert_called_once_with(str(event.id), str(user.id))

        # Simulate the worker running. It uses its own SessionLocal in
        # prod; pass the test session so the rollback fixture stays
        # consistent.
        reindex_event_task(str(event.id), str(user.id), db=test_db)

        # Verify all images reset to pending
        test_db.refresh(images[0])
        test_db.refresh(images[1])
        test_db.refresh(images[2])

        for image in images:
            assert image.status == 'pending', "All images should be reset to pending"
            assert image.face_count == 0, "Face count should be reset to 0"
            assert image.indexed_at is None, "indexed_at should be reset to None"

        # Verify all face records deleted
        face_count = test_db.query(Face).filter(Face.event_id == event.id).count()
        assert face_count == 0, "All face records should be deleted"
    
    def test_reindex_event_not_found(self, client, test_db):
        """Test reindex with nonexistent event."""
        # Create test user
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        test_db.add(user)
        test_db.commit()
        
        # Create JWT token
        token = create_access_token({"sub": str(user.id), "email": user.email})
        
        # Try to reindex nonexistent event
        fake_event_id = str(uuid.uuid4())
        response = client.post(
            f"/events/{fake_event_id}/reindex",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Verify error response
        assert response.status_code == 404
        assert "Event not found" in response.json()['detail']
    
    def test_reindex_event_unauthorized(self, client, test_db):
        """Test reindex without ownership."""
        # Create two users
        user1 = User(
            email=f"test1_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        user2 = User(
            email=f"test2_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        test_db.add(user1)
        test_db.add(user2)
        test_db.commit()
        
        # Create JWT token for user2
        token = create_access_token({"sub": str(user2.id), "email": user2.email})
        
        # Create event owned by user1
        event = Event(
            owner_user_id=user1.id,
            slug=f"test-event-{uuid.uuid4()}",
            name="Test Event",
            allow_downloads=True,
            retention_days=90
        )
        test_db.add(event)
        test_db.commit()
        
        # Try to reindex as user2
        response = client.post(
            f"/events/{event.id}/reindex",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Verify error response
        assert response.status_code == 403
        assert "permission" in response.json()['detail'].lower()
    
    def test_reindex_event_no_auth(self, client):
        """Test reindex without authentication."""
        fake_event_id = str(uuid.uuid4())
        response = client.post(f"/events/{fake_event_id}/reindex")
        
        # Verify error response (403 because HTTPBearer returns 403 for missing credentials)
        assert response.status_code == 403
    
    def test_reindex_event_invalid_id(self, client, test_db):
        """Test reindex with invalid event ID format."""
        # Create test user
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            password_hash=hash_password("password")
        )
        test_db.add(user)
        test_db.commit()
        
        # Create JWT token
        token = create_access_token({"sub": str(user.id), "email": user.email})
        
        # Try to reindex with invalid ID
        response = client.post(
            "/events/not-a-uuid/reindex",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Verify error response
        assert response.status_code == 400
        assert "Invalid event ID format" in response.json()['detail']
