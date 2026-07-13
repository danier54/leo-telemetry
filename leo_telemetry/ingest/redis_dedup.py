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

    def __init__(
        self,
        redis_client: Redis,
        *,
        seen_ttl_seconds: int = 7 * 24 * 3600,
        max_queue_size: int = 5000,
    ):
        self._redis = redis_client
        self._seen_ttl_seconds = seen_ttl_seconds
        self._max_queue_size = max_queue_size

    async def push(self, frame: RawFrame) -> bool:
        """Add a frame if unseen. Returns True if it was added.

        The seen-set's TTL is set once (`nx=True`) rather than refreshed on
        every push, so it actually rolls off `seen_ttl_seconds` after first
        use instead of being extended forever by a steady trickle of new
        frames. The queue is trimmed to `max_queue_size`, dropping the
        oldest entries first, so it can't grow without bound while no
        consumer is draining it.
        """
        added = await self._redis.sadd(SEEN_KEY, frame.dedup_key)
        if not added:
            return False
        await self._redis.expire(SEEN_KEY, self._seen_ttl_seconds, nx=True)
        await self._redis.rpush(QUEUE_KEY, pickle.dumps(frame))
        await self._redis.ltrim(QUEUE_KEY, -self._max_queue_size, -1)
        return True

    async def pop(self) -> RawFrame | None:
        """Remove and return the oldest queued frame, or None if empty."""
        raw = await self._redis.lpop(QUEUE_KEY)
        return pickle.loads(raw) if raw is not None else None

    async def qsize(self) -> int:
        return await self._redis.llen(QUEUE_KEY)

    async def peek_all(self) -> list[RawFrame]:
        """Return every currently queued frame without removing them.

        Not part of the normal push/pop consumer flow -- used for one-off
        operations like backfilling the Postgres historical archive.
        """
        raw_items = await self._redis.lrange(QUEUE_KEY, 0, -1)
        return [pickle.loads(raw) for raw in raw_items]
