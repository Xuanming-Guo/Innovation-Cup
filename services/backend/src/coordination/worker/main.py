from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence

from coordination.config import Settings, get_settings


def worker_status(settings: Settings) -> dict[str, object]:
    return {
        "service": "coordination-worker",
        "status": "foundation_ready",
        "build_commit": settings.build_commit,
        "environment": settings.environment,
        "queue_consumer_enabled": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coordination Engine durable worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Report worker foundation status and exit without polling",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    print(json.dumps(worker_status(settings), sort_keys=True), flush=True)

    if args.once:
        return 0

    try:
        while True:
            # Durable queue leasing is intentionally introduced by issue #12.
            time.sleep(settings.worker_poll_seconds)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
