"""Composite mission readiness scoring.

Scoring formula (v1): each health-relevant metric contributes a value in
[0, 1] -- 1.0 inside its nominal band, 0.0 outside its hard limits, and
linear in between. The readiness score is the mean contribution. Metrics
whose units carry no health signal (uptime seconds, packet counts, raw
ADC words) are excluded; a reading with no health-relevant metrics
scores 1.0, meaning "no evidence of a problem".

The nominal/hard bands are deliberately generic across the three target
CubeSats; tightening them per satellite is a follow-up once the team
agrees on per-bird limits.
"""

from __future__ import annotations

import math

from leo_telemetry.common.models import TelemetryReading

# unit -> ((nominal_low, nominal_high), (hard_low, hard_high))
_HEALTH_BANDS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "C": ((-10.0, 50.0), (-40.0, 85.0)),
    "V": ((3.3, 8.4), (0.0, 12.0)),
    "mV": ((3300.0, 8400.0), (0.0, 12000.0)),
    "%": ((0.0, 90.0), (0.0, 100.0)),
}


def _metric_health(value: float, unit: str) -> float | None:
    """Score one metric in [0, 1], or None if its unit is not health-relevant."""
    bands = _HEALTH_BANDS.get(unit)
    if bands is None:
        return None
    if not math.isfinite(value):
        return 0.0

    (nom_low, nom_high), (hard_low, hard_high) = bands
    if nom_low <= value <= nom_high:
        return 1.0
    if value < hard_low or value > hard_high:
        return 0.0
    if value < nom_low:
        return (value - hard_low) / (nom_low - hard_low)
    return (hard_high - value) / (hard_high - nom_high)


def compute_readiness_score(reading: TelemetryReading) -> float:
    """Combine a telemetry reading's metrics into a single readiness score."""
    contributions = [
        health
        for metric in reading.metrics
        if (health := _metric_health(metric.value, metric.unit)) is not None
    ]
    if not contributions:
        return 1.0
    return sum(contributions) / len(contributions)
