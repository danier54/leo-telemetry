"""Long-running ingest service: poll SatNOGS, dedup, queue for decode.

Configured entirely via environment variables so it runs unmodified as a
container:

    NORAD_IDS                    comma-separated NORAD IDs (default: the three target CubeSats)
    POLL_INTERVAL_SECONDS         seconds to sleep between poll cycles (default: 300)
    MIN_REQUEST_INTERVAL_SECONDS  minimum seconds between individual SatNOGS requests (default: 5)
    REDIS_URL                     Redis connection URL (default: redis://localhost:6379/0)
    SATNOGS_API_TOKEN             optional SatNOGS API token for higher rate limits
    LOG_LEVEL                     Python logging level name (default: INFO)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from redis.asyncio import Redis

from leo_telemetry.common.satellites import NORAD_IDS
from leo_telemetry.ingest.client import SatNOGSClient
from leo_telemetry.ingest.redis_dedup import RedisDedupQueue

logger = logging.getLogger(__name__)


def _norad_ids_from_env() -> tuple[int, ...]:
    raw = os.environ.get("NORAD_IDS")
    if not raw:
        return NORAD_IDS
    return tuple(int(value.strip()) for value in raw.split(","))


async def run() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    poll_interval = float(os.environ.get("POLL_INTERVAL_SECONDS", "300"))
    min_request_interval = float(os.environ.get("MIN_REQUEST_INTERVAL_SECONDS", "5"))
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    api_token = os.environ.get("SATNOGS_API_TOKEN")

    client = SatNOGSClient(
        _norad_ids_from_env(),
        api_token=api_token,
        min_interval_seconds=min_request_interval,
    )
    queue = RedisDedupQueue(Redis.from_url(redis_url))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        while not stop_event.is_set():
            await _poll_once(client, queue)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
    finally:
        await client.aclose()


async def _poll_once(client: SatNOGSClient, queue: RedisDedupQueue) -> None:
    try:
        frames = await client.poll()
    except Exception:
        logger.exception("SatNOGS poll failed, will retry next interval")
        return

    added = 0
    for frame in frames:
        if await queue.push(frame):
            added += 1
    logger.info("Polled %d frame(s), %d new after dedup", len(frames), added)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
