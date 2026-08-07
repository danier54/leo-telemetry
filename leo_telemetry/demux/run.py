"""Demultiplexing service worker daemon.

Drains DecodedFrame objects from the decode Redis queue, executes
per-satellite struct demultiplexing, and pushes typed TelemetryReading
models onto the telemetry Redis queue for observability ingestion.
Malformed frames are routed to a Dead-Letter Queue (DLQ).

Runtime Configuration (Environment Variables):
    REDIS_URL: Redis server connection string.
    DEMUX_POLL_INTERVAL_SECONDS: Idle wait time when input queue is empty.
    DEMUX_MAX_QUEUE_SIZE: Maximum output buffer depth before eviction.
    DEMUX_DLQ_MAX_SIZE: Maximum dead-letter buffer depth before eviction.
    LOG_LEVEL: Python logging level name (e.g., INFO, DEBUG).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
import signal

from redis.asyncio import Redis

from leo_telemetry.decode.redis_decoded_queue import RedisDecodedQueue
from leo_telemetry.demux.demux import demultiplex
from leo_telemetry.demux.redis_telemetry_queue import RedisTelemetryQueue
from leo_telemetry.demux.dlq import DemuxDeadLetterQueue, FailedDemuxFrame

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemuxConfig:
    """Runtime configuration for the demux worker."""

    redis_url: str
    poll_interval_seconds: float
    max_queue_size: int
    dlq_max_size: int
    log_level: str

    @classmethod
    def from_env(cls) -> DemuxConfig:
        """Parse and validate runtime settings from environment variables."""
        return cls(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            poll_interval_seconds=float(
                os.environ.get("DEMUX_POLL_INTERVAL_SECONDS", "2.0")
            ),
            max_queue_size=int(os.environ.get("DEMUX_MAX_QUEUE_SIZE", "5000")),
            dlq_max_size=int(os.environ.get("DEMUX_DLQ_MAX_SIZE", "1000")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )


async def run(config: DemuxConfig | None = None) -> None:
    """Execute the asynchronous polling and demultiplexing lifecycle."""
    cfg = config or DemuxConfig.from_env()
    logging.basicConfig(level=cfg.log_level)

    redis_client = Redis.from_url(cfg.redis_url)
    
    # Initialize all queue dependencies
    in_queue = RedisDecodedQueue(redis_client)
    out_queue = RedisTelemetryQueue(redis_client, max_queue_size=cfg.max_queue_size)
    dlq = DemuxDeadLetterQueue(redis_client, max_size=cfg.dlq_max_size)

    # Register OS signal handlers for Kubernetes pod shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, ValueError):
            pass

    logger.info("Starting demux service connected to Redis at %s", cfg.redis_url)

    try:
        while not stop_event.is_set():
            processed = await _demux_once(in_queue, out_queue, dlq)
            if not processed:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=cfg.poll_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass
    finally:
        await redis_client.aclose()


async def _demux_once(
    in_queue: RedisDecodedQueue, 
    out_queue: RedisTelemetryQueue,
    dlq: DemuxDeadLetterQueue | None = None
) -> bool:
    """Pop, demultiplex, and enqueue a single frame."""
    frame = await in_queue.pop()
    
    if frame is None:
        return False

    # Fallback initialization if called without an explicit DLQ instance
    target_dlq = dlq or DemuxDeadLetterQueue(in_queue._redis)

    try:
        reading = demultiplex(frame)
        if reading is None:
            logger.warning(
                "Demuxer rejected frame from norad=%s; dropping.",
                getattr(frame, "norad_id", "unknown"),
            )
            return True
            
    except Exception as exc:
        logger.exception(
            "Demuxer failed on frame from norad=%s; routing to DLQ.",
            getattr(frame, "norad_id", "unknown"),
        )
        failed_record = FailedDemuxFrame.from_exception(frame, exc)
        await target_dlq.push(failed_record)
        return True

    await out_queue.push(reading)
    logger.info(
        "Demuxed frame norad=%s metrics_count=%d",
        reading.norad_id,
        len(reading.metrics),
    )
    return True


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()