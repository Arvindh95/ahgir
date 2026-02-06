"""CompreFace API client for face recognition."""

import httpx
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings

logger = logging.getLogger(__name__)


class CompreFaceClient:
    """Client for CompreFace Recognition API."""

    def __init__(self):
        self.base_url = settings.compreface_api_url
        self.api_key = settings.compreface_api_key
        self._recognition_service_name = "picur-recognition"

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "x-api-key": self.api_key,
        }

    async def health_check(self) -> bool:
        """Check if CompreFace is healthy by listing subjects."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/recognition/subjects",
                    headers=self._get_headers()
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"CompreFace health check failed: {e}")
            return False

    async def add_face(
        self,
        image_data: bytes,
        subject_id: str,
        det_prob_threshold: float = 0.8
    ) -> Dict[str, Any]:
        """
        Add a face to the recognition collection.

        Args:
            image_data: Image bytes (JPEG/PNG)
            subject_id: Unique identifier for this face (e.g., image_id + face_index)
            det_prob_threshold: Minimum detection confidence

        Returns:
            dict with face details including embedding and bounding box
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                files = {"file": ("image.jpg", image_data, "image/jpeg")}
                params = {
                    "subject": subject_id,
                    "det_prob_threshold": det_prob_threshold,
                }

                response = await client.post(
                    f"{self.base_url}/api/v1/recognition/faces",
                    headers=self._get_headers(),
                    files=files,
                    params=params,
                )

                if response.status_code == 201:
                    result = response.json()
                    logger.info(f"Added face for subject {subject_id}")
                    return result
                else:
                    logger.error(f"Failed to add face: {response.status_code} - {response.text}")
                    return {"error": response.text, "status_code": response.status_code}

        except Exception as e:
            logger.error(f"Error adding face: {e}")
            return {"error": str(e)}

    async def detect_faces(
        self,
        image_data: bytes,
        det_prob_threshold: float = 0.8,
        face_plugins: str = "landmarks,gender,age"
    ) -> List[Dict[str, Any]]:
        """
        Detect faces in an image without adding them.

        Args:
            image_data: Image bytes
            det_prob_threshold: Minimum detection confidence
            face_plugins: Additional plugins to run

        Returns:
            List of detected faces with bounding boxes
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                files = {"file": ("image.jpg", image_data, "image/jpeg")}
                params = {
                    "det_prob_threshold": det_prob_threshold,
                    "face_plugins": face_plugins,
                }

                response = await client.post(
                    f"{self.base_url}/api/v1/detection/detect",
                    headers=self._get_headers(),
                    files=files,
                    params=params,
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get("result", [])
                else:
                    logger.error(f"Face detection failed: {response.status_code} - {response.text}")
                    return []

        except Exception as e:
            logger.error(f"Error detecting faces: {e}")
            return []

    async def recognize_faces(
        self,
        image_data: bytes,
        det_prob_threshold: float = 0.8,
        prediction_count: int = 50,
        face_plugins: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Recognize faces in an image against the stored collection.

        Args:
            image_data: Image bytes (selfie/scan)
            det_prob_threshold: Minimum detection confidence
            prediction_count: Max number of similar faces to return per detected face
            face_plugins: Additional plugins to run

        Returns:
            List of recognized faces with similarity scores
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                files = {"file": ("image.jpg", image_data, "image/jpeg")}
                params = {
                    "det_prob_threshold": det_prob_threshold,
                    "prediction_count": prediction_count,
                    "face_plugins": face_plugins,
                }

                response = await client.post(
                    f"{self.base_url}/api/v1/recognition/recognize",
                    headers=self._get_headers(),
                    files=files,
                    params=params,
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get("result", [])
                else:
                    logger.error(f"Face recognition failed: {response.status_code} - {response.text}")
                    return []

        except Exception as e:
            logger.error(f"Error recognizing faces: {e}")
            return []

    async def delete_face(self, subject_id: str) -> bool:
        """Delete a face from the collection."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/api/v1/recognition/faces",
                    headers=self._get_headers(),
                    params={"subject": subject_id},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting face: {e}")
            return False

    async def delete_all_faces_for_subject(self, subject_id: str) -> bool:
        """Delete all faces for a subject."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/api/v1/recognition/faces",
                    headers=self._get_headers(),
                    params={"subject": subject_id},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting faces for subject: {e}")
            return False

    async def get_subjects(self) -> List[str]:
        """Get all subjects in the recognition collection."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/recognition/subjects",
                    headers=self._get_headers(),
                )
                if response.status_code == 200:
                    result = response.json()
                    return result.get("subjects", [])
                return []
        except Exception as e:
            logger.error(f"Error getting subjects: {e}")
            return []


# Singleton instance
compreface_client = CompreFaceClient()
