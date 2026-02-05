from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://picur:picur@postgres:5432/picur"
    
    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_external_endpoint: str = "localhost:9000"  # External endpoint for browser access
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "photos"
    minio_secure: bool = False
    
    # Redis
    redis_url: str = "redis://redis:6379/0"
    
    # JWT
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Face Recognition
    face_similarity_threshold: float = 0.75

    # CompreFace
    compreface_api_url: str = "http://compreface-api:8080"
    compreface_api_key: str = ""  # Recognition service API key
    compreface_detection_api_key: str = ""  # Detection service API key
    
    # Rate Limiting
    scan_rate_limit: int = 30
    scan_rate_window_hours: int = 1
    
    class Config:
        env_file = ".env"

settings = Settings()
