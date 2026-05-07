import itertools
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Environment
    environment: str = "development"  # set to "production" in prod env

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
    face_similarity_threshold: float = 0.85
    face_min_detection_probability: float = 0.7
    face_min_crop_pixels: int = 80

    # CompreFace (comma-separated URLs for round-robin load balancing)
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
    smtp_from_email: str = "noreply@picur.my"

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    # Stripe Price IDs (created by scripts/setup_stripe_products.py)
    stripe_price_starter_monthly: str = ""
    stripe_price_starter_yearly: str = ""
    stripe_price_pro_monthly: str = ""
    stripe_price_pro_yearly: str = ""

    # Subscription grace period before downgrade-to-free after payment failure
    subscription_grace_period_days: int = 3

    # CORS
    cors_origins: str = "http://localhost:3000"  # Comma-separated; set to "https://picur.my" in production

    # Rate Limiting
    scan_rate_limit: int = 30
    scan_rate_window_hours: int = 1
    auth_rate_limit: int = 30
    auth_rate_window_hours: int = 1
    # Per-event passcode brute-force limiter (defends against rotating-IP attackers).
    event_passcode_rate_limit: int = 10
    event_passcode_rate_window_hours: int = 1
    share_rate_limit: int = 60
    share_rate_window_hours: int = 1
    bulk_download_max_images: int = 100
    bulk_download_max_bytes: int = 500 * 1024 * 1024  # 500 MB
    # Per-file upload cap (matches Caddy request_body max_size in prod).
    max_upload_bytes: int = 25 * 1024 * 1024  # 25 MB
    # Per-frame cap on guest face-scan submissions (decoded bytes).
    max_scan_frame_bytes: int = 8 * 1024 * 1024  # 8 MB
    # Total cap across all frames in one scan request.
    max_scan_total_bytes: int = 25 * 1024 * 1024  # 25 MB
    
    class Config:
        env_file = ".env"

settings = Settings()


def validate_production_secrets():
    """Fail fast if production is missing critical secrets or using dev defaults."""
    if settings.environment.lower() != "production":
        return

    errors = []
    if settings.jwt_secret_key in ("your-secret-key-change-in-production", "dev-only-not-for-prod", ""):
        errors.append("JWT_SECRET_KEY is unset or using dev default")
    if not settings.stripe_secret_key:
        errors.append("STRIPE_SECRET_KEY is unset")
    if not settings.stripe_webhook_secret:
        errors.append("STRIPE_WEBHOOK_SECRET is unset")
    if not settings.smtp_username or not settings.smtp_password:
        errors.append("SMTP_USERNAME or SMTP_PASSWORD is unset")
    if not settings.compreface_api_key:
        errors.append("COMPREFACE_API_KEY is unset")
    if settings.minio_secret_key in ("minioadmin", "minioadmin_dev_only", ""):
        errors.append("MINIO_SECRET_KEY is unset or using dev default")
    if "localhost" in settings.cors_origins.lower() or "127.0.0.1" in settings.cors_origins:
        errors.append(f"CORS_ORIGINS contains localhost in production: {settings.cors_origins}")

    if errors:
        raise RuntimeError(
            "Production startup blocked due to insecure config:\n  - " + "\n  - ".join(errors)
        )


# NOTE: don't call validate_production_secrets() at module import — it would block the
# worker (which imports config.py for DB/Redis/MinIO settings but doesn't need Stripe
# or CORS). main.py calls it from FastAPI startup so only the backend validates.

# Round-robin CompreFace URL selector (supports comma-separated URLs)
_compreface_urls = [u.strip() for u in settings.compreface_api_url.split(",") if u.strip()]
_compreface_cycle = itertools.cycle(_compreface_urls)

def get_compreface_url() -> str:
    """Get the next CompreFace API URL in round-robin order."""
    return next(_compreface_cycle)
