"""Print /health/load output for the local superadmin user.

Run inside picur-backend container to spot capacity pressure.

    docker exec picur-backend python scripts/probe_health_load.py
"""

import json
import sys

import requests

from app.auth import create_access_token
from app.database import SessionLocal
from app.models import User


def main() -> int:
    db = SessionLocal()
    user = db.query(User).filter(User.is_superadmin == True).first()
    if not user:
        print("No superadmin user found")
        return 1
    token = create_access_token({"sub": str(user.id), "email": user.email})
    resp = requests.get(
        "http://127.0.0.1:8000/health/load",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print(f"HTTP {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
