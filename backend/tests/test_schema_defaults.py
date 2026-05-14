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
    """Raw INSERT that omits is_verified must produce an unverified
    user. Pre-fix the DB default was TRUE so any backfill / import /
    manual psql session created already-verified accounts unless the
    operator explicitly set is_verified=false.
    """
    new_id = uuid.uuid4()
    email = f"raw-{uuid.uuid4().hex}@example.com"

    # Use a raw INSERT with NO is_verified column to force the DB
    # default to apply. Using the ORM would let SQLAlchemy fill in
    # default=False and mask the bug we want to catch.
    db_session.execute(
        text("""
            INSERT INTO users (id, email, password_hash)
            VALUES (:id, :email, :pw)
        """),
        {"id": str(new_id), "email": email, "pw": "x"},
    )
    db_session.commit()

    row = db_session.query(User).filter(User.id == new_id).first()
    assert row is not None
    assert row.is_verified is False, (
        "DB-level default for users.is_verified must be FALSE — a raw INSERT "
        "without the column should produce an unverified account, never a "
        "verified one. Pre-fix this defaulted to TRUE, allowing import / "
        "backfill paths to silently mint verified accounts."
    )
