"""Datetime serialization helpers — emit UTC with a timezone offset.

The DB columns are TIMESTAMP (naive) and the backend writes UTC via
``datetime.utcnow()``. Pydantic's default serializer on a naive datetime
produces an ISO string with NO timezone info, e.g.
``"2026-05-14T06:48:31.252480"``. JavaScript's ``new Date(str)`` parses
strings WITHOUT a timezone as LOCAL time, so a row written one second
ago appears 8 hours old in a Malaysian browser. These helpers force the
UTC offset (``+00:00``) into the serialized string so the browser
parses correctly and ``Date.toLocaleString()`` renders in the user's
real local time.

Use ``UTCDateTime`` as the type annotation on Pydantic response model
fields, or call ``to_utc_iso`` directly when building dict responses
that don't go through Pydantic.
"""
from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import PlainSerializer


def to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Return an ISO 8601 string with a UTC offset.

    Naive datetimes are assumed UTC because the codebase uses
    ``datetime.utcnow()`` throughout and stores into TIMESTAMP columns.
    ``None`` passes through unchanged so callers don't have to
    short-circuit nullable fields.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# Pydantic v2 annotated type. Use in place of ``datetime`` on any
# user-visible response field so the wire format includes the offset.
UTCDateTime = Annotated[
    datetime,
    PlainSerializer(to_utc_iso, return_type=str, when_used="json"),
]
