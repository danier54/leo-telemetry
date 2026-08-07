"""
Implements a Redis-backed Dead-Letter Queue (DLQ) for un-parsable telemetry payloads.

Provides a retention mechanism for dropped frames so they can be analyzed for
hardware anomalies, corrupted data links, or parser bugs without halting the 
live processing pipeline.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from redis.asyncio import Redis

from leo_telemetry.common.models import DecodedFrame

DLQ_KEY = "leo_telemetry:demux:dlq"


@dataclass
class FailedDemuxFrame:
    """Represents a frame that failed structural demultiplexing.
    
    Stores the original payload as a hex string alongside the exact
    Python exception traceback that caused the failure.
    """
    norad_id: int
    received_at: float  # Original capture Unix timestamp
    payload_hex: str
    error_message: str
    traceback: str
    failed_at: float    # Processing failure Unix timestamp

    @classmethod
    def from_exception(
        cls, frame: DecodedFrame, exc: Exception
    ) -> FailedDemuxFrame:
        """
        Construct a failure record directly from the exception context.
        
        Args:
            frame: The DecodedFrame that failed to parse.
            exc: The Exception raised during demultiplexing.
            
        Returns:
            A populated FailedDemuxFrame ready for JSON serialization.
        """
        # Safely extract attributes in case the frame itself is malformed
        norad_id = getattr(frame, "norad_id", 0)
        received_at = getattr(frame, "received_at", None)
        payload = getattr(frame, "payload", b"")
        
        return cls(
            norad_id=norad_id,
            received_at=received_at.timestamp() if received_at else 0.0,
            payload_hex=payload.hex() if isinstance(payload, bytes) else "",
            error_message=str(exc),
            traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            failed_at=datetime.now(timezone.utc).timestamp(),
        )


class DemuxDeadLetterQueue:
    """Bounded Redis List for storing structural parser failures."""

    def __init__(self, redis_client: Redis, max_size: int = 1000):
        """
        Initialize the DLQ connection.
        
        Args:
            redis_client: An active async Redis connection instance.
            max_size: Maximum number of failed frames to retain before eviction 
                      from the tail to prevent memory leaks.
        """
        self._redis = redis_client
        self._max_size = max_size

    async def push(self, failed_frame: FailedDemuxFrame) -> None:
        """
        Serialize and append a failed frame to the DLQ.
        
        Executes an rpush and ltrim in a single Redis pipeline to ensure
        the boundary limit is strictly enforced atomically.
        """
        payload = json.dumps(asdict(failed_frame)).encode("utf-8")
        
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.rpush(DLQ_KEY, payload)
            pipe.ltrim(DLQ_KEY, -self._max_size, -1)
            await pipe.execute()

    async def get_recent(self, count: int = 10) -> list[FailedDemuxFrame]:
        """
        Retrieve the most recent failures without removing them from the queue.
        
        This method uses `lrange` instead of `pop` so the observability track 
        can view failures without permanently deleting them from the queue.
        
        Args:
            count: Number of recent items to retrieve.
            
        Returns:
            A list of instantiated FailedDemuxFrame objects.
        """
        raw_items = await self._redis.lrange(DLQ_KEY, -count, -1)
        results = []
        for item in raw_items:
            if item:
                data = json.loads(item.decode("utf-8"))
                results.append(FailedDemuxFrame(**data))
        return results

    async def qsize(self) -> int:
        """Return the current number of pending dead-letter items."""
        return await self._redis.llen(DLQ_KEY)