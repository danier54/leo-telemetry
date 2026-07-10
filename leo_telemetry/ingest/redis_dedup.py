"""Redis-backed deduplication queue for overlapping ground-station captures."""

from __future__ import annotations

import pickle

from redis.asyncio import Redis

from leo_telemetry.common.models import RawFrame

SEEN_KEY = "leo_telemetry:ingest:seen"
QUEUE_KEY = "leo_telemetry:ingest:queue"


class RedisDedupQueue:
    """FIFO queue backed by Redis: a set of `dedup_key`s plus a list of frames.

    Frames are pickled for storage. That couples the queue to Python's
    pickle protocol, which is fine here since both producer (ingest) and
    consumer (decode) are Python services sharing this codebase.
    """

    def __init__(self, redis_client: Redis, *, seen_ttl_seconds: int = 7 * 24 * 3600):
        self._redis = redis_client
        self._seen_ttl_seconds = seen_ttl_seconds

    async def push(self, frame: RawFrame) -> bool:
        """Add a frame if unseen. Returns True if it was added."""
        added = await self._redis.sadd(SEEN_KEY, frame.dedup_key)
        if not added:
            return False
        await self._redis.expire(SEEN_KEY, self._seen_ttl_seconds)
        await self._redis.rpush(QUEUE_KEY, pickle.dumps(frame))
        return True

    async def pop(self) -> RawFrame | None:
        """Remove and return the oldest queued frame, or None if empty."""
        raw = await self._redis.lpop(QUEUE_KEY)
        return pickle.loads(raw) if raw is not None else None

    async def qsize(self) -> int:
        return await self._redis.llen(QUEUE_KEY)
