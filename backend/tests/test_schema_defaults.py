"""
Regression tests for the migration/schema-layer review:

P3 - users.is_verified server_default must be FALSE so raw INSERTs that
     omit the column don't silently create verified accounts. Migration
     d7f8g9h0i1 corrects the original c7d8e9f0a1b2 that left the DB
     default as TRUE.
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import User


def test_is_verified_db_default_is_false(db_session: Session):
    """The DB-level default on users.is_verified must be FALSE.
    Pre-fix the default was TRUE, so any raw INSERT (a backfill,
    a manual psql session, an import script) that omitted the
    column silently created a verified account.

    We assert against information_schema rather than running a raw
    INSERT because the row has several other NOT NULL columns
    without DB defaults (is_superadmin, etc.), so a column-skipping
    INSERT fails before reaching the is_verified codepath.
    """
    default = db_session.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'is_verified'"
        )
    ).scalar()
    assert default is not None, "is_verified must have a DB-level default"
    assert "false" in str(default).lower(), (
        f"users.is_verified DB default must be FALSE; got {default!r}. "
        "Pre-fix this defaulted to TRUE, allowing import / backfill paths to "
        "silently mint verified accounts."
    )
