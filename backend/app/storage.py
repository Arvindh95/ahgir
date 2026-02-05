"""MinIO storage service for photo management."""

from minio import Minio
from minio.error import S3Error
from io import BytesIO
from typing import Optional
import uuid
from datetime import timedelta
from sqlalchemy.orm import Session

from app.config import settings
from app.retry_utils import exponential_backoff
from app.exceptions import StorageError


class StorageService:
    """MinIO client wrapper for photo storage operations."""
    
    _instance = None
    _client = None
    
    def __init__(self):
        """Initialize MinIO client with credentials."""
        # Don't initialize client immediately to allow for testing
        pass
    
    @property
    def client(self):
        """Lazy initialization of MinIO client."""
        if self._client is None:
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            self._ensure_bucket_exists()
        return self._client
    
    @property
    def bucket(self):
        """Get bucket name from settings."""
        return settings.minio_bucket
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as e:
            raise StorageError(f"Failed to create bucket: {str(e)}")
    
    @exponential_backoff(max_retries=3, base_delay=1.0, exceptions=(S3Error, StorageError))
    def upload_photo(
        self,
        event_id: uuid.UUID,
        image_id: uuid.UUID,
        photo_data: bytes,
        photo_type: str = "original"
    ) -> str:
        """
        Upload a photo to MinIO with retry logic.
        
        Args:
            event_id: UUID of the event
            image_id: UUID of the image
            photo_data: Image bytes
            photo_type: Type of photo ('original' or 'thumb')
        
        Returns:
            Object path in MinIO
        
        Raises:
            StorageError: If upload fails after retries
        """
        object_path = f"events/{event_id}/{photo_type}/{image_id}.jpg"
        
        try:
            self.client.put_object(
                self.bucket,
                object_path,
                BytesIO(photo_data),
                length=len(photo_data),
                content_type="image/jpeg"
            )
            return object_path
        except S3Error as e:
            raise StorageError(f"Failed to upload photo: {str(e)}")
    
    @exponential_backoff(max_retries=3, base_delay=1.0, exceptions=(S3Error, StorageError))
    def get_photo(
        self,
        event_id: uuid.UUID,
        image_id: uuid.UUID,
        photo_type: str = "original"
    ) -> bytes:
        """
        Retrieve a photo from MinIO with retry logic.
        
        Args:
            event_id: UUID of the event
            image_id: UUID of the image
            photo_type: Type of photo ('original' or 'thumb')
        
        Returns:
            Image bytes
        
        Raises:
            FileNotFoundError: If photo not found
            StorageError: If retrieval fails after retries
        """
        object_path = f"events/{event_id}/{photo_type}/{image_id}.jpg"
        
        try:
            response = self.client.get_object(self.bucket, object_path)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileNotFoundError(f"Photo not found: {object_path}")
            raise StorageError(f"Failed to retrieve photo: {str(e)}")
    
    @exponential_backoff(max_retries=3, base_delay=1.0, exceptions=(S3Error,))
    def delete_photo(
        self,
        event_id: uuid.UUID,
        image_id: uuid.UUID,
        photo_type: Optional[str] = None
    ):
        """
        Delete a photo from MinIO with retry logic.
        
        Args:
            event_id: UUID of the event
            image_id: UUID of the image
            photo_type: Type of photo ('original' or 'thumb'). If None, deletes both.
        
        Raises:
            StorageError: If deletion fails after retries
        """
        if photo_type:
            object_path = f"events/{event_id}/{photo_type}/{image_id}.jpg"
            try:
                self.client.remove_object(self.bucket, object_path)
            except S3Error as e:
                raise StorageError(f"Failed to delete photo: {str(e)}")
        else:
            # Delete both original and thumbnail
            for ptype in ["original", "thumb"]:
                object_path = f"events/{event_id}/{ptype}/{image_id}.jpg"
                try:
                    self.client.remove_object(self.bucket, object_path)
                except S3Error:
                    # Ignore errors if file doesn't exist
                    pass
    
    def generate_presigned_url(
        self,
        event_id: uuid.UUID,
        image_id: uuid.UUID,
        photo_type: str = "original",
        expiry_minutes: int = 15,
        db: Optional[Session] = None,
        validate_event: bool = True
    ) -> str:
        """
        Generate a URL for photo access.

        For public buckets, returns a direct URL.
        For private buckets, generates a presigned URL.

        Args:
            event_id: UUID of the event
            image_id: UUID of the image
            photo_type: Type of photo ('original' or 'thumb')
            expiry_minutes: URL expiry time in minutes (for presigned URLs)
            db: Database session for validation (optional)
            validate_event: Whether to validate image belongs to event

        Returns:
            URL string for accessing the photo

        Raises:
            ValueError: If validation fails and image doesn't belong to event
            StorageError: If URL generation fails
        """
        # Validate that image belongs to event if requested
        if validate_event and db:
            from app.models import Image
            image = db.query(Image).filter(Image.id == image_id).first()
            if not image:
                raise ValueError(f"Image {image_id} not found")
            if image.event_id != event_id:
                raise ValueError(f"Image {image_id} does not belong to event {event_id}")

        object_path = f"events/{event_id}/{photo_type}/{image_id}.jpg"

        # Use direct URL for public bucket (no signature needed)
        from app.config import settings
        external_endpoint = settings.minio_external_endpoint
        protocol = "https" if settings.minio_external_secure else "http"

        # Build direct URL for public bucket access
        url = f"{protocol}://{external_endpoint}/{self.bucket}/{object_path}"
        return url
    
    def delete_event_photos(self, event_id: uuid.UUID):
        """
        Delete all photos for an event from MinIO.
        
        Args:
            event_id: UUID of the event
        
        Raises:
            StorageError: If deletion fails
        """
        # Delete all objects under events/{event_id}/
        prefix = f"events/{event_id}/"
        
        try:
            # List all objects with the prefix
            objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
            
            # Delete each object
            for obj in objects:
                try:
                    self.client.remove_object(self.bucket, obj.object_name)
                except S3Error:
                    # Continue deleting other objects even if one fails
                    pass
        except S3Error as e:
            raise StorageError(f"Failed to delete event photos: {str(e)}")


# Singleton instance
storage_service = StorageService()
