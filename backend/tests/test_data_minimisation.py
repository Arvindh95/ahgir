"""
Regression tests for the data-minimisation / log-leakage review:

P2 - The public security copy promises EXIF metadata (GPS, camera
     serial, capture timestamps) is forgotten before storage. The
     image BYTES are stripped already, but the DB column Image
     .exif_data used to retain everything except GPS. extract_exif
     _data now returns {} so future uploads write nothing, and a
     migration NULLs existing rows.

P2/P3 - Signed photo URLs carry their bearer credentials in `sig`
     and `expires` query params. The error handler logs the request
     URL on every 4xx/5xx, so a failed photo fetch leaked the
     credential into logs. _redact_url() scrubs sig/expires/token
     /passcode before logging.
"""
from app.error_handler import _redact_url
from app.routers.events import extract_exif_data


# ─── P2: EXIF persistence dropped ─────────────────────────────────────────


def test_extract_exif_data_always_returns_empty_dict():
    """The function now refuses to persist EXIF tags. Any input —
    valid JPEG with EXIF, JPEG without EXIF, invalid bytes — must
    return {} so upstream Image rows store nothing identifying.
    """
    # Real-ish JPEG header bytes (no actual EXIF needed since we just
    # care that the helper returns {} regardless).
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    assert extract_exif_data(fake_jpeg) == {}
    assert extract_exif_data(b"") == {}
    assert extract_exif_data(b"not an image at all") == {}


# ─── P2/P3: signed-URL log redaction ──────────────────────────────────────


def test_redact_url_strips_sig_and_expires():
    raw = "http://testserver/photos/abc/def/thumb?expires=1778734713&sig=secrethmacvalue"
    redacted = _redact_url(raw)
    assert "secrethmacvalue" not in redacted
    assert "1778734713" not in redacted
    assert "REDACTED" in redacted
    # Path still useful for debugging.
    assert "/photos/abc/def/thumb" in redacted


def test_redact_url_keeps_non_sensitive_query_params():
    raw = "http://testserver/events?page=2&limit=50&sig=secret"
    redacted = _redact_url(raw)
    assert "page=2" in redacted
    assert "limit=50" in redacted
    assert "secret" not in redacted


def test_redact_url_handles_no_query_string():
    raw = "http://testserver/events/abc-def"
    assert _redact_url(raw) == raw


def test_redact_url_strips_token_and_passcode_keys():
    """Future-proofing: token / access_token / passcode are also
    scrubbed in case a route ever puts them in the query string.
    """
    raw = "http://testserver/x?token=abc&access_token=xyz&passcode=hello&page=1"
    redacted = _redact_url(raw)
    assert "abc" not in redacted
    assert "xyz" not in redacted
    assert "hello" not in redacted
    assert "page=1" in redacted


def test_redact_url_handles_malformed_input():
    """If parsing fails for any reason, the helper must NOT leak the
    original query string. Falls back to path-only.
    """
    bad = "not://a/real/url?with=garbage&sig=must-not-leak"
    redacted = _redact_url(bad)
    # Either properly redacted or stripped down to before the ?,
    # both are acceptable — what matters is the sig value is gone.
    assert "must-not-leak" not in redacted
