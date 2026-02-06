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
    minio_external_secure: bool = False  # True in production (URLs served via HTTPS reverse proxy)
    
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
    
    # Frontend URL (used for guest links and QR codes)
    frontend_url: str = "http://localhost:3000"

    # SMTP (email)
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@ahgir.com"

    # CORS
    cors_origins: str = "http://localhost:3000"  # Comma-separated; set to "https://ahgir.com" in production

    # Rate Limiting
    scan_rate_limit: int = 30
    scan_rate_window_hours: int = 1
    auth_rate_limit: int = 10
    auth_rate_window_hours: int = 1
    share_rate_limit: int = 60
    share_rate_window_hours: int = 1
    bulk_download_max_images: int = 100
    bulk_download_max_bytes: int = 500 * 1024 * 1024  # 500 MB
    
    class Config:
        env_file = ".env"

settings = Settings()
