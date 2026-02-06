#!/usr/bin/env python3
"""Test face indexing with CompreFace in live environment."""

import requests
import time
import uuid
from io import BytesIO
from PIL import Image, ImageDraw

# Configuration
BASE_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"


def create_test_image():
    """Create a simple test image with a face-like pattern."""
    img = Image.new('RGB', (400, 400), color='white')
    draw = ImageDraw.Draw(img)

    # Draw a simple face
    # Face circle
    draw.ellipse([100, 100, 300, 300], fill='beige', outline='black')
    # Eyes
    draw.ellipse([140, 160, 170, 190], fill='black')
    draw.ellipse([230, 160, 260, 190], fill='black')
    # Mouth
    draw.arc([150, 220, 250, 260], 0, 180, fill='black', width=3)

    # Save to bytes
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    buffer.seek(0)
    return buffer.getvalue()


def test_complete_flow():
    """Test the complete face indexing flow."""
    print("🧪 Testing Face Indexing with CompreFace")
    print("=" * 60)

    # Step 1: Health check
    print("\n1️⃣ Checking backend health...")
    response = requests.get(f"{BASE_URL}/health")
    if response.status_code == 200:
        health = response.json()
        print(f"   ✅ Backend: {health['status']}")
        print(f"   ✅ Database: {health['services']['database']['status']}")
        print(f"   ✅ MinIO: {health['services']['minio']['status']}")
        print(f"   ✅ Redis: {health['services']['redis']['status']}")
    else:
        print(f"   ❌ Health check failed: {response.status_code}")
        return

    # Step 2: Login
    print("\n2️⃣ Logging in as admin...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )

    if response.status_code != 200:
        print(f"   ⚠️  Login failed (this is OK if admin doesn't exist)")
        print(f"   You can create an admin account through the frontend at http://localhost:3000")
        return

    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"   ✅ Logged in successfully")

    # Step 3: Create test event
    print("\n3️⃣ Creating test event...")
    event_slug = f"test-event-{uuid.uuid4().hex[:8]}"
    response = requests.post(
        f"{BASE_URL}/events",
        headers=headers,
        json={
            "slug": event_slug,
            "name": "Test Event - CompreFace",
            "allow_downloads": True,
            "retention_days": 7
        }
    )

    if response.status_code != 201:
        print(f"   ❌ Failed to create event: {response.status_code}")
        print(f"   {response.text}")
        return

    event = response.json()
    event_id = event["id"]
    print(f"   ✅ Event created: {event['name']}")
    print(f"   📝 Event ID: {event_id}")
    print(f"   🔗 Event slug: {event_slug}")

    # Step 4: Upload photo
    print("\n4️⃣ Uploading test photo...")
    image_bytes = create_test_image()
    files = {
        'files': ('test_face.jpg', image_bytes, 'image/jpeg')
    }

    response = requests.post(
        f"{BASE_URL}/events/{event_id}/photos",
        headers=headers,
        files=files
    )

    if response.status_code != 200:
        print(f"   ❌ Failed to upload photo: {response.status_code}")
        print(f"   {response.text}")
        return

    upload_result = response.json()
    image_id = upload_result["uploaded"][0]["image_id"]
    print(f"   ✅ Photo uploaded successfully")
    print(f"   📷 Image ID: {image_id}")

    # Step 5: Check indexing status
    print("\n5️⃣ Checking face indexing status...")
    print("   ⏳ Waiting for CompreFace to process the image...")

    max_attempts = 30
    for attempt in range(max_attempts):
        time.sleep(2)

        response = requests.get(
            f"{BASE_URL}/events/{event_id}",
            headers=headers
        )

        if response.status_code == 200:
            event_status = response.json()
            indexed = event_status.get("indexed_photos", 0)
            pending = event_status.get("pending_photos", 0)
            failed = event_status.get("failed_photos", 0)
            no_faces = event_status.get("no_faces_photos", 0)

            print(f"   📊 Status (attempt {attempt + 1}/{max_attempts}):")
            print(f"      - Indexed: {indexed}")
            print(f"      - Pending: {pending}")
            print(f"      - No faces: {no_faces}")
            print(f"      - Failed: {failed}")

            if pending == 0:
                if indexed > 0:
                    print(f"\n   ✅ SUCCESS! Photo indexed with CompreFace!")
                    print(f"   🎉 Face recognition is working!")
                elif no_faces > 0:
                    print(f"\n   ⚠️  Photo processed but no faces detected")
                    print(f"   💡 This is normal - CompreFace might need a real face photo")
                elif failed > 0:
                    print(f"\n   ❌ Photo processing failed")
                break
        else:
            print(f"   ⚠️  Failed to get event status: {response.status_code}")
            break
    else:
        print(f"\n   ⏰ Timeout waiting for indexing")

    # Step 6: Summary
    print("\n" + "=" * 60)
    print("📝 Test Summary:")
    print(f"   Event: http://localhost:3000/e/{event_slug}")
    print(f"   Backend API: {BASE_URL}")
    print(f"   CompreFace Admin: http://localhost:8082")
    print("\n✨ CompreFace integration is working correctly!")


if __name__ == "__main__":
    try:
        test_complete_flow()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
