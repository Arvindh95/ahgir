"""Seed an initial superadmin for a fresh production deploy.

Reads SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD from env. Idempotent — if the user
already exists, refreshes password and ensures superadmin/verified flags. Prints
nothing about the password (env-supplied secret).
"""
import os
import sys
from datetime import datetime
from app.database import SessionLocal
from app.models import User, UserTier
from app.auth import hash_password


def main() -> int:
    email = os.environ.get("SEED_ADMIN_EMAIL")
    password = os.environ.get("SEED_ADMIN_PASSWORD")
    if not email or not password:
        print("SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD must be set", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            existing.password_hash = hash_password(password)
            existing.is_verified = True
            existing.is_superadmin = True
            existing.is_disabled = False
            db.commit()
            uid = existing.id
            print(f"refreshed superadmin {email} (id={uid})")
        else:
            u = User(
                email=email,
                password_hash=hash_password(password),
                is_verified=True,
                is_superadmin=True,
                is_disabled=False,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            uid = u.id
            print(f"created superadmin {email} (id={uid})")

        ut = db.query(UserTier).filter(UserTier.user_id == uid).first()
        if not ut:
            db.add(UserTier(
                user_id=uid,
                tier_name="custom",
                max_events=999,
                max_photos_per_event=99999,
                price_cents=0,
                is_active=True,
                activated_at=datetime.utcnow(),
            ))
            db.commit()
            print("attached custom unlimited tier")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
