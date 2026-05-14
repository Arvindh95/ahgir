"""
Regression tests for the email-layer review:

P2 - send_email must use a CERT-verifying STARTTLS context so a network
     MITM between the backend and the SMTP relay can't intercept SMTP
     creds + verification / reset links.

P2 - When enqueue fails (Redis / RQ down), the user-facing handler
     must NOT silently return success. /register and /resend-verify
     return 503. /forgot-password keeps its anti-enumeration generic
     200 but logs critically if both async + sync delivery fail.

P3 - validate_production_secrets must reject blank / placeholder
     SMTP_FROM_EMAIL alongside missing SMTP_USERNAME / SMTP_PASSWORD.
"""
import smtplib
import ssl
from unittest.mock import MagicMock, patch

import pytest


# ─── P2 #1: STARTTLS context ──────────────────────────────────────────────


def test_send_email_uses_verifying_tls_context(monkeypatch):
    """Verify the SMTP STARTTLS upgrade is given a CERT_REQUIRED context.
    Pre-fix, server.starttls() was called with no context, defaulting
    to CERT_NONE — a network MITM could decrypt SMTP traffic.
    """
    from app import email as email_module

    captured = {}

    class _FakeSMTP:
        def __init__(self, host, port):
            captured["host"] = host
            captured["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            captured["context"] = context

        def login(self, *a, **kw):
            captured["login_called"] = True

        def sendmail(self, *a, **kw):
            captured["sendmail_called"] = True

    monkeypatch.setattr(email_module.smtplib, "SMTP", _FakeSMTP)
    # Stub the retry decorator so we can call the underlying body once.
    email_module.send_email("dst@example.com", "Subject", "<p>hi</p>")

    assert "context" in captured
    ctx = captured["context"]
    assert isinstance(ctx, ssl.SSLContext), "starttls must receive an ssl.SSLContext"
    assert ctx.verify_mode == ssl.CERT_REQUIRED, (
        "TLS context must verify the SMTP relay's certificate; "
        f"got verify_mode={ctx.verify_mode}"
    )
    assert ctx.check_hostname is True, (
        "TLS context must check the relay's hostname against the cert"
    )


# ─── P3 #3: production validation requires SMTP_FROM_EMAIL ────────────────


def _baseline_prod_config(monkeypatch):
    """Set every field validate_production_secrets cares about to a
    valid value, so test cases can flip ONE field at a time and
    assert the new failure."""
    from app import config

    valid = {
        "environment": "production",
        "jwt_secret_key": "x" * 64,
        "stripe_secret_key": "sk_live_real_key",
        "stripe_webhook_secret": "whsec_real",
        "smtp_username": "real-mailer",
        "smtp_password": "real-smtp-secret",
        "smtp_from_email": "noreply@picur.my",
        "compreface_api_key": "real-recognition",
        "compreface_detection_api_key": "real-detection",
        "minio_secret_key": "real-minio-secret",
        "cors_origins": "https://picur.my",
        "frontend_url": "https://picur.my",
    }
    for k, v in valid.items():
        monkeypatch.setattr(config.settings, k, v)


def test_production_validation_rejects_blank_smtp_from_email(monkeypatch):
    """Blank SMTP_FROM_EMAIL must fail production validation. Pre-fix
    the validator skipped this field entirely — production could come
    up healthy and silently fail every transactional email."""
    from app import config

    _baseline_prod_config(monkeypatch)
    monkeypatch.setattr(config.settings, "smtp_from_email", "")

    with pytest.raises(RuntimeError) as exc:
        config.validate_production_secrets()
    assert "SMTP_FROM_EMAIL" in str(exc.value)


def test_production_validation_rejects_placeholder_smtp_from_email(monkeypatch):
    from app import config

    _baseline_prod_config(monkeypatch)
    monkeypatch.setattr(config.settings, "smtp_from_email", "noreply@yourdomain.com")

    with pytest.raises(RuntimeError) as exc:
        config.validate_production_secrets()
    assert "SMTP_FROM_EMAIL" in str(exc.value)


def test_production_validation_rejects_non_email_smtp_from_email(monkeypatch):
    from app import config

    _baseline_prod_config(monkeypatch)
    monkeypatch.setattr(config.settings, "smtp_from_email", "definitely-not-an-email")

    with pytest.raises(RuntimeError) as exc:
        config.validate_production_secrets()
    assert "SMTP_FROM_EMAIL" in str(exc.value)


def test_production_validation_accepts_real_smtp_from_email(monkeypatch):
    """Sanity check the baseline: with all values valid the validator
    passes."""
    from app import config

    _baseline_prod_config(monkeypatch)
    # Should not raise.
    config.validate_production_secrets()
