import pytest
from datetime import datetime, timedelta
import uuid
from app.models import User, Event, Image, Face, GuestSession, AuditLog, RateLimit
from sqlalchemy.exc import IntegrityError

class TestUserModel:
    """Test User model creation and relationships"""
    
    def test_create_user(self, db_session):
        """Test creating a user with all required fields"""
        user = User(
            email="test@example.com",
            password_hash="hashed_password"
        )
        db_session.add(user)
        db_session.commit()
        
        assert user.id is not None
        assert user.email == "test@example.com"
        assert user.password_hash == "hashed_password"
        assert user.created_at is not None
        assert user.updated_at is not None
    
    def test_user_email_unique_constraint(self, db_session):
        """Test that duplicate emails are rejected"""
        user1 = User(email="duplicate@example.com", password_hash="hash1")
        db_session.add(user1)
        db_session.commit()
        
        user2 = User(email="duplicate@example.com", password_hash="hash2")
        db_session.add(user2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
    
    def test_user_events_relationship(self, db_session):
        """Test User to Events relationship"""
        user = User(email="photographer@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(
            owner_user_id=user.id,
            slug="test-event",
            name="Test Event"
        )
        db_session.add(event)
        db_session.commit()
        
        assert len(user.events) == 1
        assert user.events[0].name == "Test Event"

class TestEventModel:
    """Test Event model creation and relationships"""
    
    def test_create_event(self, db_session):
        """Test creating an event with all fields"""
        user = User(email="owner@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(
            owner_user_id=user.id,
            slug="wedding-2024",
            name="Smith Wedding",
            allow_downloads=True,
            retention_days=90
        )
        db_session.add(event)
        db_session.commit()
        
        assert event.id is not None
        assert event.slug == "wedding-2024"
        assert event.name == "Smith Wedding"
        assert event.allow_downloads is True
        assert event.retention_days == 90
        assert event.owner_user_id == user.id
    
    def test_event_slug_unique_constraint(self, db_session):
        """Test that duplicate slugs are rejected"""
        user = User(email="owner2@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event1 = Event(owner_user_id=user.id, slug="duplicate-slug", name="Event 1")
        db_session.add(event1)
        db_session.commit()
        
        event2 = Event(owner_user_id=user.id, slug="duplicate-slug", name="Event 2")
        db_session.add(event2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
    
    def test_event_cascade_delete(self, db_session):
        """Test that deleting a user cascades to events"""
        user = User(email="cascade@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(owner_user_id=user.id, slug="cascade-event", name="Cascade Event")
        db_session.add(event)
        db_session.commit()
        
        event_id = event.id
        
        # Delete user
        db_session.delete(user)
        db_session.commit()
        
        # Verify event is also deleted
        deleted_event = db_session.query(Event).filter(Event.id == event_id).first()
        assert deleted_event is None

class TestImageModel:
    """Test Image model creation and relationships"""
    
    def test_create_image(self, db_session):
        """Test creating an image with all required fields"""
        user = User(email="img_owner@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(owner_user_id=user.id, slug="img-event", name="Image Event")
        db_session.add(event)
        db_session.commit()
        
        image = Image(
            event_id=event.id,
            filename="photo.jpg",
            file_hash="abc123hash",
            size_bytes=1024000,
            width=1920,
            height=1080,
            status="pending",
            face_count=0
        )
        db_session.add(image)
        db_session.commit()
        
        assert image.id is not None
        assert image.filename == "photo.jpg"
        assert image.status == "pending"
        assert image.face_count == 0
    
    def test_image_hash_unique_per_event(self, db_session):
        """Test that duplicate hashes within same event are rejected"""
        user = User(email="hash_owner@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(owner_user_id=user.id, slug="hash-event", name="Hash Event")
        db_session.add(event)
        db_session.commit()
        
        image1 = Image(
            event_id=event.id,
            filename="photo1.jpg",
            file_hash="samehash123",
            size_bytes=1024,
            status="pending"
        )
        db_session.add(image1)
        db_session.commit()
        
        image2 = Image(
            event_id=event.id,
            filename="photo2.jpg",
            file_hash="samehash123",
            size_bytes=1024,
            status="pending"
        )
        db_session.add(image2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
    
    def test_image_cascade_delete_from_event(self, db_session):
        """Test that deleting an event cascades to images"""
        user = User(email="img_cascade@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(owner_user_id=user.id, slug="img-cascade-event", name="Cascade")
        db_session.add(event)
        db_session.commit()
        
        image = Image(
            event_id=event.id,
            filename="cascade.jpg",
            file_hash="cascadehash",
            size_bytes=1024,
            status="pending"
        )
        db_session.add(image)
        db_session.commit()
        
        image_id = image.id
        
        # Delete event
        db_session.delete(event)
        db_session.commit()
        
        # Verify image is also deleted
        deleted_image = db_session.query(Image).filter(Image.id == image_id).first()
        assert deleted_image is None

class TestFaceModel:
    """Test Face model creation and relationships"""
    
    def test_create_face(self, db_session):
        """Test creating a face with embedding"""
        user = User(email="face_owner@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(owner_user_id=user.id, slug="face-event", name="Face Event")
        db_session.add(event)
        db_session.commit()
        
        image = Image(
            event_id=event.id,
            filename="face.jpg",
            file_hash="facehash",
            size_bytes=1024,
            status="indexed"
        )
        db_session.add(image)
        db_session.commit()
        
        # Create a 512-dim embedding (simplified for test)
        embedding = [0.1] * 512
        
        face = Face(
            image_id=image.id,
            event_id=event.id,
            embedding=embedding,
            bbox=[100.0, 150.0, 200.0, 250.0],
            quality_score=0.95
        )
        db_session.add(face)
        db_session.commit()
        
        assert face.id is not None
        assert face.quality_score == 0.95
        assert len(face.bbox) == 4
    
    def test_face_cascade_delete_from_image(self, db_session):
        """Test that deleting an image cascades to faces"""
        user = User(email="face_cascade@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(owner_user_id=user.id, slug="face-cascade", name="Face Cascade")
        db_session.add(event)
        db_session.commit()
        
        image = Image(
            event_id=event.id,
            filename="cascade_face.jpg",
            file_hash="cascadefacehash",
            size_bytes=1024,
            status="indexed"
        )
        db_session.add(image)
        db_session.commit()
        
        face = Face(
            image_id=image.id,
            event_id=event.id,
            embedding=[0.1] * 512,
            bbox=[10.0, 20.0, 30.0, 40.0],
            quality_score=0.8
        )
        db_session.add(face)
        db_session.commit()
        
        face_id = face.id
        
        # Delete image
        db_session.delete(image)
        db_session.commit()
        
        # Verify face is also deleted
        deleted_face = db_session.query(Face).filter(Face.id == face_id).first()
        assert deleted_face is None

class TestGuestSessionModel:
    """Test GuestSession model"""
    
    def test_create_guest_session(self, db_session):
        """Test creating a guest session"""
        user = User(email="session_owner@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(owner_user_id=user.id, slug="session-event", name="Session Event")
        db_session.add(event)
        db_session.commit()
        
        session = GuestSession(
            event_id=event.id,
            session_token="unique_token_123",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db_session.add(session)
        db_session.commit()
        
        assert session.id is not None
        assert session.session_token == "unique_token_123"
        assert session.expires_at > datetime.utcnow()

class TestAuditLogModel:
    """Test AuditLog model"""
    
    def test_create_audit_log(self, db_session):
        """Test creating an audit log entry"""
        user = User(email="audit_owner@example.com", password_hash="hash")
        db_session.add(user)
        db_session.commit()
        
        event = Event(owner_user_id=user.id, slug="audit-event", name="Audit Event")
        db_session.add(event)
        db_session.commit()
        
        log = AuditLog(
            event_id=event.id,
            actor_type="admin",
            actor_id=user.id,
            action="upload",
            metadata_={"photo_count": 10}
        )
        db_session.add(log)
        db_session.commit()
        
        assert log.id is not None
        assert log.actor_type == "admin"
        assert log.action == "upload"
        assert log.metadata_["photo_count"] == 10

class TestRateLimitModel:
    """Test RateLimit model"""
    
    def test_create_rate_limit(self, db_session):
        """Test creating a rate limit entry"""
        session_id = uuid.uuid4()
        
        rate_limit = RateLimit(
            session_id=session_id,
            action="scan",
            count=1,
            window_start=datetime.utcnow()
        )
        db_session.add(rate_limit)
        db_session.commit()
        
        assert rate_limit.id is not None
        assert rate_limit.action == "scan"
        assert rate_limit.count == 1
