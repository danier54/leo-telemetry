"""One-shot backfill: copy every frame currently sitting in the live Redis
FIFO queue into the Postgres historical archive.

This exists for the one-time migration onto Postgres -- frames that were
already dedup'd and queued before the archive existed wouldn't otherwise
ever land in it, since normal ingest only writes new frames as they're
polled. Safe to re-run: inserts are idempotent on `dedup_key`.

Uses the same environment variables as `leo_telemetry.ingest.run`
(REDIS_URL, POSTGRES_HOST/PORT/DB/USER/PASSWORD).
"""

from __future__ import annotations

import asyncio
import logging
import os

from redis.asyncio import Redis

from leo_telemetry.common.storage import RawFrameStore
from leo_telemetry.ingest.redis_dedup import RedisDedupQueue
from leo_telemetry.ingest.run import _postgres_dsn_from_env

logger = logging.getLogger(__name__)


async def backfill() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    dsn = _postgres_dsn_from_env()
    if dsn is None:
        raise SystemExit("POSTGRES_HOST is not set -- nothing to backfill into")

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    queue = RedisDedupQueue(Redis.from_url(redis_url))
    store = await RawFrameStore.connect(dsn)

    try:
        await store.ensure_schema()
        frames = await queue.peek_all()
        inserted = 0
        for frame in frames:
            if await store.insert_frame(frame):
                inserted += 1
        logger.info(
            "Backfill complete: %d frame(s) in queue, %d newly inserted, %d already present",
            len(frames),
            inserted,
            len(frames) - inserted,
        )
    finally:
        await store.close()


def main() -> None:
    asyncio.run(backfill())


if __name__ == "__main__":
    main()
