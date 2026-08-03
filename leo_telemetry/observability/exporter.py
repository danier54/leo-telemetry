"""Prometheus metrics exporter."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from datetime import datetime, timezone
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, REGISTRY, start_http_server
from redis.asyncio import Redis

from leo_telemetry.common.models import TelemetryReading
from leo_telemetry.demux.redis_telemetry_queue import RedisTelemetryQueue


_METRIC_CACHE: dict[tuple[int, str], Gauge] = {}
_COUNTER_CACHE: dict[tuple[int, str], Counter] = {}
_TIMESTAMP_CACHE: dict[tuple[int, str], Gauge] = {}

logger = logging.getLogger(__name__)


def start_exporter(port: int = 8000) -> None:
    """Expose the metrics registry over HTTP and consume live telemetry from Redis."""
    if is_port_in_use(port):
        return

    start_http_server(port)
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    poll_interval_seconds = float(os.environ.get("EXPORTER_POLL_INTERVAL_SECONDS", "1.0"))
    asyncio.run(consume_queue_from_redis(redis_url, poll_interval_seconds=poll_interval_seconds))


async def consume_queue_from_redis(
    redis_url: str,
    *,
    poll_interval_seconds: float = 1.0,
) -> None:
    """Continuously export readings drained from the Redis telemetry queue."""
    redis_client = Redis.from_url(redis_url)
    queue = RedisTelemetryQueue(redis_client)

    try:
        await consume_queue(queue, poll_interval_seconds=poll_interval_seconds)
    finally:
        await redis_client.aclose()


async def consume_queue(
    reading_queue: Any,
    *,
    poll_interval_seconds: float = 1.0,
    max_iterations: int | None = None,
) -> int:
    """Drain a queue of TelemetryReading objects and export each one."""
    exported = 0
    while True:
        if max_iterations is not None and exported >= max_iterations:
            return exported

        try:
            reading = await reading_queue.pop()
        except Exception:
            logger.exception("Failed to read telemetry queue; retrying")
            await asyncio.sleep(poll_interval_seconds)
            continue

        if reading is None:
            await asyncio.sleep(poll_interval_seconds)
            continue

        export(reading)
        exported += 1


def start_http_server_if_needed(port: int = 8000) -> bool:
    """Start the Prometheus HTTP server only when the requested port is free."""
    if is_port_in_use(port):
        return False

    start_http_server(port)
    return True


def is_port_in_use(port: int, host: str = "0.0.0.0") -> bool:
    """Return True when the given port is already listening on the provided host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return True
        return False


def export(reading: TelemetryReading, registry: CollectorRegistry | None = None) -> None:
    """Register a telemetry reading's metrics with the Prometheus registry.

    Each metric is exported as a gauge with labels for the satellite id, metric name,
    and unit. This makes the values immediately usable in Grafana panels or
    Prometheus queries.
    """
    target_registry = registry or REGISTRY
    gauge = _get_or_create_gauge(target_registry)
    counter = _get_or_create_counter(target_registry)
    timestamp_gauge = _get_or_create_timestamp_gauge(target_registry)

    counter.labels(satellite_id=str(reading.norad_id)).inc()
    received_at = reading.received_at or datetime.now(timezone.utc)
    timestamp_gauge.labels(satellite_id=str(reading.norad_id)).set(
        received_at.timestamp()
    )

    for metric in reading.metrics:
        gauge.labels(
            metric_name=metric.name,
            unit=metric.unit,
            satellite_id=str(reading.norad_id),
        ).set(float(metric.value))


def _get_or_create_gauge(registry: CollectorRegistry) -> Gauge:
    cache_key = (id(registry), "leo_telemetry_metric_value")
    cached = _METRIC_CACHE.get(cache_key)
    if cached is not None:
        return cached

    gauge = Gauge(
        "leo_telemetry_metric_value",
        "Value of a decoded telemetry metric emitted by leo-telemetry.",
        labelnames=("metric_name", "unit", "satellite_id"),
        registry=registry,
    )
    _METRIC_CACHE[cache_key] = gauge
    return gauge


def _get_or_create_counter(registry: CollectorRegistry) -> Counter:
    cache_key = (id(registry), "leo_telemetry_readings_total")
    cached = _COUNTER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    counter = Counter(
        "leo_telemetry_readings_total",
        "Number of telemetry readings received by the pipeline.",
        labelnames=("satellite_id",),
        registry=registry,
    )
    _COUNTER_CACHE[cache_key] = counter
    return counter


def _get_or_create_timestamp_gauge(registry: CollectorRegistry) -> Gauge:
    cache_key = (id(registry), "leo_telemetry_last_received_timestamp_seconds")
    cached = _TIMESTAMP_CACHE.get(cache_key)
    if cached is not None:
        return cached

    gauge = Gauge(
        "leo_telemetry_last_received_timestamp_seconds",
        "Unix timestamp of the last telemetry reading received for each satellite.",
        labelnames=("satellite_id",),
        registry=registry,
    )
    _TIMESTAMP_CACHE[cache_key] = gauge
    return gauge
