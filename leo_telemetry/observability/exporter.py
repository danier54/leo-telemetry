"""Prometheus metrics exporter."""

from __future__ import annotations

from leo_telemetry.common.models import TelemetryReading


def export(reading: TelemetryReading) -> None:
    """Register a telemetry reading's metrics with the Prometheus registry."""
    raise NotImplementedError
