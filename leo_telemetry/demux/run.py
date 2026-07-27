"""Demultiplexing service worker daemon.

Drains DecodedFrame objects from the decode Redis queue, executes
per-satellite struct demultiplexing, and pushes typed TelemetryReading
models onto the telemetry Redis queue for observability ingestion.

Runtime Configuration (Environment Variables):
    REDIS_URL: Redis server connection string.
    DEMUX_POLL_INTERVAL_SECONDS: Idle wait time when input queue is empty.
    DEMUX_MAX_QUEUE_SIZE: Maximum output buffer depth before eviction.
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemuxConfig:
    """Runtime configuration for the demux worker."""

    redis_url: str
    poll_interval_seconds: float
    max_queue_size: int
    log_level: str

    @classmethod
    def from_env(cls) -> DemuxConfig:
        """Parse and validate runtime settings from environment variables.

        Returns:
            A populated, immutable DemuxConfig instance.
        """
        return cls(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            poll_interval_seconds=float(
                os.environ.get("DEMUX_POLL_INTERVAL_SECONDS", "2.0")
            ),
            max_queue_size=int(os.environ.get("DEMUX_MAX_QUEUE_SIZE", "5000")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )


async def run(config: DemuxConfig | None = None) -> None:
    """Execute the asynchronous polling and demultiplexing lifecycle.

    Establishes queue connections, registers graceful shutdown handlers,
    and continuously processes frames until interrupted by the OS.

    Args:
        config: Optional configuration override for testing. If omitted,
                settings are loaded from environment variables.
    """
    cfg = config or DemuxConfig.from_env()
    logging.basicConfig(level=cfg.log_level)

    redis_client = Redis.from_url(cfg.redis_url)
    in_queue = RedisDecodedQueue(redis_client)
    out_queue = RedisTelemetryQueue(
        redis_client, max_queue_size=cfg.max_queue_size
    )

    # Register OS signal handlers for Kubernetes pod shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, ValueError):
            pass

    logger.info(
        "Starting demux service connected to Redis at %s", cfg.redis_url
    )

    try:
        while not stop_event.is_set():
            processed = await _demux_once(in_queue, out_queue)
            if not processed:
                # Sleep when the queue is empty to prevent CPU spinning
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=cfg.poll_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass
    finally:
        await redis_client.aclose()


async def _demux_once(
    in_queue: RedisDecodedQueue, out_queue: RedisTelemetryQueue
) -> bool:
    """Pop, demultiplex, and enqueue a single frame.

    Args:
        in_queue:  The decode stage buffer to pop raw frames from.
        out_queue: The telemetry buffer to push typed readings to.

    Returns:
        True if a frame was processed or intentionally dropped; False if
        the input queue was empty.
    """
    frame = await in_queue.pop()
    
    if frame is None:
        # Exit immediately, avoid all parsing logic
        return False

    try:
        reading = demultiplex(frame)
    except Exception:
        # Log and exit early without pushing garbage to the output queue
        logger.exception(
            "Demuxer failed on frame from norad=%s; dropping.", frame.norad_id
        )
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