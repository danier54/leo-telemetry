"""Redis-backed store of each satellite's most recent TelemetryReading.

The Prometheus registry is in-memory, so a pod restart would blank every
per-satellite gauge until that satellite next beacons -- which for these
CubeSats can be days. The exporter saves the latest reading per satellite
here and replays them into the registry on startup, so restarts do not
erase the dashboard's view of the fleet.
"""

from __future__ import annotations

import pickle

from redis.asyncio import Redis

from leo_telemetry.common.models import TelemetryReading

HASH_KEY = "leo_telemetry:observability:last_readings"


class LastReadingStore:
    """Per-satellite latest-reading persistence in a Redis hash."""

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    async def save(self, reading: TelemetryReading) -> None:
        """Persist a reading as its satellite's most recent.

        Keeps the stored reading when it is newer than the incoming one,
        so out-of-order processing cannot regress the replay state.
        """
        stored = await self._redis.hget(HASH_KEY, str(reading.norad_id))
        if stored is not None:
            existing: TelemetryReading = pickle.loads(stored)
            if existing.received_at > reading.received_at:
                return
        await self._redis.hset(
            HASH_KEY, str(reading.norad_id), pickle.dumps(reading)
        )

    async def load_all(self) -> list[TelemetryReading]:
        """Return the stored latest reading for every satellite."""
        raw = await self._redis.hgetall(HASH_KEY)
        return [pickle.loads(value) for value in raw.values()]
