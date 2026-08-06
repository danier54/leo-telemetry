"""Observability service worker daemon.

Drains TelemetryReading objects from the demux Redis queue into the
Prometheus registry, serves the /metrics scrape endpoint, and keeps live
satellite positions updated from Celestrak TLEs via Skyfield.

Runtime Configuration (Environment Variables):
    REDIS_URL: Redis server connection string.
    OBS_POLL_INTERVAL_SECONDS: Idle wait time when input queue is empty.
    METRICS_PORT: TCP port the /metrics endpoint listens on.
    TLE_REFRESH_SECONDS: How often to re-fetch TLEs from Celestrak.
    POSITION_UPDATE_SECONDS: How often to re-propagate satellite positions.
    LOG_LEVEL: Python logging level name (e.g., INFO, DEBUG).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
import signal

import httpx
from redis.asyncio import Redis

from redis.asyncio import Redis as RedisClient

from leo_telemetry.common.satellites import AUDIO_NORAD_IDS, NORAD_IDS
from leo_telemetry.decode.redis_decoded_queue import QUEUE_KEY as DECODED_QUEUE_KEY
from leo_telemetry.demux.redis_telemetry_queue import QUEUE_KEY as TELEMETRY_QUEUE_KEY
from leo_telemetry.demux.redis_telemetry_queue import RedisTelemetryQueue
from leo_telemetry.ingest.redis_dedup import QUEUE_KEY as RAW_QUEUE_KEY
from leo_telemetry.observability.exporter import export, start_scrape_endpoint
from leo_telemetry.observability.last_readings import LastReadingStore
from leo_telemetry.observability.metrics import QUEUE_DEPTH
from leo_telemetry.observability.tracking import fetch_tle, update_position_metrics

_QUEUE_KEYS = {
    "raw": RAW_QUEUE_KEY,
    "decoded": DECODED_QUEUE_KEY,
    "telemetry": TELEMETRY_QUEUE_KEY,
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObservabilityConfig:
    """Runtime configuration for the observability worker."""

    redis_url: str
    poll_interval_seconds: float
    metrics_port: int
    tle_refresh_seconds: float
    position_update_seconds: float
    log_level: str

    @classmethod
    def from_env(cls) -> ObservabilityConfig:
        """Parse and validate runtime settings from environment variables.

        Returns:
            A populated, immutable ObservabilityConfig instance.
        """
        return cls(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            poll_interval_seconds=float(
                os.environ.get("OBS_POLL_INTERVAL_SECONDS", "2.0")
            ),
            metrics_port=int(os.environ.get("METRICS_PORT", "8000")),
            tle_refresh_seconds=float(
                os.environ.get("TLE_REFRESH_SECONDS", "21600")
            ),
            position_update_seconds=float(
                os.environ.get("POSITION_UPDATE_SECONDS", "15")
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )


async def _update_queue_depths(redis_client: RedisClient) -> None:
    """Publish the depth of every stage-to-stage Redis queue."""
    for queue_name, key in _QUEUE_KEYS.items():
        QUEUE_DEPTH.labels(queue=queue_name).set(await redis_client.llen(key))


async def _export_once(
    queue: RedisTelemetryQueue, store: LastReadingStore | None = None
) -> bool:
    """Pop, export, and persist a single reading.

    Args:
        queue: The demux output buffer to pop readings from.
        store: Optional per-satellite persistence for restart replay.

    Returns:
        True if a reading was exported; False if the queue was empty.
    """
    reading = await queue.pop()
    if reading is None:
        return False

    export(reading)
    if store is not None:
        await store.save(reading)
    logger.info(
        "Exported reading norad=%s metrics_count=%d",
        reading.norad_id,
        len(reading.metrics),
    )
    return True


async def _replay_persisted_readings(store: LastReadingStore) -> None:
    """Restore each satellite's latest reading into the fresh registry.

    Without this, a pod restart blanks every per-satellite gauge until
    that satellite next beacons, which can be days.
    """
    readings = await store.load_all()
    for reading in readings:
        export(reading, count=False)
    if readings:
        logger.info(
            "Replayed %d persisted readings into the registry", len(readings)
        )


async def _track_positions(config: ObservabilityConfig, stop_event: asyncio.Event) -> None:
    """Refresh TLEs periodically and re-propagate satellite positions.

    Tracking is best-effort: satellites without published TLEs (or during
    Celestrak outages) are skipped and retried on the next refresh.
    """
    tles: dict[int, tuple[str, str]] = {}
    last_refresh = float("-inf")

    async with httpx.AsyncClient() as client:
        while not stop_event.is_set():
            now = asyncio.get_running_loop().time()
            if now - last_refresh >= config.tle_refresh_seconds:
                for norad_id in NORAD_IDS + AUDIO_NORAD_IDS:
                    tle = await fetch_tle(norad_id, client)
                    if tle is not None:
                        tles[norad_id] = tle
                last_refresh = now
                logger.info("TLE refresh complete; tracking %d satellites", len(tles))

            for norad_id, tle in tles.items():
                try:
                    update_position_metrics(norad_id, tle)
                except Exception:
                    logger.exception(
                        "Position update failed for norad=%s; will retry", norad_id
                    )

            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=config.position_update_seconds
                )
            except asyncio.TimeoutError:
                pass


async def run(config: ObservabilityConfig | None = None) -> None:
    """Execute the asynchronous export and tracking lifecycle.

    Serves the scrape endpoint, registers graceful shutdown handlers, and
    continuously exports readings until interrupted by the OS.

    Args:
        config: Optional configuration override for testing. If omitted,
                settings are loaded from environment variables.
    """
    cfg = config or ObservabilityConfig.from_env()
    logging.basicConfig(level=cfg.log_level)

    redis_client = Redis.from_url(cfg.redis_url)
    queue = RedisTelemetryQueue(redis_client)
    store = LastReadingStore(redis_client)
    await _replay_persisted_readings(store)

    # Register OS signal handlers for Kubernetes pod shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, ValueError):
            pass

    server = start_scrape_endpoint(cfg.metrics_port)
    tracker = asyncio.create_task(_track_positions(cfg, stop_event))

    logger.info(
        "Starting observability service on :%d connected to Redis at %s",
        cfg.metrics_port,
        cfg.redis_url,
    )

    try:
        while not stop_event.is_set():
            exported = await _export_once(queue, store)
            await _update_queue_depths(redis_client)
            if not exported:
                # Sleep when the queue is empty to prevent CPU spinning
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=cfg.poll_interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass
    finally:
        stop_event.set()
        try:
            await tracker
        except Exception:
            logger.exception("Position tracker task failed")
        server.shutdown()
        server.server_close()
        await redis_client.aclose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
