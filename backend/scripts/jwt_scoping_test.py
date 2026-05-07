"""Verify JWT type-scoping fix: only type=access tokens authorize admin API.

Audit P1 finding: get_current_user accepted any signed JWT with a sub claim.
Email-verify and password-reset tokens both contained sub, so 1-hour links
worked as Bearer tokens for protected admin endpoints. Fix: require
type=access on the JWT. This script proves it.
"""

import sys
import requests

from app.auth import (
    create_access_token,
    create_verification_token,
    create_password_reset_token,
)
from app.database import SessionLocal
from app.models import User


def main() -> int:
    db = SessionLocal()
    user = db.query(User).filter(User.is_superadmin == True).first()
    if not user:
        print("No superadmin user found")
        return 1

    access = create_access_token({"sub": str(user.id), "email": user.email})
    verify = create_verification_token(user.id)
    reset = create_password_reset_token(user.id)

    url = "http://127.0.0.1:8000/payments/my-tier"

    def probe(token: str) -> int:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        return r.status_code

    print(f"{'TOKEN TYPE':<18}{'STATUS':<10}{'EXPECT'}")
    print("-" * 45)
    results = []
    for label, tok, expect in [
        ("access", access, 200),
        ("email_verify", verify, 401),
        ("password_reset", reset, 401),
    ]:
        status = probe(tok)
        ok = status == expect
        results.append(ok)
        print(f"{label:<18}{status:<10}{expect}  {'PASS' if ok else 'FAIL'}")

    print()
    print(f"=== JWT SCOPING: {'ALL PASS' if all(results) else 'FAILED'} ===")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
