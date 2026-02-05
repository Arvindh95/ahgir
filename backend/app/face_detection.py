"""Face detection and embedding extraction using InsightFace."""

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

# Configuration for different group sizes
DETECTION_CONFIGS = {
    'small': {  # 1-10 people / selfies - very lenient
        'det_size': (640, 640),
        'min_face_size': 20,
        'det_threshold': 0.1,  # Very low threshold for selfies/webcam
    },
    'medium': {  # 10-30 people
        'det_size': (1280, 1280),
        'min_face_size': 32,
        'det_threshold': 0.3,
    },
    'large': {  # 30-100+ people
        'det_size': (1920, 1920),
        'min_face_size': 20,
        'det_threshold': 0.25,
    },
}


class FaceDetector:
    """Face detector using InsightFace buffalo_l model with adaptive detection."""

    _instance = None
    _app = None
    _current_det_size = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FaceDetector, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize InsightFace with buffalo_l model."""
        if self._app is None:
            logger.info("Initializing InsightFace with buffalo_l model...")
            self._app = FaceAnalysis(
                name='buffalo_l',
                providers=['CPUExecutionProvider']  # Use CPU for compatibility
            )
            # Start with large detection size for maximum accuracy
            config = DETECTION_CONFIGS['large']
            self._app.prepare(ctx_id=0, det_size=config['det_size'], det_thresh=config['det_threshold'])
            self._current_det_size = config['det_size']
            logger.info(f"InsightFace initialized with det_size={config['det_size']}")

    def _set_detection_size(self, det_size: Tuple[int, int], det_thresh: float):
        """Dynamically change detection size if needed."""
        if self._current_det_size != det_size:
            logger.info(f"Changing detection size from {self._current_det_size} to {det_size}")
            self._app.prepare(ctx_id=0, det_size=det_size, det_thresh=det_thresh)
            self._current_det_size = det_size

        # Also try to set threshold directly on detection models
        for model in self._app.models:
            if hasattr(model, 'det_thresh'):
                model.det_thresh = det_thresh
                logger.info(f"Set det_thresh={det_thresh} on model {model.__class__.__name__}")

    def detect_faces(
        self,
        image_data: bytes,
        min_face_size: int = 20,
        det_threshold: float = 0.25,
        config_name: Optional[str] = None
    ) -> List[Tuple[np.ndarray, List[float], float]]:
        """
        Detect faces in an image and extract embeddings.

        Automatically adapts detection parameters based on image size to handle
        everything from small portraits to large group photos (100+ people).

        Args:
            image_data: Image bytes (JPEG or PNG)
            min_face_size: Minimum face size in pixels (default: 20 for large groups)
            det_threshold: Detection confidence threshold (default: 0.25)
            config_name: Optional config preset ('small', 'medium', 'large')

        Returns:
            List of tuples containing:
                - embedding: 512-dimensional numpy array
                - bbox: Bounding box as [x1, y1, x2, y2]
                - quality_score: Detection confidence score

        Raises:
            ValueError: If image cannot be decoded
        """
        # Decode image from bytes
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Failed to decode image")

        # Auto-select config based on image dimensions if not specified
        if config_name and config_name in DETECTION_CONFIGS:
            config = DETECTION_CONFIGS[config_name]
            min_face_size = config['min_face_size']
            det_threshold = config['det_threshold']
            self._set_detection_size(config['det_size'], det_threshold)
        else:
            # Use adaptive sizing based on image resolution
            img_height, img_width = img.shape[:2]
            img_max = max(img_width, img_height)

            # For high-res images (likely group photos), use larger detection
            if img_max >= 3000:
                config = DETECTION_CONFIGS['large']
            elif img_max >= 1500:
                config = DETECTION_CONFIGS['medium']
            else:
                config = DETECTION_CONFIGS['small']

            # Apply config values for filtering (THIS WAS THE BUG - these weren't being set!)
            min_face_size = config['min_face_size']
            det_threshold = config['det_threshold']
            logger.info(f"Auto-selected '{list(DETECTION_CONFIGS.keys())[list(DETECTION_CONFIGS.values()).index(config)]}' config: det_threshold={det_threshold}, min_face_size={min_face_size}")

            # Only change detection size if needed (to avoid reinit overhead)
            if self._current_det_size != config['det_size']:
                self._set_detection_size(config['det_size'], config['det_threshold'])

        # Detect faces - try BGR first (OpenCV default)
        faces = self._app.get(img)
        logger.info(f"Raw detection found {len(faces)} faces in image ({img.shape[1]}x{img.shape[0]}) [BGR]")

        # If no faces found, try with enhanced image (helps with webcam)
        if len(faces) == 0:
            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
            faces = self._app.get(enhanced)
            logger.info(f"Raw detection found {len(faces)} faces [CLAHE enhanced]")

        # If still no faces, try RGB conversion
        if len(faces) == 0:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            faces = self._app.get(img_rgb)
            logger.info(f"Raw detection found {len(faces)} faces [RGB conversion]")

        # Last resort: try with increased brightness
        if len(faces) == 0:
            bright = cv2.convertScaleAbs(img, alpha=1.3, beta=30)
            faces = self._app.get(bright)
            logger.info(f"Raw detection found {len(faces)} faces [brightness adjusted]")

        # Filter and extract face data
        results = []
        for face in faces:
            # Check detection score
            if face.det_score < det_threshold:
                continue

            # Check face size
            bbox = face.bbox.astype(int).tolist()
            face_width = bbox[2] - bbox[0]
            face_height = bbox[3] - bbox[1]

            if face_width < min_face_size or face_height < min_face_size:
                logger.debug(f"Skipping small face: {face_width}x{face_height}")
                continue

            # Extract embedding (512-dim vector)
            embedding = face.embedding

            # Normalize embedding (L2 normalization)
            embedding = embedding / np.linalg.norm(embedding)

            results.append((
                embedding,
                bbox,
                float(face.det_score)
            ))

        logger.info(f"Returning {len(results)} faces after filtering")
        return results


# Singleton instance
face_detector = FaceDetector()
