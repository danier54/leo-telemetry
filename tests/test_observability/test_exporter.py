from __future__ import annotations

from datetime import datetime, timezone

from leo_telemetry.common.models import TelemetryMetric, TelemetryReading
from leo_telemetry.observability.exporter import export
from leo_telemetry.observability.metrics import REGISTRY


def _reading(norad_id: int = 60525) -> TelemetryReading:
    return TelemetryReading(
        norad_id=norad_id,
        received_at=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
        metrics=(
            TelemetryMetric("battery_1_pack_1_vbatt", 8200.0, "mV"),
            TelemetryMetric("system_uptime", 3600.0, "s"),
        ),
    )


def test_export_registers_metrics_with_prometheus():
    export(_reading())

    value = REGISTRY.get_sample_value(
        "leo_telemetry_metric",
        {
            "norad_id": "60525",
            "satellite": "ORESAT0.5",
            "name": "battery_1_pack_1_vbatt",
            "unit": "mV",
        },
    )
    assert value == 8200.0


def test_export_counts_readings_and_records_receive_time():
    labels = {"norad_id": "60525", "satellite": "ORESAT0.5"}
    before = (
        REGISTRY.get_sample_value("leo_telemetry_readings_total", labels) or 0.0
    )

    export(_reading())

    after = REGISTRY.get_sample_value("leo_telemetry_readings_total", labels)
    assert after == before + 1.0

    timestamp = REGISTRY.get_sample_value(
        "leo_telemetry_last_reading_timestamp_seconds", labels
    )
    assert timestamp == _reading().received_at.timestamp()


def test_export_publishes_readiness_score():
    export(_reading())

    score = REGISTRY.get_sample_value(
        "leo_telemetry_readiness_score",
        {"norad_id": "60525", "satellite": "ORESAT0.5"},
    )
    assert score == 1.0  # vbatt is nominal; uptime carries no health signal


def test_export_labels_unknown_satellite_by_norad_id():
    export(_reading(norad_id=99999))

    value = REGISTRY.get_sample_value(
        "leo_telemetry_metric",
        {
            "norad_id": "99999",
            "satellite": "99999",
            "name": "battery_1_pack_1_vbatt",
            "unit": "mV",
        },
    )
    assert value == 8200.0
