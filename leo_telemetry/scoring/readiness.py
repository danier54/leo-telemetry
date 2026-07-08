"""Composite mission readiness scoring."""

from __future__ import annotations

from leo_telemetry.common.models import TelemetryReading


def compute_readiness_score(reading: TelemetryReading) -> float:
    """Combine a telemetry reading's metrics into a single readiness score."""
    raise NotImplementedError
