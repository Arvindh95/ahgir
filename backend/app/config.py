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
    # KMS master key set on the MinIO container (format: <name>:<base64-32B>).
    # The backend never *uses* this value (MinIO does), but mirroring it into
    # the backend env lets validate_production_secrets() fail fast at startup
    # instead of waiting for every upload to 400. Empty in dev.
    minio_kms_secret_key: str = ""
    
    # Redis
    redis_url: str = "redis://redis:6379/0"
    
    # JWT
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Face Recognition
    # Cosine-similarity floor applied to LARGE indexed faces (>= face_size_large_px).
    # Tiny crops produce noisier embeddings and need a stricter floor — set those
    # via the *_medium / *_small variants below.
    face_similarity_threshold: float = 0.80
    face_similarity_threshold_medium: float = 0.85
    face_similarity_threshold_small: float = 0.90
    # Indexed-face min_side (px) boundaries selecting which threshold applies.
    face_size_medium_px: int = 60
    face_size_large_px: int = 150
    # Index broadly, then let CompreFace's add-face detection gate and the
    # tiered scan similarity threshold reject unusable or unrelated faces.
    face_min_detection_probability: float = 0.3
    # Minimum bounding-box side (px) for a detected face to be registered.
    face_min_crop_pixels: int = 32
    # Fraction of the bbox width/height padded onto each crop before sending to
    # the recognition embedder. More context (hair, ears, jaw) yields a more
    # stable embedding; 0.4 ≈ 40% on each side.
    face_crop_padding_factor: float = 0.4
    # Cross-gender filter — disabled by default. Enabling requires the gender
    # plugin to be present in compreface-core's ML_PLUGINS_LIST and a full
    # reindex so Face.gender is populated.
    face_gender_filter_enabled: bool = False

    # CompreFace (comma-separated URLs for round-robin load balancing)
    compreface_api_url: str = "http://compreface-api:8080"
    compreface_api_key: str = ""  # Recognition service API key
    compreface_detection_api_key: str = ""  # Detection service API key
    # Mirror of COMPREFACE_DB_PASSWORD (set on the CompreFace postgres + API
    # containers). Backend doesn't connect to that DB, but mirroring lets
    # validate_production_secrets() refuse the upstream default "postgres".
    compreface_db_password: str = ""
    
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
    # Optional Stripe Billing Portal Configuration ID. If set, /payments/portal
    # passes this as `configuration=`. Use it to pin the portal to:
    #   subscription_cancel.mode = at_period_end
    #   subscription_update.proration_behavior = none
    #   subscription_update.schedule_at_period_end = true
    # so plan changes / cancellations honor the "paid period continues" rule
    # we promise in billing.tsx. The in-app /payments/cancel endpoint already
    # enforces at-period-end for cancellations; this config covers the
    # remaining portal-driven plan-change paths.
    stripe_billing_portal_config_id: str = ""
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
    # Two-tier passcode brute-force defence:
    # * event_passcode_rate_limit applies per event slug. Catches
    #   distributed (rotating-IP) attacks but, if set too low, a single
    #   bad actor could exhaust it and lock all guests out for the window.
    # * event_passcode_ip_rate_limit applies per (slug, client_ip) pair.
    #   Catches a single bad actor without affecting other guests.
    # Both must allow the attempt for it to proceed.
    event_passcode_rate_limit: int = 50
    event_passcode_rate_window_hours: int = 1
    event_passcode_ip_rate_limit: int = 5
    event_passcode_ip_rate_window_hours: int = 1
    share_rate_limit: int = 60
    share_rate_window_hours: int = 1
    # Per-IP abuse report cap. Same window as scan/auth — abuse mass-reporting
    # is rare and bursty, 5/hour per IP balances responsiveness with queue
    # protection.
    abuse_report_rate_limit: int = 5
    abuse_report_rate_window_hours: int = 1
    bulk_download_max_images: int = 100
    bulk_download_max_bytes: int = 500 * 1024 * 1024  # 500 MB
    # Per-file upload cap (matches Caddy request_body max_size in prod).
    max_upload_bytes: int = 25 * 1024 * 1024  # 25 MB
    # Per-file upload chunk size used by the streaming reader. Reading in
    # chunks (rather than one big .read()) lets us abort once max_upload_bytes
    # is exceeded without buffering an oversized payload into RAM first.
    upload_chunk_bytes: int = 1 * 1024 * 1024  # 1 MB
    # Per-frame cap on guest face-scan submissions (decoded bytes).
    max_scan_frame_bytes: int = 8 * 1024 * 1024  # 8 MB
    # Total cap across all frames in one scan request.
    max_scan_total_bytes: int = 25 * 1024 * 1024  # 25 MB
    # Maximum side length (px) sent to CompreFace per scan frame. Sanitised
    # selfies bigger than this are downsized before upload — CompreFace
    # doesn't need 4K input to match a face, and capping the side bounds the
    # bytes we forward upstream regardless of what the guest submitted.
    scan_frame_max_side_px: int = 1024
    
    class Config:
        env_file = ".env"

settings = Settings()


_PLACEHOLDER_TOKENS = ("change_me", "changeme", "your-secret", "yourdomain", "example.com")


def _looks_like_placeholder(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(token in lowered for token in _PLACEHOLDER_TOKENS)


def _password_from_url(url: str) -> str:
    """Pull the password out of a sqlalchemy/postgres URL. Returns '' on parse
    failure or when the URL has no password — caller treats both as 'missing'."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.password or ""
    except Exception:
        return ""


def _looks_like_production() -> bool:
    """Heuristics that strongly suggest this process is running in production
    even when ENVIRONMENT was left at the development default.

    Prevents the silent-prod-as-dev failure: someone copies env values for
    domain hosts but forgets ENVIRONMENT=production, so the dev defaults
    skip secret validation entirely. If anything looks production-shaped,
    we assert anyway.
    """
    frontend = (getattr(settings, "frontend_url", "") or "").lower()
    minio_ext = (getattr(settings, "minio_external_endpoint", "") or "").lower()
    cors = (getattr(settings, "cors_origins", "") or "").lower()

    def _is_real_host(value: str) -> bool:
        if not value:
            return False
        if "localhost" in value or "127.0.0.1" in value or "0.0.0.0" in value:
            return False
        # An https scheme or a hostname containing a TLD-looking dot is a
        # strong signal that this is a real deployment, not a dev box.
        return value.startswith("https://") or ("." in value.split("//")[-1].split("/")[0])

    return any(_is_real_host(v) for v in (frontend, minio_ext, cors))


def validate_production_secrets():
    """Fail fast if production is missing critical secrets or using dev defaults.

    Trips when EITHER ENVIRONMENT is explicitly production OR the resolved
    config looks production-shaped (real frontend URL, real MinIO host, real
    CORS origin). The latter catches the silent-prod-as-dev failure where a
    missing ENVIRONMENT= leaves the development default in place and skips
    every secret check.
    """
    if settings.environment.lower() != "production":
        if not _looks_like_production():
            return
        # Looks-like-prod fallthrough. Treat as production for the rest of
        # this function; refuse to keep running with a development label
        # against a production-shaped config.
        # (We don't mutate settings.environment here; the caller can fix the
        # env once the error message points at the missing flag.)

    errors = []
    if settings.environment.lower() != "production":
        errors.append(
            f"ENVIRONMENT is set to '{settings.environment}' but the resolved "
            f"config looks like production (frontend_url, minio_external_endpoint, "
            f"or cors_origins points at a real host). Set ENVIRONMENT=production "
            f"to enable production behaviour."
        )

    if settings.jwt_secret_key in ("your-secret-key-change-in-production", "dev-only-not-for-prod", ""):
        errors.append("JWT_SECRET_KEY is unset or using dev default")
    elif len(settings.jwt_secret_key) < 32:
        errors.append("JWT_SECRET_KEY must be at least 32 characters")
    elif _looks_like_placeholder(settings.jwt_secret_key):
        errors.append("JWT_SECRET_KEY still contains a placeholder (e.g. CHANGE_ME_*)")
    if not settings.stripe_secret_key:
        errors.append("STRIPE_SECRET_KEY is unset")
    elif _looks_like_placeholder(settings.stripe_secret_key):
        errors.append("STRIPE_SECRET_KEY still contains a placeholder (e.g. CHANGE_ME_*)")
    if not settings.stripe_webhook_secret:
        errors.append("STRIPE_WEBHOOK_SECRET is unset")
    elif _looks_like_placeholder(settings.stripe_webhook_secret):
        errors.append("STRIPE_WEBHOOK_SECRET still contains a placeholder (e.g. CHANGE_ME_*)")
    if not settings.smtp_username or not settings.smtp_password:
        errors.append("SMTP_USERNAME or SMTP_PASSWORD is unset")
    elif _looks_like_placeholder(settings.smtp_username) or _looks_like_placeholder(settings.smtp_password):
        errors.append("SMTP_USERNAME or SMTP_PASSWORD still contains a placeholder")
    # SMTP_FROM_EMAIL has a default in the code, but docker-compose.yml
    # can override it with the empty string. Without a usable From
    # address, transactional delivery fails (every relay rejects
    # MAIL FROM:<>) even though SMTP_USERNAME / SMTP_PASSWORD pass.
    from_email = getattr(settings, "smtp_from_email", "") or ""
    if not from_email.strip():
        errors.append("SMTP_FROM_EMAIL is unset")
    elif _looks_like_placeholder(from_email):
        errors.append("SMTP_FROM_EMAIL still contains a placeholder (e.g. noreply@yourdomain.com)")
    elif "@" not in from_email or from_email.startswith("@") or from_email.endswith("@"):
        errors.append(f"SMTP_FROM_EMAIL does not look like an email address: {from_email}")
    if not settings.compreface_api_key:
        errors.append("COMPREFACE_API_KEY is unset")
    elif _looks_like_placeholder(settings.compreface_api_key):
        errors.append("COMPREFACE_API_KEY still contains a placeholder (e.g. CHANGE_ME_*)")
    if not settings.compreface_detection_api_key:
        errors.append("COMPREFACE_DETECTION_API_KEY is unset")
    elif _looks_like_placeholder(settings.compreface_detection_api_key):
        errors.append("COMPREFACE_DETECTION_API_KEY still contains a placeholder (e.g. CHANGE_ME_*)")
    if settings.minio_secret_key in ("minioadmin", "minioadmin_dev_only", ""):
        errors.append("MINIO_SECRET_KEY is unset or using dev default")
    elif _looks_like_placeholder(settings.minio_secret_key):
        errors.append("MINIO_SECRET_KEY still contains a placeholder (e.g. CHANGE_ME_*)")
    # KMS key mirror — storage.py uses sse=SseS3() so MinIO MUST have been
    # started with MINIO_KMS_SECRET_KEY or every upload 400s. Fail fast.
    if not settings.minio_kms_secret_key:
        errors.append("MINIO_KMS_SECRET_KEY is unset (required for SSE-S3 uploads)")
    elif _looks_like_placeholder(settings.minio_kms_secret_key):
        errors.append("MINIO_KMS_SECRET_KEY still contains a placeholder (e.g. CHANGE_ME_*)")
    elif ":" not in settings.minio_kms_secret_key:
        errors.append("MINIO_KMS_SECRET_KEY must be in '<name>:<base64-key>' format")
    # App Postgres password — parse from DATABASE_URL since that's what the
    # process actually connects with. Catches the silent dev-default leak
    # where docker-compose.yml defaults POSTGRES_PASSWORD to picur_dev_only.
    db_pw = _password_from_url(settings.database_url)
    if db_pw in ("", "picur", "picur_dev_only", "postgres"):
        errors.append("DATABASE_URL password is unset or using a dev default")
    elif _looks_like_placeholder(db_pw):
        errors.append("DATABASE_URL password still contains a placeholder (e.g. CHANGE_ME_*)")
    # CompreFace DB password — mirrored from COMPREFACE_DB_PASSWORD env.
    if settings.compreface_db_password in ("", "postgres"):
        errors.append("COMPREFACE_DB_PASSWORD is unset or using the upstream default 'postgres'")
    elif _looks_like_placeholder(settings.compreface_db_password):
        errors.append("COMPREFACE_DB_PASSWORD still contains a placeholder (e.g. CHANGE_ME_*)")
    if "localhost" in settings.cors_origins.lower() or "127.0.0.1" in settings.cors_origins:
        errors.append(f"CORS_ORIGINS contains localhost in production: {settings.cors_origins}")
    if _looks_like_placeholder(settings.cors_origins):
        errors.append(f"CORS_ORIGINS still contains a placeholder host: {settings.cors_origins}")
    if _looks_like_placeholder(getattr(settings, "frontend_url", "")):
        errors.append(f"FRONTEND_URL still contains a placeholder host: {settings.frontend_url}")

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
