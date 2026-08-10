"""Redis-backed FIFO queue for decoded frames, handed off to demux.

Unlike RedisDedupQueue and RedisAudioQueue, this queue does not dedup:
DecodedFrame (leo_telemetry/common/models.py) carries no stable identity
field to key a seen-set on, so push() always succeeds. Adding one would
mean changing DecodedFrame, a cross-track contract change out of scope
here.
"""

from __future__ import annotations

import pickle

from redis.asyncio import Redis

from leo_telemetry.common.models import DecodedFrame
from leo_telemetry.decode.constants import (
    DECODED_QUEUE_KEY,
    DEFAULT_DECODED_QUEUE_SIZE,
)

# Backwards-compatible public name used by observability and existing callers.
QUEUE_KEY = DECODED_QUEUE_KEY


class RedisDecodedQueue:
    def __init__(
        self,
        redis_client: Redis,
        *,
        max_queue_size: int = DEFAULT_DECODED_QUEUE_SIZE,
    ):
        self._redis = redis_client
        self._max_queue_size = max_queue_size

    async def push(self, frame: DecodedFrame) -> None:
        await self._redis.rpush(QUEUE_KEY, pickle.dumps(frame))
        await self._redis.ltrim(QUEUE_KEY, -self._max_queue_size, -1)

    async def pop(self) -> DecodedFrame | None:
        raw = await self._redis.lpop(QUEUE_KEY)
        return pickle.loads(raw) if raw is not None else None

    async def qsize(self) -> int:
        return await self._redis.llen(QUEUE_KEY)
