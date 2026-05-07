"""Verify the P2 security fixes actually trigger the expected guards.

Tests:
  1. Decompression-bomb upload — a small-on-disk image with huge pixel
     count is rejected with 413 before Pillow burns CPU on it.
  2. Deleted guest session — a JWT issued for a session that has been
     removed from the DB no longer authorizes protected guest endpoints.

Run inside picur-backend container so we can hit localhost:8000 and
manipulate the DB directly:
    docker exec -e PYTHONPATH=/app picur-backend python /app/scripts/attack_test_security_fixes.py
"""

import io
import sys
import uuid
from datetime import datetime, timedelta

import requests
from PIL import Image as PILImage

from app.auth import create_access_token, create_event_token, hash_password
from app.database import SessionLocal
from app.models import Event, GuestSession, User, UserTier


BASE_URL = "http://127.0.0.1:8000"


# ---------- Test 1: Decompression bomb ----------

def make_bomb(width: int = 9000, height: int = 9000) -> bytes:
    """Pure-white image at width×height. Compresses to a few hundred KB
    via PNG zlib but expands to width*height*3 bytes uncompressed (>50MP)."""
    img = PILImage.new("RGB", (width, height), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=9, optimize=True)
    return buf.getvalue()


def test_decompression_bomb(token: str, event_uuid: str) -> bool:
    print("\n--- Test 1: Decompression bomb ---")
    bomb = make_bomb()
    pixels = 9000 * 9000  # 81 megapixels
    print(f"  bomb size on disk: {len(bomb):,} bytes")
    print(f"  bomb pixel count : {pixels:,} (limit is 50,000,000)")

    files = {"files": ("bomb.png", bomb, "image/png")}
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{BASE_URL}/events/{event_uuid}/photos",
        files=files,
        headers=headers,
        timeout=30,
    )
    print(f"  HTTP {r.status_code}")
    body = r.text[:400]
    print(f"  body: {body}")

    if r.status_code in (400, 413):
        print("  PASS: bomb rejected before processing")
        return True
    if r.status_code == 201:
        # If accepted, check whether the bomb was accepted as an image (bad)
        # or rejected via validate_image_format which returns failures inline.
        try:
            data = r.json()
            if data.get("uploaded") and not data.get("failed"):
                print("  FAIL: bomb was accepted as a valid image")
                return False
            print(f"  PASS: bomb listed as failed in response: {data.get('failed')}")
            return True
        except Exception:
            print("  ?: 201 with non-JSON body, inspect manually")
            return False
    print(f"  ?: unexpected status {r.status_code}")
    return False


# ---------- Test 2: Deleted guest session ----------

def test_deleted_session(event_uuid: str) -> bool:
    print("\n--- Test 2: Deleted guest session ---")

    db = SessionLocal()

    session_id = uuid.uuid4()
    expires = datetime.utcnow() + timedelta(hours=1)
    jwt_token = create_event_token(
        uuid.UUID(event_uuid),
        session_id,
        expires_delta=timedelta(hours=1),
    )
    row = GuestSession(
        id=session_id,
        event_id=uuid.UUID(event_uuid),
        session_token=jwt_token,
        expires_at=expires,
    )
    db.add(row)
    db.commit()
    print(f"  Created GuestSession id={session_id}")

    # Use the token while session exists — should succeed (e.g., POST /scan
    # requires a face, but the auth check happens first; we just need to
    # know that the request gets past the auth dependency).
    headers = {"Authorization": f"Bearer {jwt_token}"}
    r1 = requests.post(
        f"{BASE_URL}/scan",
        headers=headers,
        json={"image": "not-real-base64"},
        timeout=10,
    )
    print(f"  Step A (session exists) → HTTP {r1.status_code} (expect 4xx but NOT 401)")
    step_a_ok = r1.status_code != 401

    # Now delete the session row
    db.delete(row)
    db.commit()
    db.close()
    print(f"  Deleted GuestSession id={session_id}")

    # Same JWT should now fail with 401
    r2 = requests.post(
        f"{BASE_URL}/scan",
        headers=headers,
        json={"image": "not-real-base64"},
        timeout=10,
    )
    print(f"  Step B (session deleted) → HTTP {r2.status_code} (expect 401)")
    step_b_ok = r2.status_code == 401

    if step_a_ok and step_b_ok:
        print("  PASS: deleted session rejected immediately")
        return True
    print("  FAIL: see step results above")
    return False


# ---------- Setup ----------

def ensure_test_event() -> tuple[str, str]:
    """Get or create a throwaway event owned by superadmin. Returns (admin_jwt, event_uuid)."""
    db = SessionLocal()
    user = db.query(User).filter(User.is_superadmin == True).first()
    if not user:
        raise RuntimeError("no superadmin user found")
    admin_jwt = create_access_token({"sub": str(user.id), "email": user.email})

    event = (
        db.query(Event)
        .filter(Event.owner_user_id == user.id, Event.slug.like("attack-test-%"))
        .first()
    )
    if event is None:
        slug = f"attack-test-{uuid.uuid4().hex[:8]}"
        event = Event(
            owner_user_id=user.id,
            slug=slug,
            name="Attack Test Event",
            allow_downloads=False,
            retention_days=1,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        print(f"Created test event: {slug} ({event.id})")
    else:
        print(f"Reusing test event: {event.slug} ({event.id})")

    eid = str(event.id)
    db.close()
    return admin_jwt, eid


def main() -> int:
    admin_jwt, event_uuid = ensure_test_event()

    results = []
    results.append(("decompression_bomb", test_decompression_bomb(admin_jwt, event_uuid)))
    results.append(("deleted_guest_session", test_deleted_session(event_uuid)))

    print("\n=== Summary ===")
    all_pass = all(ok for _, ok in results)
    for name, ok in results:
        print(f"  {name:30s} {'PASS' if ok else 'FAIL'}")
    print(f"\n{'ALL PASS' if all_pass else 'FAILURES — review above'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
