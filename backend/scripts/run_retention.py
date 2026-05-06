"""Cron entrypoint: enqueue a retention check job.

Run from a scheduled container or host cron. Exits 0 on success, non-zero on failure.
The actual deletion runs in an RQ worker, not this script — keep this thin so a
crashing container is recoverable.
"""

import logging
import sys

from app.queue import enqueue_retention_check


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("retention.cron")
    try:
        job_id = enqueue_retention_check()
        log.info(f"Enqueued retention check job {job_id}")
        return 0
    except Exception as e:
        log.error(f"Failed to enqueue retention check: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
