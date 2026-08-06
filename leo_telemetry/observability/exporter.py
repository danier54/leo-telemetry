"""Prometheus metrics exporter."""

from __future__ import annotations

from datetime import datetime
from wsgiref.simple_server import WSGIServer

from prometheus_client import start_http_server

from leo_telemetry.common.models import TelemetryReading
from leo_telemetry.observability.metrics import (
    LAST_READING_TIMESTAMP,
    READINESS_SCORE,
    READINGS_TOTAL,
    REGISTRY,
    TELEMETRY_METRIC,
    satellite_label,
)
from leo_telemetry.scoring.readiness import compute_readiness_score


# Latest received_at exported per satellite, so out-of-order processing
# (API pages arrive newest-first, backfills replay history) can never
# regress the gauges to an older reading's values.
_latest_exported: dict[int, datetime] = {}


def export(reading: TelemetryReading, *, count: bool = True) -> None:
    """Register a telemetry reading's metrics with the Prometheus registry.

    Gauges are monotonic in frame time: a reading older than the
    satellite's newest exported reading only increments the counter.

    Args:
        reading: The reading to publish.
        count:   Whether to increment the readings counter. Startup replay
                 of persisted readings passes False so restarts do not
                 inflate throughput rates.
    """
    norad = str(reading.norad_id)
    satellite = satellite_label(reading.norad_id)

    latest = _latest_exported.get(reading.norad_id)
    if latest is not None and reading.received_at < latest:
        if count:
            READINGS_TOTAL.labels(norad_id=norad, satellite=satellite).inc()
        return
    _latest_exported[reading.norad_id] = reading.received_at

    for metric in reading.metrics:
        TELEMETRY_METRIC.labels(
            norad_id=norad,
            satellite=satellite,
            name=metric.name,
            unit=metric.unit,
        ).set(metric.value)

    if count:
        READINGS_TOTAL.labels(norad_id=norad, satellite=satellite).inc()
    else:
        # Materialize the series at its current value so rate queries
        # have a baseline immediately after startup.
        READINGS_TOTAL.labels(norad_id=norad, satellite=satellite)
    LAST_READING_TIMESTAMP.labels(norad_id=norad, satellite=satellite).set(
        reading.received_at.timestamp()
    )
    READINESS_SCORE.labels(norad_id=norad, satellite=satellite).set(
        compute_readiness_score(reading)
    )


def start_scrape_endpoint(port: int) -> WSGIServer:
    """Serve the shared registry on /metrics for Prometheus to scrape.

    Returns:
        The running WSGI server, so callers (and tests) can shut it down.
    """
    server, _thread = start_http_server(port, registry=REGISTRY)
    return server
