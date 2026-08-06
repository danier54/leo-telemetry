from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from leo_telemetry.common.models import TelemetryMetric, TelemetryReading
from leo_telemetry.scoring.readiness import compute_readiness_score


def _reading(*metrics: TelemetryMetric) -> TelemetryReading:
    return TelemetryReading(
        norad_id=60525,
        received_at=datetime.now(timezone.utc),
        metrics=metrics,
    )


def test_compute_readiness_score_combines_metrics():
    reading = _reading(
        TelemetryMetric("temp_battery_1", 20.0, "C"),      # nominal -> 1.0
        TelemetryMetric("battery_1_voltage", 15.0, "V"),   # past hard limit -> 0.0
    )

    assert compute_readiness_score(reading) == 0.5


def test_all_nominal_metrics_score_one():
    reading = _reading(
        TelemetryMetric("temp_battery_1", 20.0, "C"),
        TelemetryMetric("battery_1_pack_1_vbatt", 8200.0, "mV"),
        TelemetryMetric("system_storage_percent", 40.0, "%"),
    )

    assert compute_readiness_score(reading) == 1.0


def test_score_degrades_linearly_between_nominal_and_hard_limits():
    # C nominal high is 50, hard high is 85; 67.5 is halfway between.
    reading = _reading(TelemetryMetric("temp_battery_1", 67.5, "C"))

    assert compute_readiness_score(reading) == pytest.approx(0.5)


def test_non_health_units_are_excluded_from_the_score():
    reading = _reading(
        TelemetryMetric("temp_battery_1", 20.0, "C"),
        TelemetryMetric("system_power_cycles", 1_000_000.0, "count"),
        TelemetryMetric("comms_rx_packets", 0.0, "count"),
    )

    assert compute_readiness_score(reading) == 1.0


def test_reading_with_no_health_relevant_metrics_scores_one():
    reading = _reading(TelemetryMetric("system_uptime", 12.0, "s"))

    assert compute_readiness_score(reading) == 1.0


def test_non_finite_values_score_zero():
    reading = _reading(TelemetryMetric("temp_battery_1", math.nan, "C"))

    assert compute_readiness_score(reading) == 0.0
