"""Filename sanitization for safe ZIP / filesystem operations.

User-supplied filenames are stored on Image rows and re-emitted in download
ZIPs. Without sanitization, crafted filenames could create zip-slip entries
that overwrite files on extraction (e.g. `../../../etc/passwd`).
"""

import os
import re

# Anything that isn't safe in a cross-platform filename. Keeps unicode letters,
# digits, dot, dash, underscore, space, parentheses.
_UNSAFE = re.compile(r"[^\w\-. ()À-ɏḀ-ỿ]")
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
