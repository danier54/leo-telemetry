"""Redis-backed FIFO ring buffer for demultiplexed telemetry readings.

This module provides the decoupling handoff point between the demux
service and downstream consumers (observability and scoring tracks).
"""

from __future__ import annotations

import pickle
from redis.asyncio import Redis

from leo_telemetry.common.models import TelemetryReading

# Shared Redis key for downstream observability and scoring ingestion
QUEUE_KEY = "leo_telemetry:telemetry:queue"


class RedisTelemetryQueue:
    """Bounded Redis FIFO queue for typed TelemetryReading objects."""

    def __init__(self, redis_client: Redis, *, max_queue_size: int = 5000):
        """Initialize the queue connection and configure boundary limits.

        Args:
            redis_client:   An active async Redis connection instance.
            max_queue_size: Maximum number of readings to retain before
                            evicting the oldest items from the head.
        """
        self._redis = redis_client
        self._max_queue_size = max_queue_size

    async def push(self, reading: TelemetryReading) -> None:
        """Serialize and append a reading to the tail.

        Args:
            reading: The typed telemetry model to enqueue.
        """
        payload = pickle.dumps(reading)
        
        # Queue operations locally in memory and flush them to Redis in a single network round-trip
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.rpush(QUEUE_KEY, payload)
            pipe.ltrim(QUEUE_KEY, -self._max_queue_size, -1)
            await pipe.execute()

    async def pop(self) -> TelemetryReading | None:
        """Pop and deserialize the oldest reading from the head of the queue.

        Returns:
            The oldest TelemetryReading, or None if the queue is empty.
        """
        raw = await self._redis.lpop(QUEUE_KEY)

        # Ensure raw is bytes before passing to pickle.loads
        if not isinstance(raw, bytes):
            return None
        
        return pickle.loads(raw)

    async def qsize(self) -> int:
        """Return the current number of pending telemetry readings.

        This method is intended for downstream Prometheus exporters to
        monitor queue saturation and detect potential tail-drop eviction.

        Returns:
            The integer count of currently buffered items.
        """
        return await self._redis.llen(QUEUE_KEY)