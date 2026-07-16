"""Redis-backed dedup queue for audio observation metadata.

Mirrors RedisDedupQueue's shape (seen-set + FIFO list) but for
AudioObservation instead of RawFrame, under separate keys so the two queues
don't collide.
"""

from __future__ import annotations

import pickle

from redis.asyncio import Redis

from leo_telemetry.ingest.audio_client import AudioObservation

SEEN_KEY = "leo_telemetry:ingest:audio:seen"
QUEUE_KEY = "leo_telemetry:ingest:audio:queue"


class RedisAudioQueue:
    """FIFO queue of AudioObservation metadata, deduped by observation_id."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        seen_ttl_seconds: int = 7 * 24 * 3600,
        max_queue_size: int = 500,
    ):
        self._redis = redis_client
        self._seen_ttl_seconds = seen_ttl_seconds
        self._max_queue_size = max_queue_size

    async def push(self, observation: AudioObservation) -> bool:
        """Add an observation if unseen. Returns True if it was added."""
        added = await self._redis.sadd(SEEN_KEY, observation.dedup_key)
        if not added:
            return False
        await self._redis.expire(SEEN_KEY, self._seen_ttl_seconds, nx=True)
        await self._redis.rpush(QUEUE_KEY, pickle.dumps(observation))
        await self._redis.ltrim(QUEUE_KEY, -self._max_queue_size, -1)
        return True

    async def pop(self) -> AudioObservation | None:
        raw = await self._redis.lpop(QUEUE_KEY)
        return pickle.loads(raw) if raw is not None else None

    async def qsize(self) -> int:
        return await self._redis.llen(QUEUE_KEY)
