"""Long-running ingest service: poll SatNOGS, dedup, queue for decode.

Configured entirely via environment variables so it runs unmodified as a
container:

    NORAD_IDS                    comma-separated NORAD IDs (default: the three target CubeSats)
    POLL_INTERVAL_SECONDS         seconds to sleep between poll cycles (default: 300)
    MIN_REQUEST_INTERVAL_SECONDS  minimum seconds between individual SatNOGS requests (default: 5)
    REDIS_URL                     Redis connection URL (default: redis://localhost:6379/0)
    SATNOGS_API_TOKEN             optional SatNOGS API token for higher rate limits
    POSTGRES_HOST                 Postgres host; if unset, the historical archive is disabled
    POSTGRES_PORT                 Postgres port (default: 5432)
    POSTGRES_DB                   Postgres database name (default: leo_telemetry)
    POSTGRES_USER                 Postgres user (default: ingest)
    POSTGRES_PASSWORD             Postgres password
    LOG_LEVEL                     Python logging level name (default: INFO)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from redis.asyncio import Redis

from leo_telemetry.common.satellites import NORAD_IDS
from leo_telemetry.common.storage import RawFrameStore
from leo_telemetry.ingest.client import SatNOGSClient
from leo_telemetry.ingest.redis_dedup import RedisDedupQueue

logger = logging.getLogger(__name__)


def _norad_ids_from_env() -> tuple[int, ...]:
    raw = os.environ.get("NORAD_IDS")
    if not raw:
        return NORAD_IDS
    return tuple(int(value.strip()) for value in raw.split(","))


def _postgres_dsn_from_env() -> str | None:
    host = os.environ.get("POSTGRES_HOST")
    if not host:
        return None
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "leo_telemetry")
    user = os.environ.get("POSTGRES_USER", "ingest")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


async def _connect_store() -> RawFrameStore | None:
    """Connect to the Postgres historical archive, if configured.

    The archive is a nice-to-have alongside the Redis queue, not a
    dependency the poll loop needs to function -- so a missing or
    unreachable database logs a warning and disables it rather than
    crashing ingest at startup.
    """
    dsn = _postgres_dsn_from_env()
    if dsn is None:
        return None
    try:
        store = await RawFrameStore.connect(dsn)
        await store.ensure_schema()
        return store
    except Exception:
        logger.exception("Could not connect to Postgres, historical archive disabled")
        return None


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
    store = await _connect_store()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        while not stop_event.is_set():
            await _poll_once(client, queue, store)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
    finally:
        await client.aclose()
        if store is not None:
            await store.close()


async def _poll_once(
    client: SatNOGSClient,
    queue: RedisDedupQueue,
    store: RawFrameStore | None = None,
) -> None:
    try:
        frames = await client.poll()
    except Exception:
        logger.exception("SatNOGS poll failed, will retry next interval")
        return

    added = 0
    for frame in frames:
        if await queue.push(frame):
            added += 1
            if store is not None:
                try:
                    await store.insert_frame(frame)
                except Exception:
                    logger.exception(
                        "Failed to persist frame %s to Postgres archive", frame.dedup_key
                    )
    logger.info("Polled %d frame(s), %d new after dedup", len(frames), added)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
