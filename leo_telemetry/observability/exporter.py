"""Prometheus metrics exporter."""

from __future__ import annotations

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


def export(reading: TelemetryReading) -> None:
    """Register a telemetry reading's metrics with the Prometheus registry."""
    norad = str(reading.norad_id)
    satellite = satellite_label(reading.norad_id)

    for metric in reading.metrics:
        TELEMETRY_METRIC.labels(
            norad_id=norad,
            satellite=satellite,
            name=metric.name,
            unit=metric.unit,
        ).set(metric.value)

    READINGS_TOTAL.labels(norad_id=norad, satellite=satellite).inc()
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
