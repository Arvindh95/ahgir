"""Cron entrypoint: enqueue a retention check job.

Run from a scheduled container or host cron. Exits 0 on success, non-zero on failure.
The actual deletion runs in an RQ worker, not this script — keep this thin so a
crashing container is recoverable.
"""

import logging
import sys

from app.queue import (
    enqueue_retention_check,
    enqueue_subscription_processor,
    enqueue_stale_pending_reconciler,
    enqueue_storage_cleanup_drain,
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("retention.cron")
    rc = 0
    try:
        job_id = enqueue_retention_check()
        log.info(f"Enqueued retention check job {job_id}")
    except Exception as e:
        log.error(f"Failed to enqueue retention check: {e}", exc_info=True)
        rc = 1
    try:
        job_id = enqueue_subscription_processor()
        log.info(f"Enqueued subscription processor job {job_id}")
    except Exception as e:
        log.error(f"Failed to enqueue subscription processor: {e}", exc_info=True)
        rc = 1
    try:
        job_id = enqueue_stale_pending_reconciler()
        log.info(f"Enqueued stale-pending reconciler job {job_id}")
    except Exception as e:
        log.error(f"Failed to enqueue stale-pending reconciler: {e}", exc_info=True)
        rc = 1
    try:
        job_id = enqueue_storage_cleanup_drain()
        log.info(f"Enqueued storage cleanup drain job {job_id}")
    except Exception as e:
        log.error(f"Failed to enqueue storage cleanup drain: {e}", exc_info=True)
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
