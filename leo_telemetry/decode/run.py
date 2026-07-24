"""Long-running decode service: drain the ingest Redis queue, run each
RawFrame through the AX.25 decoder, and push successfully decoded frames
onto a second Redis queue for demux.

Configured entirely via environment variables so it runs unmodified as a
container:

    REDIS_URL                     Redis connection URL (default: redis://localhost:6379/0)
    DECODE_POLL_INTERVAL_SECONDS  seconds to sleep when the input queue is empty (default: 2)
    LOG_LEVEL                     Python logging level name (default: INFO)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from redis.asyncio import Redis

from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.decode.redis_decoded_queue import RedisDecodedQueue
from leo_telemetry.ingest.redis_dedup import RedisDedupQueue

logger = logging.getLogger(__name__)


async def run() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    poll_interval = float(os.environ.get("DECODE_POLL_INTERVAL_SECONDS", "2"))
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    redis_client = Redis.from_url(redis_url)
    in_queue = RedisDedupQueue(redis_client)
    out_queue = RedisDecodedQueue(redis_client)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        while not stop_event.is_set():
            decoded = await _decode_once(in_queue, out_queue)
            if not decoded:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                except asyncio.TimeoutError:
                    pass
    finally:
        await redis_client.aclose()


async def _decode_once(in_queue: RedisDedupQueue, out_queue: RedisDecodedQueue) -> bool:
    """Pop and decode one raw frame. Returns True if a frame was popped
    (so the caller can skip the poll-interval sleep while draining a
    backlog, instead of waiting between every single frame).
    """
    frame = await in_queue.pop()
    if frame is None:
        return False

    try:
        result = decode_frame(frame)
    except Exception:
        logger.exception("Decoder raised on frame from norad=%s, dropping", frame.norad_id)
        return True

    if result is None:
        logger.info("Failed to decode frame from norad=%s", frame.norad_id)
        return True

    await out_queue.push(result)
    logger.info(
        "Decoded frame norad=%s src=%s dest=%s crc_valid=%s",
        result.norad_id, result.src_callsign, result.dest_callsign, result.crc_valid,
    )
    return True


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
