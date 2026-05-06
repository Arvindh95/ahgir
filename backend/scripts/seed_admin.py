"""Dev-only: create or refresh a superadmin user for local testing.

Usage (inside backend container):
    PYTHONPATH=/app python scripts/seed_admin.py
"""
from datetime import datetime
from app.database import SessionLocal
from app.models import User, UserTier
from app.auth import hash_password


EMAIL = "admin@picur.dev"
PASSWORD = "DevPass123!"


def main():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == EMAIL).first()
        if existing:
            existing.password_hash = hash_password(PASSWORD)
            existing.is_verified = True
            existing.is_superadmin = True
            existing.is_disabled = False
            db.commit()
            print(f"Updated existing user {EMAIL} (id={existing.id})")
            user_id = existing.id
        else:
            u = User(
                email=EMAIL,
                password_hash=hash_password(PASSWORD),
                is_verified=True,
                is_superadmin=True,
                is_disabled=False,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            print(f"Created superadmin {EMAIL} (id={u.id})")
            user_id = u.id

        ut = db.query(UserTier).filter(UserTier.user_id == user_id).first()
        if not ut:
            db.add(UserTier(
                user_id=user_id,
                tier_name="premium_plus",
                max_events=10,
                max_photos_per_event=500,
                price_cents=10000,
                is_active=True,
                activated_at=datetime.utcnow(),
            ))
            db.commit()
            print("Attached premium_plus tier")

        print()
        print(f"Login at http://localhost:3000/admin/login")
        print(f"  email:    {EMAIL}")
        print(f"  password: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
