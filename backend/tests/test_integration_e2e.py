"""
Integration tests for end-to-end flows in PicUr
Tests complete workflows: Admin upload flow, Guest scan flow, and background processing
"""

import pytest
import io
import base64
import time
from PIL import Image as PILImage
import numpy as np
from unittest.mock import patch, MagicMock
from app.models import User, Event, Image, Face
from app.auth import create_access_token, hash_password


@pytest.mark.integration
class TestAdminUploadFlow:
    """
    Test complete Admin upload flow:
    Register → Login → Create Event → Upload Photos → Check Status
    Validates: Requirements 1.1, 2.1, 3.1
    """
    
    def test_complete_admin_upload_flow(self, client, db_session):
        """Test the complete admin workflow from registration to photo upload"""
        
        # Step 1: Register Admin
        register_data = {
            "email": "photographer@example.com",
            "password": "SecurePassword123!"
        }
        response = client.post("/auth/register", json=register_data)
        assert response.status_code == 201
        user_data = response.json()
        assert user_data["email"] == register_data["email"]
        user_id = user_data["user_id"]
        
        # Step 2: Login Admin
        login_data = {
            "email": "photographer@example.com",
            "password": "SecurePassword123!"
        }
        response = client.post("/auth/login", json=login_data)
        assert response.status_code == 200
        token_data = response.json()
        assert "access_token" in token_data
        access_token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Step 3: Create Event
        event_data = {
            "name": "Smith Wedding",
            "date": "2024-06-15",
            "passcode": "wedding2024",
            "allow_downloads": True,
            "retention_days": 90
        }
        response = client.post("/events", json=event_data, headers=headers)
        assert response.status_code == 201
        event = response.json()
        assert event["name"] == "Smith Wedding"
        assert event["owner_user_id"] == user_id
        event_id = event["event_id"]
        slug = event["slug"]
        
        # Step 4: Upload Photos
        # Create test image
        img = PILImage.new('RGB', (800, 600), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        files = {
            'files': ('test_photo.jpg', img_bytes, 'image/jpeg')
        }
        
        # Mock MinIO and face detection for this test
        with patch('app.routers.events.storage_service') as mock_storage, \
             patch('app.routers.events.enqueue_face_indexing') as mock_queue:

            mock_storage.upload_photo.return_value = True

            response = client.post(
                f"/events/{event_id}/photos",
                files=files,
                headers=headers
            )
            assert response.status_code == 201
            upload_result = response.json()
            assert len(upload_result["uploaded"]) == 1
            assert upload_result["uploaded"][0]["status"] == "pending"
            image_id = upload_result["uploaded"][0]["image_id"]
        
        # Step 5: Check Event Status
        response = client.get(f"/events/{event_id}", headers=headers)
        assert response.status_code == 200
        event_status = response.json()
        assert event_status["status"]["total_photos"] == 1
        assert event_status["status"]["pending"] >= 1
        
        # Step 6: List Photos
        response = client.get(f"/events/{event_id}/photos", headers=headers)
        assert response.status_code == 200
        photos = response.json()
        assert photos["total"] == 1
        assert len(photos["photos"]) == 1
        
        # Step 7: Verify Event in List
        response = client.get("/events", headers=headers)
        assert response.status_code == 200
        events = response.json()
        assert len(events["events"]) == 1
        assert events["events"][0]["event_id"] == event_id


@pytest.mark.integration
class TestGuestScanFlow:
    """
    Test complete Guest scan flow:
    Access Event → Enter Passcode → Scan Face → View Matches → Download
    Validates: Requirements 5.1, 6.1
    """
    
    def test_complete_guest_scan_flow(self, client, db_session):
        """Test the complete guest workflow from event access to photo download"""
        
        # Setup: Create Admin, Event, and Photos with faces
        admin = User(
            email="admin@example.com",
            password_hash=hash_password("password123")
        )
        db_session.add(admin)
        db_session.commit()
        
        event = Event(
            owner_user_id=admin.id,
            slug="test-wedding-abc",
            name="Test Wedding",
            date="2024-06-15",
            passcode_hash=hash_password("wedding123"),
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        
        # Create test image with face
        image = Image(
            event_id=event.id,
            filename="photo1.jpg",
            file_hash="abc123",
            size_bytes=1024000,
            width=1920,
            height=1080,
            status="indexed",
            face_count=1
        )
        db_session.add(image)
        db_session.commit()
        
        # Create face embedding
        face_embedding = np.random.rand(512).tolist()
        face = Face(
            image_id=image.id,
            event_id=event.id,
            embedding=face_embedding,
            bbox=[100, 100, 200, 200],
            quality_score=0.95
        )
        db_session.add(face)
        db_session.commit()
        
        # Step 1: Access Event by Slug
        response = client.get(f"/e/{event.slug}")
        assert response.status_code == 200
        event_info = response.json()
        assert event_info["name"] == "Test Wedding"
        assert event_info["requires_passcode"] is True
        
        # Step 2: Authenticate with Passcode
        auth_data = {"passcode": "wedding123"}
        response = client.post(f"/e/{event.slug}/auth", json=auth_data)
        assert response.status_code == 200
        auth_result = response.json()
        assert "event_token" in auth_result
        event_token = auth_result["event_token"]
        guest_headers = {"Authorization": f"Bearer {event_token}"}
        
        # Step 3: Scan Face
        # Create test face image
        face_img = PILImage.new('RGB', (200, 200), color='blue')
        face_bytes = io.BytesIO()
        face_img.save(face_bytes, format='JPEG')
        face_bytes.seek(0)
        face_base64 = base64.b64encode(face_bytes.getvalue()).decode('utf-8')
        
        scan_data = {"image": face_base64}
        
        # Mock face detection, MinIO, and rate limiter
        with patch('app.routers.guest.face_detector') as mock_detector, \
             patch('app.routers.guest.storage_service') as mock_storage, \
             patch('app.routers.guest.rate_limiter') as mock_rate_limiter:

            # Mock face detection to return tuple format: (embedding_array, bbox, quality_score)
            mock_detector.detect_faces.return_value = [
                (np.array(face_embedding), [100, 100, 200, 200], 0.95)
            ]

            mock_storage.generate_presigned_url.return_value = "https://presigned-url.com/photo"
            mock_rate_limiter.enforce_rate_limit.return_value = None

            response = client.post("/scan", json=scan_data, headers=guest_headers)
            assert response.status_code == 200
            matches = response.json()
            assert "matches" in matches
            assert len(matches["matches"]) > 0

            # Verify match details
            match = matches["matches"][0]
            assert "image_id" in match
            assert "similarity" in match
            assert "thumbnail_url" in match
            assert "original_url" in match
            assert "download_url" in match  # Should be present since allow_downloads=True
            assert match["similarity"] > 0.6  # Above threshold
    
    def test_guest_scan_without_passcode(self, client, db_session):
        """Test guest flow for event without passcode"""
        
        # Setup: Create event without passcode
        admin = User(
            email="admin2@example.com",
            password_hash=hash_password("password123")
        )
        db_session.add(admin)
        db_session.commit()
        
        event = Event(
            owner_user_id=admin.id,
            slug="public-event-xyz",
            name="Public Event",
            date="2024-07-01",
            passcode_hash=None,  # No passcode
            allow_downloads=False,
            retention_days=30
        )
        db_session.add(event)
        db_session.commit()
        
        # Step 1: Access Event
        response = client.get(f"/e/{event.slug}")
        assert response.status_code == 200
        event_info = response.json()
        assert event_info["requires_passcode"] is False
        
        # Step 2: Authenticate without passcode
        response = client.post(f"/e/{event.slug}/auth", json={})
        assert response.status_code == 200
        auth_result = response.json()
        assert "event_token" in auth_result


@pytest.mark.integration
class TestBackgroundProcessingFlow:
    """
    Test background processing flow:
    Upload Photo → Queue Job → Process Face → Update Status
    Validates: Requirements 4.1
    """
    
    def test_face_indexing_workflow(self, client, db_session):
        """Test the complete background processing workflow"""
        
        # Setup: Create Admin and Event
        admin = User(
            email="admin@example.com",
            password_hash=hash_password("password123")
        )
        db_session.add(admin)
        db_session.commit()
        
        token = create_access_token({"sub": str(admin.id), "email": admin.email})
        headers = {"Authorization": f"Bearer {token}"}
        
        event = Event(
            owner_user_id=admin.id,
            slug="test-event-123",
            name="Test Event",
            date="2024-06-01",
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        
        # Step 1: Upload Photo
        img = PILImage.new('RGB', (800, 600), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        files = {'files': ('test.jpg', img_bytes, 'image/jpeg')}

        with patch('app.routers.events.storage_service') as mock_storage, \
             patch('app.routers.events.enqueue_face_indexing') as mock_queue:

            mock_storage.upload_photo.return_value = True

            response = client.post(
                f"/events/{event.id}/photos",
                files=files,
                headers=headers
            )
            assert response.status_code == 201
            upload_result = response.json()
            image_id = upload_result["uploaded"][0]["image_id"]
            
            # Verify job was queued
            mock_queue.assert_called_once()
        
        # Step 2: Simulate Face Indexing
        # Get the image from database
        image = db_session.query(Image).filter(Image.id == image_id).first()
        assert image is not None
        assert image.status == "pending"
        
        # Simulate worker processing
        with patch('app.workers.face_indexer.storage_service') as mock_storage, \
             patch('app.workers.face_indexer.face_detector') as mock_detector:

            # Mock storage to return image bytes
            mock_storage.get_photo.return_value = img_bytes.getvalue()

            # Mock face detection result as tuple format
            embedding = np.random.rand(512)
            mock_detector.detect_faces.return_value = [
                (embedding, [100, 100, 200, 200], 0.95)
            ]

            # Import and run the indexing function
            from app.workers.face_indexer import index_photo

            # Run the job with db_session
            index_photo(str(image_id), db_session=db_session)
        
        # Step 3: Verify Status Update
        db_session.refresh(image)
        assert image.status == "indexed"
        assert image.face_count == 1
        
        # Verify face was stored
        faces = db_session.query(Face).filter(Face.image_id == image.id).all()
        assert len(faces) == 1
        assert faces[0].event_id == event.id
        
        # Step 4: Check Event Status
        response = client.get(f"/events/{event.id}", headers=headers)
        assert response.status_code == 200
        event_status = response.json()
        assert event_status["status"]["indexed"] == 1
        assert event_status["status"]["total_faces"] == 1
    
    def test_reindex_workflow(self, client, db_session):
        """Test the reindex workflow"""
        
        # Setup: Create Admin, Event, and indexed photos
        admin = User(
            email="admin@example.com",
            password_hash=hash_password("password123")
        )
        db_session.add(admin)
        db_session.commit()
        
        token = create_access_token({"sub": str(admin.id), "email": admin.email})
        headers = {"Authorization": f"Bearer {token}"}
        
        event = Event(
            owner_user_id=admin.id,
            slug="reindex-test",
            name="Reindex Test",
            date="2024-06-01",
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        
        # Create indexed images
        for i in range(3):
            image = Image(
                event_id=event.id,
                filename=f"photo{i}.jpg",
                file_hash=f"hash{i}",
                size_bytes=1024000,
                width=1920,
                height=1080,
                status="indexed",
                face_count=1
            )
            db_session.add(image)
        db_session.commit()
        
        # Step 1: Trigger Reindex
        with patch('app.routers.events.enqueue_face_indexing') as mock_queue:
            response = client.post(f"/events/{event.id}/reindex", headers=headers)
            assert response.status_code == 200
            result = response.json()
            assert result["queued_count"] == 3
            
            # Verify all images were queued
            assert mock_queue.call_count == 3
        
        # Step 2: Verify Status Reset
        images = db_session.query(Image).filter(Image.event_id == event.id).all()
        for image in images:
            assert image.status == "pending"


@pytest.mark.integration
class TestCrossFlowIntegration:
    """
    Test integration between different flows
    """
    
    def test_multi_admin_isolation(self, client, db_session):
        """Test that multiple admins remain isolated"""
        
        # Create two admins
        admin1 = User(email="admin1@example.com", password_hash=hash_password("pass1"))
        admin2 = User(email="admin2@example.com", password_hash=hash_password("pass2"))
        db_session.add_all([admin1, admin2])
        db_session.commit()
        
        token1 = create_access_token({"sub": str(admin1.id), "email": admin1.email})
        token2 = create_access_token({"sub": str(admin2.id), "email": admin2.email})
        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}
        
        # Admin 1 creates event
        event_data = {"name": "Admin 1 Event", "date": "2024-06-01"}
        response = client.post("/events", json=event_data, headers=headers1)
        assert response.status_code == 201
        event1_id = response.json()["event_id"]

        # Admin 2 creates event
        event_data = {"name": "Admin 2 Event", "date": "2024-07-01"}
        response = client.post("/events", json=event_data, headers=headers2)
        assert response.status_code == 201
        event2_id = response.json()["event_id"]
        
        # Admin 1 lists events - should only see their event
        response = client.get("/events", headers=headers1)
        assert response.status_code == 200
        events = response.json()["events"]
        assert len(events) == 1
        assert events[0]["event_id"] == event1_id
        
        # Admin 2 lists events - should only see their event
        response = client.get("/events", headers=headers2)
        assert response.status_code == 200
        events = response.json()["events"]
        assert len(events) == 1
        assert events[0]["event_id"] == event2_id
        
        # Admin 2 tries to access Admin 1's event - should fail
        response = client.get(f"/events/{event1_id}", headers=headers2)
        assert response.status_code == 403
    
    def test_guest_event_isolation(self, client, db_session):
        """Test that guests can only access their event's photos"""
        
        # Setup: Create two events with photos
        admin = User(email="admin@example.com", password_hash=hash_password("pass"))
        db_session.add(admin)
        db_session.commit()
        
        event1 = Event(
            owner_user_id=admin.id,
            slug="event1",
            name="Event 1",
            date="2024-06-01",
            allow_downloads=True
        )
        event2 = Event(
            owner_user_id=admin.id,
            slug="event2",
            name="Event 2",
            date="2024-07-01",
            allow_downloads=True
        )
        db_session.add_all([event1, event2])
        db_session.commit()
        
        # Add images and faces to both events
        for event in [event1, event2]:
            image = Image(
                event_id=event.id,
                filename="photo.jpg",
                file_hash=f"hash_{event.id}",
                size_bytes=1024000,
                status="indexed",
                face_count=1
            )
            db_session.add(image)
            db_session.commit()
            
            face = Face(
                image_id=image.id,
                event_id=event.id,
                embedding=np.random.rand(512).tolist(),
                bbox=[100, 100, 200, 200],
                quality_score=0.95
            )
            db_session.add(face)
        db_session.commit()
        
        # Guest authenticates to event1
        response = client.post(f"/e/{event1.slug}/auth", json={})
        assert response.status_code == 200
        token1 = response.json()["event_token"]
        headers1 = {"Authorization": f"Bearer {token1}"}
        
        # Guest scans face - should only get matches from event1
        face_img = PILImage.new('RGB', (200, 200), color='blue')
        face_bytes = io.BytesIO()
        face_img.save(face_bytes, format='JPEG')
        face_base64 = base64.b64encode(face_bytes.getvalue()).decode('utf-8')
        
        with patch('app.routers.guest.face_detector') as mock_detector, \
             patch('app.routers.guest.storage_service') as mock_storage, \
             patch('app.routers.guest.rate_limiter') as mock_rate_limiter:

            # Mock face detection to return tuple format
            mock_detector.detect_faces.return_value = [
                (np.random.rand(512), [100, 100, 200, 200], 0.95)
            ]
            mock_storage.generate_presigned_url.return_value = "https://url.com/photo"
            mock_rate_limiter.enforce_rate_limit.return_value = None

            response = client.post("/scan", json={"image": face_base64}, headers=headers1)
            assert response.status_code == 200
            matches = response.json()["matches"]

            # Verify all matches are from event1
            for match in matches:
                image = db_session.query(Image).filter(Image.id == match["image_id"]).first()
                assert image.event_id == event1.id
