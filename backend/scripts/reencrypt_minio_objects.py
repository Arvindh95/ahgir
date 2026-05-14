"""Re-encrypt every existing MinIO object with SSE-S3.

Run AFTER:
1. MINIO_KMS_SECRET_KEY is set on the VPS .env.production
2. MinIO has been recreated to pick up the env
3. The new storage.py with sse=SseS3() is deployed

Objects uploaded before SSE-S3 was enabled stay unencrypted at rest
unless we re-write them. This script iterates the bucket, downloads
each object, and re-uploads it with sse=SseS3() so the at-rest claim
becomes true for the entire current dataset, not just new uploads.

Safe to run while the app is live: each object is re-uploaded with
the same object key, so MinIO atomically replaces the bytes. There is
no window where the object is missing.

Idempotent: an already-encrypted object stays correctly encrypted on
re-write — no harm in running twice.

Usage (on the VPS, inside picur-backend container):
    docker exec picur-backend python scripts/reencrypt_minio_objects.py
"""
import logging
import sys
from io import BytesIO

from minio.sse import SseS3

from app.config import settings
from app.storage import storage_service

logger = logging.getLogger("reencrypt")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    bucket = storage_service.bucket
    client = storage_service.client
    rewritten = 0
    skipped = 0
    failed = 0

    logger.info(f"Re-encrypting all objects in bucket '{bucket}' with SSE-S3")

    for obj in client.list_objects(bucket, recursive=True):
        key = obj.object_name
        try:
            stat = client.stat_object(bucket, key)
            already = (stat.metadata or {}).get("x-amz-server-side-encryption", "").upper()
            if already in ("AES256", "AWS:KMS"):
                logger.debug(f"already encrypted, skipping: {key}")
                skipped += 1
                continue

            response = client.get_object(bucket, key)
            try:
                body = response.read()
            finally:
                response.close()
                response.release_conn()

            content_type = stat.content_type or "application/octet-stream"

            client.put_object(
                bucket,
                key,
                BytesIO(body),
                length=len(body),
                content_type=content_type,
                sse=SseS3(),
            )
            rewritten += 1
            if rewritten % 50 == 0:
                logger.info(f"progress: rewritten={rewritten} skipped={skipped} failed={failed}")
        except Exception as exc:
            failed += 1
            logger.error(f"failed to re-encrypt {key}: {exc}")
            continue

    logger.info(
        f"done — rewritten={rewritten} (now SSE-S3 encrypted), "
        f"skipped={skipped} (already encrypted), failed={failed}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
