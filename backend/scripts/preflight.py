"""Production preflight — call validate_production_secrets() and exit.

Used as a startup gate for sidecar processes (worker, retention-scheduler).
The API process runs the same check at FastAPI import time in app/main.py;
sidecars skip module-import validation (config.py explains why) so they
need an explicit preflight call before doing real work.

Exit codes:
  0 — config OK (production-shaped + all secrets pass, OR not production)
  1 — production validation raised (insecure config)
"""

import sys

from app.config import validate_production_secrets


def main() -> int:
    try:
        validate_production_secrets()
    except RuntimeError as e:
        print(f"[preflight] BLOCKED:\n{e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
