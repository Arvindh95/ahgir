"""Dev-only: remove the old admin@local.test seed if present (rejected by EmailStr now)."""
from app.database import SessionLocal
from app.models import User


def main():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "admin@local.test").first()
        if u:
            db.delete(u)
            db.commit()
            print("Removed admin@local.test")
        else:
            print("No admin@local.test row to remove")
    finally:
        db.close()


if __name__ == "__main__":
    main()
