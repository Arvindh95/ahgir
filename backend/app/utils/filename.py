"""Filename sanitization for safe ZIP / filesystem operations.

User-supplied filenames are stored on Image rows and re-emitted in download
ZIPs. Without sanitization, crafted filenames could create zip-slip entries
that overwrite files on extraction (e.g. `../../../etc/passwd`).
"""

import os
import re
import unicodedata
from urllib.parse import quote

# Anything that isn't safe in a cross-platform filename. Keeps unicode letters,
# digits, dot, dash, underscore, space, parentheses.
_UNSAFE = re.compile(r"[^\w\-. ()À-ɏḀ-ỿ]")
_ATTACHMENT_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_LEN = 200


def safe_zip_filename(name: str | None, fallback: str) -> str:
    """Return a path-traversal-safe filename suitable for ZIP entries.

    Strategy:
    1. basename() to strip directory components (handles ../ and absolute paths).
    2. Strip leading dots to avoid hidden files / "..".
    3. Replace remaining unsafe characters with underscore.
    4. Truncate to MAX_LEN preserving extension.
    5. Fall back to caller-provided default if result is empty.
    """
    if not name:
        return fallback

    # Strip any path components, including those introduced via backslash on Windows clients.
    base = os.path.basename(name.replace("\\", "/"))
    base = base.lstrip(".")
    if not base:
        return fallback

    cleaned = _UNSAFE.sub("_", base)
    if not cleaned or cleaned in (".", ".."):
        return fallback

    if len(cleaned) > _MAX_LEN:
        root, ext = os.path.splitext(cleaned)
        keep = _MAX_LEN - len(ext)
        cleaned = root[:keep] + ext

    return cleaned


def safe_attachment_filename(name: str | None, fallback: str = "download") -> str:
    """Return an ASCII filename safe for a Content-Disposition header."""
    raw = str(name or fallback)
    raw = _CONTROL_CHARS.sub("", raw)
    raw = raw.replace("/", "_").replace("\\", "_").strip()

    ascii_name = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    cleaned = _ATTACHMENT_UNSAFE.sub("_", ascii_name)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._- ")

    if not cleaned:
        cleaned = fallback

    if len(cleaned) > _MAX_LEN:
        root, ext = os.path.splitext(cleaned)
        keep = max(1, _MAX_LEN - len(ext))
        cleaned = root[:keep].rstrip("._- ") + ext

    return cleaned or fallback


def attachment_content_disposition(name: str | None, fallback: str = "download") -> str:
    """Build a standards-friendly attachment Content-Disposition value."""
    filename = safe_attachment_filename(name, fallback)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded}"
