"""MinIO storage service for photo management."""

import hashlib
import hmac
import time
from minio import Minio
from minio.error import S3Error
from minio.sse import SseS3
from io import BytesIO
from typing import Optional
import uuid
from datetime import timedelta
from sqlalchemy.orm import Session

from app.config import settings
from app.retry_utils import exponential_backoff
from app.exceptions import StorageError


# Derive a URL-signing key from JWT secret so we don't need a second secret.
# Domain-separated via HKDF-style salt so a leak of signed URLs cannot forge JWTs.
def _url_signing_key() -> bytes:
    return hashlib.sha256(
        b"picur:url-signing-v1:" + settings.jwt_secret_key.encode("utf-8")
    ).digest()


_VALID_PHOTO_TYPES = {"original", "thumb", "cover"}


def _build_signature_payload(event_id: str, image_id: str, photo_type: str, expires: int) -> bytes:
    return f"{event_id}:{image_id}:{photo_type}:{expires}".encode("utf-8")


def generate_signed_cover_url(
    event_id: uuid.UUID,
    expires_minutes: int = 15,
) -> str:
    """Build a short-lived signed URL for an event's cover image."""
    # Cover is event-scoped (one per event), so we use event_id in the image_id slot
    # as a sentinel — both signer and verifier agree on this convention.
    return generate_signed_url(event_id, event_id, "cover", expires_minutes)


def generate_signed_url(
    event_id: uuid.UUID,
    image_id: uuid.UUID,
    photo_type: str = "original",
    expires_minutes: int = 15,
) -> str:
    """Build a short-lived signed URL pointing at the backend photo route.

    The URL carries the path + an HMAC signature over (event_id, image_id, photo_type, expires).
    Backend validates the signature before streaming bytes from MinIO. No JWT needed because
    the signed URL itself is the bearer.
    """
    if photo_type not in _VALID_PHOTO_TYPES:
        raise ValueError(f"photo_type must be one of {_VALID_PHOTO_TYPES}, got {photo_type!r}")
    expires = int(time.time()) + expires_minutes * 60
    payload = _build_signature_payload(str(event_id), str(image_id), photo_type, expires)
    sig = hmac.new(_url_signing_key(), payload, hashlib.sha256).hexdigest()
    return (
        f"{settings.frontend_url}/api/photos/{event_id}/{image_id}/{photo_type}"
        f"?expires={expires}&sig={sig}"
    )


def verify_signed_url(
    event_id: str,
    image_id: str,
    photo_type: str,
    expires: int,
    sig: str,
) -> bool:
    """Constant-time verify of an HMAC-signed photo URL. False if expired or tampered."""
    if photo_type not in _VALID_PHOTO_TYPES:
        return False
    if expires < int(time.time()):
        return False
    payload = _build_signature_payload(event_id, image_id, photo_type, expires)
    expected = hmac.new(_url_signing_key(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


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
    def upload_cover(
        self,
        event_id: uuid.UUID,
        photo_data: bytes,
        content_type: str = "image/jpeg",
    ) -> str:
        """Upload an event cover image to MinIO with retry. Always overwrites existing cover.

        Passes sse=SseS3() so MinIO encrypts the object at write time
        with the server-managed KMS key (configured via
        MINIO_KMS_SECRET_KEY env in docker-compose.vps.yml). Requires
        MinIO to have been started with that env or this call 400s.
        """
        object_path = f"events/{event_id}/cover.jpg"
        try:
            self.client.put_object(
                self.bucket,
                object_path,
                BytesIO(photo_data),
                length=len(photo_data),
                content_type=content_type,
                sse=SseS3(),
            )
            return object_path
        except S3Error as e:
            raise StorageError(f"Failed to upload cover: {str(e)}")

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
                content_type="image/jpeg",
                sse=SseS3(),  # SSE-S3: server-side encryption with MinIO KMS
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
            image_id: UUID of the image (ignored when photo_type='cover')
            photo_type: 'original' | 'thumb' | 'cover'

        Returns:
            Image bytes

        Raises:
            FileNotFoundError: If photo not found
            StorageError: If retrieval fails after retries
        """
        if photo_type == "cover":
            object_path = f"events/{event_id}/cover.jpg"
        else:
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
    
    def generate_url(
        self,
        event_id: uuid.UUID,
        image_id: uuid.UUID,
        photo_type: str = "original",
        expires_minutes: int = 15,
    ) -> str:
        """Return a short-lived signed URL pointing at the backend photo route.

        Replaces the previous unsigned MinIO direct URL. Callers do NOT need to validate
        ownership before calling this — the route handler validates the signature, and
        the signature is only generated from authenticated contexts (event_token / admin).
        """
        return generate_signed_url(event_id, image_id, photo_type, expires_minutes)

    def generate_presigned_url(
        self,
        event_id: uuid.UUID,
        image_id: uuid.UUID,
        photo_type: str = "original",
        expiry_minutes: int = 15,
        db: Optional[Session] = None,
        validate_event: bool = True,
    ) -> str:
        """Back-compat shim — older tests and call sites used this name. Delegates to
        the new HMAC-signed URL. The DB / validate_event parameters are accepted for
        signature compatibility but no longer needed (signature is the credential).
        """
        if validate_event and db:
            from app.models import Image
            image = db.query(Image).filter(Image.id == image_id).first()
            if not image:
                raise ValueError(f"Image {image_id} not found")
            if image.event_id != event_id:
                raise ValueError(f"Image {image_id} does not belong to event {event_id}")
        return generate_signed_url(event_id, image_id, photo_type, expiry_minutes)
    
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
